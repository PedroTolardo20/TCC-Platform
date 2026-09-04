#!/usr/bin/env python3
"""Cliente de acao rclpy para o MoveGroup, cobrindo o braco+gripper do RAV.

Substitui a API moveit_commander (ROS1, indisponivel aqui) por um cliente
proprio da action /move_action do move_group -- e o que moveit_commander e
moveit_py fazem por baixo dos panos, sem a camada de conveniencia.

move_to_pose resolve o IK via /compute_ik e manda o resultado como meta em
espaco de juntas (mesmo caminho de move_to_named_state) em vez de usar
Position/OrientationConstraint direto no OMPL: testado na pratica, o goal
sampler do OMPL falha em amostrar a regiao (tolerancia curta demais pra um
braco de so 3 DOF), enquanto o IK direto resolve de primeira.
"""

import threading
import xml.etree.ElementTree as ET
from pathlib import Path

import rclpy
from ament_index_python.packages import get_package_share_directory
from geometry_msgs.msg import Point, Pose, Quaternion
from moveit_msgs.action import MoveGroup
from moveit_msgs.msg import (
    AttachedCollisionObject,
    CollisionObject,
    Constraints,
    JointConstraint,
    MoveItErrorCodes,
    PlanningScene,
    PlanningSceneWorld,
    RobotState,
)
from moveit_msgs.srv import ApplyPlanningScene, GetPositionIK
from rclpy.action import ActionClient
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from shape_msgs.msg import SolidPrimitive

from rav_manipulator_moveit_config.srv import (
    MoveToNamedState,
    MoveToPose,
    Pick,
    Place,
)

ARM_GROUP = "rav_arm"
ARM_JOINTS = ["shoulder_joint", "elbow_joint", "wrist_joint"]
GRIPPER_GROUP = "rav_gripper"
TCP_LINK = "gripper_tcp"
TOUCH_LINKS = [
    "gripper_base_link",
    "gripper_pinion_link",
    "left_finger_link",
    "right_finger_link",
]
GRASP_OBJECT_ID = "grasped_object"
DEFAULT_FRAME = "manipulator_world"

# As 3 juntas do braco giram no mesmo eixo, entao o conjunto de
# orientacoes alcancaveis do gripper_tcp e estreito -- travar uma
# orientacao arbitraria junto com a posicao costuma falhar no IK
# (confirmado testando: nem com boa semente, nem via OMPL puro-posicao
# resolve de forma generica). Com free_orientation, tentamos essas
# candidatas em ordem e usamos a primeira que o IK resolver: identidade
# primeiro (alcanca uma regiao maior, comprovado empiricamente), depois
# a "vertical" usada nos poses nomeados (home/ready/cad_reference).
FREE_ORIENTATION_CANDIDATES = [
    Quaternion(x=0.0, y=0.0, z=0.0, w=1.0),
    Quaternion(x=0.710, y=0.0, z=0.0, w=0.704),
]

PLANNING_ATTEMPTS = 5
PLANNING_TIME_S = 5.0
GOAL_WAIT_TIMEOUT_S = PLANNING_TIME_S + 15.0
IK_TIMEOUT_S = 2.0
JOINT_TOLERANCE = 0.01


def _parse_named_states(srdf_path: Path) -> dict:
    """Le rav_manipulator.srdf: {group: {state_name: {joint: valor}}}.

    Fonte unica de verdade para os group_state -- nao duplica os valores
    de home/ready/open/closed no codigo Python.
    """
    tree = ET.parse(srdf_path)
    states: dict = {}
    for group_state in tree.getroot().findall("group_state"):
        group = group_state.get("group")
        name = group_state.get("name")
        joints = {
            joint.get("name"): float(joint.get("value"))
            for joint in group_state.findall("joint")
        }
        states.setdefault(group, {})[name] = joints
    return states


