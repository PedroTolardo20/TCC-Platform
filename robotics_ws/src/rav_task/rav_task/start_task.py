import asyncio
import json
import threading
import time

import rclpy
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
from rcl_interfaces.srv import SetParameters
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from std_srvs.srv import Trigger

import websockets

from rav_manipulator_moveit_config.srv import MoveToNamedState, Place

VISION_NODE = "rav_vision_3d"

# Altura de entrega por classe (frame manipulator_world, mesmo do place()).
# Local (x, y) e fixo -- so o z muda de acordo com a altura da caixa/frasco
# de cada produto. Valores abaixo sao placeholder: precisa calibrar contra
# o ponto de entrega real antes de rodar em produção.
PLACE_Z_BY_CLASS = {
    "ibuprotrat": 0.05,
    "maxalgina": 0.04,
    "aciclovir": 0.03,
}
DEFAULT_PLACE_Z = 0.05

CAM_POSE_STATE = "cam_pose"


class StartTaskNode(Node):
    """Orquestra o pick-and-place: recebe do RavPlatform (via WebSocket)
    os avisos de chegada e aciona, nessa ordem, os serviços que já existem
    em rav_vision/rav_manipulator_moveit_config (vision_pick_bridge e
    manipulator_node). Não sobe nenhum processo -- assume que start_devices
    já deixou tudo de pé.
    """

    def __init__(self):
        super().__init__("start_task")

        self.declare_parameter("port", 8766)
        self.declare_parameter("place_x", 0.0)
        self.declare_parameter("place_y", 0.0)
        self.declare_parameter("cam_pose_settle_s", 1.5)

        self.port = int(self.get_parameter("port").value)
        self.place_x = float(self.get_parameter("place_x").value)
        self.place_y = float(self.get_parameter("place_y").value)
        self.cam_pose_settle_s = float(
            self.get_parameter("cam_pose_settle_s").value
        )

        cb_group = ReentrantCallbackGroup()

        self._move_client = self.create_client(
            MoveToNamedState, "move_to_named_state", callback_group=cb_group
        )
        self._pick_client = self.create_client(
            Trigger, "pick_from_vision", callback_group=cb_group
        )
        self._place_client = self.create_client(
            Place, "place", callback_group=cb_group
        )
        self._vision_param_client = self.create_client(
            SetParameters, f"/{VISION_NODE}/set_parameters", callback_group=cb_group
        )

        # Pedido em andamento (um robô, um pedido por vez).
        self._classe_yolo = None

        self.get_logger().info(
            f"start_task pronto. Aguardando conexão do RavPlatform em "
            f"0.0.0.0:{self.port}. place=({self.place_x:.3f}, "
            f"{self.place_y:.3f}, z por classe)."
        )

    # ------------------------------------------------------------------
    # Chamadas de serviço (bloqueantes -- chamadas de fora da thread do
    # executor rclpy, via loop.run_in_executor no lado asyncio).
    # ------------------------------------------------------------------
    def _wait_for_future(self, client, future, timeout_s: float):
        done = threading.Event()
        future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout=timeout_s):
            return None, f"timeout esperando o serviço '{client.srv_name}'"
        return future.result(), None

    def _call_service(self, client, request, timeout_s: float):
        if not client.wait_for_service(timeout_sec=5.0):
            return False, f"serviço '{client.srv_name}' não respondeu"
        result, erro = self._wait_for_future(client, client.call_async(request), timeout_s)
        if erro:
            return False, erro
        return result.success, result.message

    def _move_to_named_state(self, state_name: str):
        return self._call_service(
            self._move_client, MoveToNamedState.Request(state_name=state_name), 30.0
        )

    def _pick_from_vision(self):
        return self._call_service(self._pick_client, Trigger.Request(), 60.0)

    def _place(self, x: float, y: float, z: float):
        return self._call_service(
            self._place_client, Place.Request(x=x, y=y, z=z), 60.0
        )

    def _set_target_class(self, classe: str):
        """Ajusta target_class do rav_vision_3d em tempo real, pra ele só
        publicar deteccoes da classe pedida (evita pegar o objeto errado
        quando tem mais de um remedio visivel na prateleira)."""
        client = self._vision_param_client
        if not client.wait_for_service(timeout_sec=5.0):
            return False, f"serviço '{client.srv_name}' não respondeu"

        request = SetParameters.Request(parameters=[
            Parameter(
                name="target_class",
                value=ParameterValue(
                    type=ParameterType.PARAMETER_STRING, string_value=classe
                ),
            )
        ])
        result, erro = self._wait_for_future(client, client.call_async(request), 5.0)
        if erro:
            return False, erro

        if not result.results or not result.results[0].successful:
            razao = result.results[0].reason if result.results else "sem resposta"
            return False, f"rav_vision_3d recusou target_class='{classe}': {razao}"
        return True, "ok"

    # ------------------------------------------------------------------
    # Sequências completas, chamadas do handler WebSocket.
    # ------------------------------------------------------------------
    def executar_pick(self):
        classe = self._classe_yolo
        if not classe:
            return False, "classeYolo não definida para este pedido"

        ok, msg = self._set_target_class(classe)
        if not ok:
            return False, f"falha ao ajustar target_class: {msg}"

        try:
            ok, msg = self._move_to_named_state(CAM_POSE_STATE)
            if not ok:
                return False, f"falha ao mover para {CAM_POSE_STATE}: {msg}"

            # Deixa a visão publicar algumas detecções estáveis, já
            # filtradas pra 'classe', com o braço parado em cam_pose.
            time.sleep(self.cam_pose_settle_s)

            ok, msg = self._pick_from_vision()
            if not ok:
                return False, f"pick_from_vision falhou: {msg}"
            return True, msg
        finally:
            # Sempre libera o filtro no final (sucesso ou falha), pra não
            # deixar o rav_vision_3d preso numa classe de um pedido antigo.
            self._set_target_class("")

    def executar_place(self):
        z = PLACE_Z_BY_CLASS.get(self._classe_yolo, DEFAULT_PLACE_Z)
        if self._classe_yolo not in PLACE_Z_BY_CLASS:
            self.get_logger().warn(
                f"classeYolo '{self._classe_yolo}' sem z calibrado, usando "
                f"default {DEFAULT_PLACE_Z}"
            )
        ok, msg = self._place(self.place_x, self.place_y, z)
        if not ok:
            return False, f"place falhou: {msg}"
        return True, msg

    # ------------------------------------------------------------------
    # WebSocket
    # ------------------------------------------------------------------
    async def handle_connection(self, websocket):
        peer = websocket.remote_address
        self.get_logger().info(f"RavPlatform conectado: {peer}")
        loop = asyncio.get_running_loop()

        try:
            async for raw in websocket:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    self.get_logger().warn(f"mensagem inválida ignorada: {raw!r}")
                    continue

                tipo = msg.get("tipo")

                if tipo == "pedido":
                    self._classe_yolo = msg.get("classeYolo")
                    self.get_logger().info(
                        f"pedido recebido: classeYolo={self._classe_yolo}"
                    )

                elif tipo == "chegou_pickup":
                    self.get_logger().info("chegou_pickup -- iniciando pick")
                    success, mensagem = await loop.run_in_executor(
                        None, self.executar_pick
                    )
                    await websocket.send(json.dumps({
                        "tipo": "pick_concluido",
                        "success": success,
                        "mensagem": mensagem,
                    }))

                elif tipo == "chegou_place":
                    self.get_logger().info("chegou_place -- iniciando place")
                    success, mensagem = await loop.run_in_executor(
                        None, self.executar_place
                    )
                    await websocket.send(json.dumps({
                        "tipo": "place_concluido",
                        "success": success,
                        "mensagem": mensagem,
                    }))
                    self._classe_yolo = None

                else:
                    self.get_logger().warn(f"tipo desconhecido: {tipo!r}")
        finally:
            self.get_logger().info(f"RavPlatform desconectado: {peer}")

    async def serve_forever(self):
        async with websockets.serve(self.handle_connection, "0.0.0.0", self.port):
            await asyncio.Future()


def main():
    rclpy.init()
    node = StartTaskNode()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)

    spin_thread = threading.Thread(target=executor.spin, daemon=True)
    spin_thread.start()

    try:
        asyncio.run(node.serve_forever())
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
