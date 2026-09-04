import threading

import rclpy
from geometry_msgs.msg import PoseStamped
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.time import Time
from std_srvs.srv import Trigger

from rav_manipulator_moveit_config.srv import Pick

TARGET_POSE_TOPIC = "/rav_vision/target_pose"
EXPECTED_FRAME = "manipulator_world"

# Bloco alcancavel remapeado empiricamente via /compute_ik (grade varrida
# em 2026-08-31, com a camera ja montada na gripper): fora dessa faixa o
# IK fica instavel/patchy, entao a ponte recusa a deteccao em vez de
# arriscar mandar o braco pra uma pose que pode falhar ou colidir.
Y_MIN, Y_MAX = -0.70, -0.3
Z_MIN, Z_MAX = -0.40, 0.40
X_TOLERANCE = 0.1

MAX_TARGET_AGE_S = 2.0


class VisionPickBridge(Node):
    """Junta deteccao de visao + gatilho manual antes de mover o braco.

    A visao so alimenta a ultima posicao valida (dentro do workspace
    seguro); o pick de verdade so acontece quando 'pick_from_vision' e
    chamado, e usa a deteccao mais recente se ainda estiver fresca.
    """

    def __init__(self):
        super().__init__("vision_pick_bridge")

        self.declare_parameter("radius", 0.02)
        self.declare_parameter("height", 0.08)
        self.radius = float(self.get_parameter("radius").value)
        self.height = float(self.get_parameter("height").value)

        cb_group = ReentrantCallbackGroup()

        self._latest_target = None  # (x, y, z, stamp)

        self.create_subscription(
            PoseStamped,
            TARGET_POSE_TOPIC,
            self._on_target_pose,
            10,
            callback_group=cb_group,
        )

        self._pick_client = self.create_client(
            Pick, "pick", callback_group=cb_group
        )

        self.create_service(
            Trigger,
            "pick_from_vision",
            self._handle_pick_from_vision,
            callback_group=cb_group,
        )

        self.get_logger().info(
            "vision_pick_bridge pronto. Ouvindo "
            f"{TARGET_POSE_TOPIC} (frame esperado: '{EXPECTED_FRAME}'). "
            "Chame o servico 'pick_from_vision' pra executar o pick."
        )

    def _on_target_pose(self, msg: PoseStamped):
        if msg.header.frame_id != EXPECTED_FRAME:
            self.get_logger().warn(
                f"target_pose chegou no frame '{msg.header.frame_id}', "
                f"esperado '{EXPECTED_FRAME}' -- rode o realtime_3d_inference "
                f"com -p target_frame:={EXPECTED_FRAME}. Ignorando."
            )
            return

        x = msg.pose.position.x
        y = msg.pose.position.y - 0.02
        z = msg.pose.position.z + 0.09

        # if not self._is_within_safe_workspace(x, y, z):
        #     self.get_logger().warn(
        #         f"Deteccao fora do workspace seguro "
        #         f"(x={x:.3f} y={y:.3f} z={z:.3f}) -- ignorada."
        #     )
        #     return

        # x sempre ~0 nesse braco (3 juntas coplanares) -- trava em 0.0
        # em vez de repassar o ruido de profundidade da visao.
        self._latest_target = (0.0, y, z, msg.header.stamp)

    @staticmethod
    def _is_within_safe_workspace(x: float, y: float, z: float) -> bool:
        return (
            abs(x) <= X_TOLERANCE
            and Y_MIN <= y <= Y_MAX
            and Z_MIN <= z <= Z_MAX
        )

    def _handle_pick_from_vision(self, request, response):
        if self._latest_target is None:
            response.success = False
            response.message = (
                "nenhuma deteccao valida recebida ainda dentro do "
                "workspace seguro"
            )
            return response

        x, y, z, stamp = self._latest_target
        age_s = (self.get_clock().now() - Time.from_msg(stamp)).nanoseconds / 1e9
        if age_s > MAX_TARGET_AGE_S:
            response.success = False
            response.message = (
                f"ultima deteccao valida tem {age_s:.1f}s (limite "
                f"{MAX_TARGET_AGE_S}s) -- aponte a camera pro objeto de "
                "novo antes de chamar"
            )
            return response

        if not self._pick_client.wait_for_service(timeout_sec=5.0):
            response.success = False
            response.message = "servico 'pick' nao respondeu"
            return response

        pick_request = Pick.Request(
            x=x, y=y, z=z, radius=self.radius, height=self.height
        )

        done = threading.Event()
        future = self._pick_client.call_async(pick_request)
        future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout=30.0):
            response.success = False
            response.message = "timeout esperando o servico 'pick'"
            return response

        result = future.result()
        response.success = result.success
        response.message = f"pick em ({x:.3f}, {y:.3f}, {z:.3f}): {result.message}"
        return response


def main():
    rclpy.init()
    node = VisionPickBridge()
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