class RavManipulator(Node):
    """Braco + gripper do RAV, via /move_action e /compute_ik do move_group."""

    def __init__(self):
        super().__init__("rav_manipulator")

        srdf_path = (
            Path(get_package_share_directory("rav_manipulator_moveit_config"))
            / "config"
            / "rav_manipulator.srdf"
        )
        self._named_states = _parse_named_states(srdf_path)
        # Dicionario nome->grupo (ex.: "ready"->"rav_arm", "open"->
        # "rav_gripper"), derivado do SRDF: quem chama move_to_named_state
        # so precisa saber o nome da pose, nao o grupo.
        self._state_to_group = {
            state_name: group
            for group, states in self._named_states.items()
            for state_name in states
        }

        # Callback group unico e reentrante: os handlers de servico bloqueiam
        # esperando a action/servico do move_group terminar, entao a
        # resposta precisa poder rodar em outra thread do executor ao
        # mesmo tempo (ver _wait_for_future).
        cb_group = ReentrantCallbackGroup()

        self._move_action = ActionClient(
            self, MoveGroup, "move_action", callback_group=cb_group
        )
        self._ik_client = self.create_client(
            GetPositionIK, "compute_ik", callback_group=cb_group
        )
        self._scene_client = self.create_client(
            ApplyPlanningScene, "apply_planning_scene", callback_group=cb_group
        )

        self.create_service(
            MoveToNamedState,
            "move_to_named_state",
            self._handle_move_to_named_state,
            callback_group=cb_group,
        )
        self.create_service(
            MoveToPose, "move_to_pose", self._handle_move_to_pose,
            callback_group=cb_group,
        )
        self.create_service(
            Pick, "pick", self._handle_pick, callback_group=cb_group
        )
        self.create_service(
            Place, "place", self._handle_place, callback_group=cb_group
        )

        self.get_logger().info("rav_manipulator pronto.")

    # ------------------------------------------------------------------
    # Espera bloqueante por um future sem tomar o executor principal.
    # ------------------------------------------------------------------
    def _wait_for_future(self, future, timeout_s: float):
        # Nao usa rclpy.spin_until_future_complete: chamado de dentro de um
        # callback de servico que ja roda sob o MultiThreadedExecutor
        # principal, spin_until_future_complete cria um executor temporario
        # proprio que disputa recursos com ele e trava a partir da segunda
        # chamada. add_done_callback + threading.Event deixa as OUTRAS
        # threads do executor principal processarem a resposta normalmente.
        done = threading.Event()
        future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout=timeout_s):
            return None
        return future.result()

    # ------------------------------------------------------------------
    # Nucleo: unico lugar que fala com a action /move_action
    # ------------------------------------------------------------------
    def _plan_and_execute(
        self, group_name: str, constraints: Constraints
    ) -> tuple[bool, str]:
        if not self._move_action.wait_for_server(timeout_sec=5.0):
            return False, "move_group nao respondeu (action /move_action indisponivel)"

        goal = MoveGroup.Goal()
        goal.request.group_name = group_name
        goal.request.goal_constraints = [constraints]
        goal.request.num_planning_attempts = PLANNING_ATTEMPTS
        goal.request.allowed_planning_time = PLANNING_TIME_S
        goal.planning_options.plan_only = False

        goal_handle = self._wait_for_future(
            self._move_action.send_goal_async(goal), GOAL_WAIT_TIMEOUT_S
        )
        if goal_handle is None:
            return False, "timeout esperando move_group aceitar o goal"
        if not goal_handle.accepted:
            return False, "move_group rejeitou o goal"

        result = self._wait_for_future(
            goal_handle.get_result_async(), GOAL_WAIT_TIMEOUT_S
        )
        if result is None:
            return False, "timeout esperando o resultado do move_group"

        error_code = result.result.error_code.val
        if error_code == MoveItErrorCodes.SUCCESS:
            trajectory_points = result.result.planned_trajectory.joint_trajectory.points
            if len(trajectory_points) <= 1:
                self.get_logger().warn(
                    f"Goal do grupo '{group_name}' ja estava satisfeito "
                    f"(dentro da tolerancia de {JOINT_TOLERANCE} rad) -- "
                    "sucesso reportado sem nenhum movimento real."
                )
            return True, "ok"
        return False, f"falhou com error_code={error_code}"

    # ------------------------------------------------------------------
    # Movimentos basicos
    # ------------------------------------------------------------------
    def move_to_named_state(self, state_name: str) -> tuple[bool, str]:
        group = self._state_to_group.get(state_name)
        if group is None:
            options = ", ".join(sorted(self._state_to_group))
            return False, f"'{state_name}' nao existe no SRDF (opcoes: {options})"

        joints = self._named_states[group][state_name]
        return self._plan_and_execute(group, self._joint_constraints(joints))

    def move_to_pose(self, x: float, y: float, z: float, frame_id: str = DEFAULT_FRAME) -> tuple[bool, str]:
        position = Point(x=x, y=y, z=z)

        last_msg = "sem orientacoes candidatas"
        for orientation in FREE_ORIENTATION_CANDIDATES:
            target = Pose(position=position, orientation=orientation)
            ok, joints_or_msg = self._solve_ik(target, frame_id)
            if ok:
                return self._plan_and_execute(
                    ARM_GROUP, self._joint_constraints(joints_or_msg)
                )
            last_msg = joints_or_msg
        return False, last_msg

    def _solve_ik(self, pose: Pose, frame_id: str):
        """Retorna (True, {joint: valor}) ou (False, mensagem de erro)."""
        ik_request = GetPositionIK.Request()
        ik_request.ik_request.group_name = ARM_GROUP
        ik_request.ik_request.ik_link_name = TCP_LINK
        ik_request.ik_request.pose_stamped.header.frame_id = frame_id
        ik_request.ik_request.pose_stamped.pose = pose
        ik_request.ik_request.timeout.sec = int(IK_TIMEOUT_S)
        ik_request.ik_request.avoid_collisions = True

        if not self._ik_client.wait_for_service(timeout_sec=5.0):
            return False, "compute_ik nao respondeu (servico indisponivel)"

        response = self._wait_for_future(
            self._ik_client.call_async(ik_request), IK_TIMEOUT_S + 5.0
        )
        if response is None:
            return False, "timeout esperando o compute_ik"
        if response.error_code.val != MoveItErrorCodes.SUCCESS:
            return False, f"IK falhou com error_code={response.error_code.val}"

        solution = dict(
            zip(response.solution.joint_state.name, response.solution.joint_state.position)
        )
        return True, {name: solution[name] for name in ARM_JOINTS}

    @staticmethod
    def _joint_constraints(joints: dict) -> Constraints:
        constraints = Constraints()
        constraints.joint_constraints = [
            JointConstraint(
                joint_name=name,
                position=value,
                tolerance_above=JOINT_TOLERANCE,
                tolerance_below=JOINT_TOLERANCE,
                weight=1.0,
            )
            for name, value in joints.items()
        ]
        return constraints

    # ------------------------------------------------------------------
    # Objeto de colisao (pick/place)
    # ------------------------------------------------------------------
    def _apply_planning_scene(self, scene: PlanningScene) -> tuple[bool, str]:
        # /apply_planning_scene em vez de publicar nos topicos
        # collision_object/attached_collision_object: publicar logo apos
        # criar o publisher pode perder a mensagem porque o move_group
        # ainda nao descobriu o publisher (race de discovery do ROS2). O
        # servico e sincrono e confirma sucesso.
        scene.is_diff = True
        if not self._scene_client.wait_for_service(timeout_sec=5.0):
            return False, "apply_planning_scene nao respondeu (servico indisponivel)"
        request = ApplyPlanningScene.Request(scene=scene)
        response = self._wait_for_future(self._scene_client.call_async(request), 5.0)
        if response is None:
            return False, "timeout esperando o apply_planning_scene"
        if not response.success:
            return False, "apply_planning_scene recusou a mudanca"
        return True, "ok"

    def _add_grasp_object(
        self, pose: Pose, radius: float, height: float, frame_id: str
    ) -> tuple[bool, str]:
        obj = CollisionObject()
        obj.header.frame_id = frame_id
        obj.id = GRASP_OBJECT_ID
        obj.primitives = [
            SolidPrimitive(type=SolidPrimitive.CYLINDER, dimensions=[height, radius])
        ]
        obj.primitive_poses = [pose]
        obj.operation = CollisionObject.ADD
        scene = PlanningScene(world=PlanningSceneWorld(collision_objects=[obj]))
        return self._apply_planning_scene(scene)

    def _attach_grasp_object(self) -> tuple[bool, str]:
        attached = AttachedCollisionObject()
        attached.link_name = TCP_LINK
        attached.object.id = GRASP_OBJECT_ID
        attached.object.operation = CollisionObject.ADD
        attached.touch_links = TOUCH_LINKS
        scene = PlanningScene(
            robot_state=RobotState(
                attached_collision_objects=[attached], is_diff=True
            )
        )
        return self._apply_planning_scene(scene)

    def _detach_and_remove_grasp_object(self) -> tuple[bool, str]:
        # Detach (volta pro robot_state) e remove do mundo na mesma
        # atualizacao -- so detach deixa o objeto solto na cena, sem dono.
        attached = AttachedCollisionObject()
        attached.link_name = TCP_LINK
        attached.object.id = GRASP_OBJECT_ID
        attached.object.operation = CollisionObject.REMOVE

        world_removal = CollisionObject()
        world_removal.id = GRASP_OBJECT_ID
        world_removal.operation = CollisionObject.REMOVE

        scene = PlanningScene(
            robot_state=RobotState(
                attached_collision_objects=[attached], is_diff=True
            ),
            world=PlanningSceneWorld(collision_objects=[world_removal]),
        )
        return self._apply_planning_scene(scene)

    # ------------------------------------------------------------------
    # Pick / place
    # ------------------------------------------------------------------
    def pick(
        self, x: float, y: float, z: float,
        radius: float = 0.02, height: float = 0.08, frame_id: str = DEFAULT_FRAME,
    ) -> tuple[bool, str]:
        ok, msg = self.move_to_named_state("open")
        if not ok:
            return False, f"falha ao abrir a gripper: {msg}"

        ok, msg = self.move_to_pose(x, y, z, frame_id)
        if not ok:
            return False, f"falha ao alcancar o objeto: {msg}"

        object_pose = Pose(position=Point(x=x, y=y, z=z))
        ok, msg = self._add_grasp_object(object_pose, radius, height, frame_id)
        if not ok:
            return False, f"falha ao adicionar o objeto na cena: {msg}"

        ok, msg = self._attach_grasp_object()
        if not ok:
            return False, f"falha ao anexar o objeto na gripper: {msg}"

        ok, msg = self.move_to_named_state("close_ibu")
        if not ok:
            return False, f"falha ao fechar a gripper: {msg}"
        
        ok, msg = self.move_to_named_state("cad_reference")
        if not ok:
            return False, f"falha ao mover para cad_reference: {msg}"
        return True, "ok"
    

    def place(self, x: float, y: float, z: float, frame_id: str = DEFAULT_FRAME) -> tuple[bool, str]:
        ok, msg = self.move_to_pose(x, y, z, frame_id)
        if not ok:
            return False, f"falha ao alcancar o destino: {msg}"

        ok, msg = self._detach_and_remove_grasp_object()
        if not ok:
            return False, f"falha ao soltar o objeto: {msg}"

        ok, msg = self.move_to_named_state("open")
        if not ok:
            return False, f"falha ao abrir a gripper: {msg}"

        return True, "ok"

    # ------------------------------------------------------------------
    # Handlers de servico
    # ------------------------------------------------------------------
    def _handle_move_to_named_state(self, request, response):
        response.success, response.message = self.move_to_named_state(
            request.state_name
        )
        return response

    def _handle_move_to_pose(self, request, response):
        response.success, response.message = self.move_to_pose(
            request.x, request.y, request.z, request.frame_id
        )
        return response

    def _handle_pick(self, request, response):
        response.success, response.message = self.pick(
            request.x, request.y, request.z, request.radius, request.height
        )
        return response

    def _handle_place(self, request, response):
        response.success, response.message = self.place(
            request.x, request.y, request.z
        )
        return response


def main():
    rclpy.init()
    node = RavManipulator()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
