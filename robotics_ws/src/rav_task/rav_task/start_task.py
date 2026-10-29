import asyncio
import json
import math
import threading
import time

import rclpy
from geometry_msgs.msg import PoseStamped
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
from rcl_interfaces.srv import SetParameters
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.time import Time
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
    "pomada": 0.04,
    "aciclovir": 0.03,
}
DEFAULT_PLACE_Z = 0.05

CAM_POSE_STATE = "cam_pose"

TARGET_POSE_TOPIC = "/rav_vision/target_pose"


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

        # Alinhamento da base (Temi) antes do pick: o braco so alcanca o
        # plano x~0 (3 juntas coplanares, a ponte trava x=0), entao se a
        # visao ve o objeto fora de |x| <= align_tolerance_m a base gira
        # ate ele entrar nessa faixa.
        self.declare_parameter("align_tolerance_m", 0.02)
        self.declare_parameter("align_max_iterations", 6)
        # Distancia (m) do eixo de giro do Temi ate a origem de
        # manipulator_world, ao longo da direcao de alcance do braco (-y).
        # O angulo de giro e atan2(x, |y| + offset): sem esse offset o
        # giro sai grande demais pra objetos perto. Medir com regua.
        self.declare_parameter("base_axis_offset_m", 0.0)
        # +1 se turnBy positivo (anti-horario, visto de cima) leva um
        # objeto em x>0 pra x=0; -1 se for o contrario. Conferir no 1o teste.
        self.declare_parameter("turn_sign", 1)
        self.declare_parameter("min_turn_deg", 2)
        self.declare_parameter("max_turn_deg", 45)
        self.declare_parameter("turn_timeout_s", 15.0)
        # Depois do giro: tempo pra camera/visao estabilizar e prazo pra
        # chegar uma deteccao nova (YOLO na CPU leva ~2s por frame).
        self.declare_parameter("post_turn_settle_s", 1.0)
        self.declare_parameter("detection_timeout_s", 8.0)

        self.align_tolerance_m = float(self.get_parameter("align_tolerance_m").value)
        self.align_max_iterations = int(self.get_parameter("align_max_iterations").value)
        self.base_axis_offset_m = float(self.get_parameter("base_axis_offset_m").value)
        self.turn_sign = 1 if int(self.get_parameter("turn_sign").value) >= 0 else -1
        self.min_turn_deg = int(self.get_parameter("min_turn_deg").value)
        self.max_turn_deg = int(self.get_parameter("max_turn_deg").value)
        self.turn_timeout_s = float(self.get_parameter("turn_timeout_s").value)
        self.post_turn_settle_s = float(self.get_parameter("post_turn_settle_s").value)
        self.detection_timeout_s = float(self.get_parameter("detection_timeout_s").value)

        cb_group = ReentrantCallbackGroup()

        # Ultima deteccao da visao (x, y, z, stamp em segundos).
        self._target_lock = threading.Lock()
        self._latest_target = None
        self.create_subscription(
            PoseStamped,
            TARGET_POSE_TOPIC,
            self._on_target_pose,
            10,
            callback_group=cb_group,
        )

        # Conexao WebSocket ativa com o RavPlatform + espera do giro.
        self._ws = None
        self._ws_loop = None
        self._giro_evento = threading.Event()
        self._giro_resultado = (False, "")

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
    # Alinhamento da base (giro do Temi) pela coordenada x da visão.
    # ------------------------------------------------------------------
    def _on_target_pose(self, msg: PoseStamped):
        stamp = Time.from_msg(msg.header.stamp).nanoseconds / 1e9
        with self._target_lock:
            self._latest_target = (
                msg.pose.position.x, msg.pose.position.y, msg.pose.position.z, stamp
            )

    def _esperar_deteccao(self, depois_de: float):
        """Espera uma detecção cuja imagem foi capturada depois de
        'depois_de' (relógio ROS, s) -- garante que é do frame pós-giro."""
        prazo = time.monotonic() + self.detection_timeout_s
        while time.monotonic() < prazo:
            with self._target_lock:
                alvo = self._latest_target
            if alvo is not None and alvo[3] > depois_de:
                return alvo
            time.sleep(0.1)
        return None

    def _enviar_ws(self, payload: dict):
        if self._ws is None or self._ws_loop is None:
            return False
        futuro = asyncio.run_coroutine_threadsafe(
            self._ws.send(json.dumps(payload)), self._ws_loop
        )
        try:
            futuro.result(timeout=5.0)
            return True
        except Exception as exc:
            self.get_logger().error(f"falha ao enviar pelo WebSocket: {exc}")
            return False

    def _girar_base(self, graus: int):
        """Pede pro RavPlatform girar o Temi (turnBy) e espera a confirmação."""
        self._giro_evento.clear()
        if not self._enviar_ws({"tipo": "girar_base", "graus": graus}):
            return False, "RavPlatform não conectado para girar a base"
        if not self._giro_evento.wait(timeout=self.turn_timeout_s):
            return False, f"timeout ({self.turn_timeout_s}s) esperando giro_concluido"
        return self._giro_resultado

    def alinhar_base(self):
        """Gira a base até |x| da detecção ficar dentro da tolerância."""
        agora = self.get_clock().now().nanoseconds / 1e9
        for tentativa in range(1, self.align_max_iterations + 1):
            alvo = self._esperar_deteccao(depois_de=agora)
            if alvo is None:
                return False, (
                    f"sem detecção nova em {self.detection_timeout_s}s "
                    "para alinhar a base"
                )
            x, y, _, _ = alvo

            if abs(x) <= self.align_tolerance_m:
                self.get_logger().info(
                    f"base alinhada: x={x:+.3f} (tolerância "
                    f"±{self.align_tolerance_m:.3f}) após {tentativa - 1} giro(s)"
                )
                return True, "ok"

            # Ângulo do objeto visto do eixo de giro do Temi.
            alcance = abs(y) + self.base_axis_offset_m
            angulo = self.turn_sign * math.degrees(math.atan2(x, alcance))
            # Limita entre min e max mantendo o sinal: giros muito pequenos
            # o Temi ignora, e um giro grande demais (deteccao ruim) e perigoso.
            modulo = min(self.max_turn_deg, max(self.min_turn_deg, round(abs(angulo))))
            graus = int(math.copysign(modulo, angulo))

            self.get_logger().info(
                f"alinhamento {tentativa}/{self.align_max_iterations}: "
                f"x={x:+.3f} y={y:+.3f} -> girando base {graus:+d} graus"
            )
            ok, msg = self._girar_base(graus)
            if not ok:
                return False, f"giro da base falhou: {msg}"

            time.sleep(self.post_turn_settle_s)
            agora = self.get_clock().now().nanoseconds / 1e9

        return False, (
            f"objeto fora de ±{self.align_tolerance_m:.3f} m depois de "
            f"{self.align_max_iterations} giros"
        )

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

            ok, msg = self.alinhar_base()
            if not ok:
                return False, f"falha ao alinhar a base: {msg}"

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
    async def _rodar_e_responder(self, websocket, funcao, tipo_resposta, depois=None):
        # Roda em tarefa separada (nao com await direto no loop de leitura):
        # durante o pick o alinhamento pede giros ao Temi e precisa receber
        # o "giro_concluido" enquanto executar_pick ainda nao terminou.
        loop = asyncio.get_running_loop()
        success, mensagem = await loop.run_in_executor(None, funcao)
        await websocket.send(json.dumps({
            "tipo": tipo_resposta,
            "success": success,
            "mensagem": mensagem,
        }))
        if depois is not None:
            depois()

    async def handle_connection(self, websocket):
        peer = websocket.remote_address
        self.get_logger().info(f"RavPlatform conectado: {peer}")
        self._ws = websocket
        self._ws_loop = asyncio.get_running_loop()
        tarefas = set()

        def disparar(coro):
            tarefa = asyncio.create_task(coro)
            tarefas.add(tarefa)
            tarefa.add_done_callback(tarefas.discard)

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
                    disparar(self._rodar_e_responder(
                        websocket, self.executar_pick, "pick_concluido"
                    ))

                elif tipo == "chegou_place":
                    self.get_logger().info("chegou_place -- iniciando place")

                    def limpar_pedido():
                        self._classe_yolo = None

                    disparar(self._rodar_e_responder(
                        websocket, self.executar_place, "place_concluido",
                        depois=limpar_pedido,
                    ))

                elif tipo == "giro_concluido":
                    self._giro_resultado = (
                        bool(msg.get("success")), str(msg.get("mensagem", ""))
                    )
                    self._giro_evento.set()

                else:
                    self.get_logger().warn(f"tipo desconhecido: {tipo!r}")
        finally:
            if self._ws is websocket:
                self._ws = None
                self._ws_loop = None
            # Destrava um alinhamento que estava esperando giro dessa conexão.
            self._giro_resultado = (False, "RavPlatform desconectou durante o giro")
            self._giro_evento.set()
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
