"""Teste isolado do alinhamento da base com o objeto (nada de pick).

Usa a orientação ABSOLUTA do Temi no mapa (yaw) em vez de giros relativos,
pra erro de ângulo não acumular:
  1. Temi vai até 'preprateleira' (braço em home)
  2. braço -> cam_pose: mede o objeto (x lateral, distância) e o yaw atual
  3. com o erro de ângulo alfa = yaw - yaw_prateleira, calcula quanto andar
     AO LONGO da prateleira: s = d*sin(alfa) + x*cos(alfa)
  4. braço -> home; gira até yaw_prateleira ± 90° (absoluto, malha fechada),
     anda |s| mantendo esse rumo, gira até yaw_prateleira
  5. braço -> cam_pose e confere; no máximo 'max_correcoes' correções extras
  6. alinhado: braço -> home e anda 'avanco_final_m' (20 cm) pra frente,
     mantendo o rumo de frente pra prateleira; depois braço -> cam_pose
  7. pick (/pick_from_vision) -> braço em ready -> base vai até o local
     'place' (com o braço em ready) -> braço na pose 'place' -> abre a
     garra (e tira o objeto da cena do MoveIt) -> cad_reference -> home
     -> base volta pra 'home base'

yaw_prateleira = yaw do Temi exatamente de frente pra prateleira, medido
uma vez POR LOCAL com:
  ros2 run rav_task teste_alinhamento --ros-args -p modo:=calibrar_yaw -p local:=<local>
(salvo em ~/.ros/rav_alinhamento.json e lido daí nas próximas execuções).

A sequência fica em executar_tarefa(), usada também pelo orquestrador
(rav_task/orquestrador.py), que espera os pedidos do RavTotem.

Fala com o app do Temi (RavWebSocketServer, porta 8765) mandando mensagens
{"tipo": "comando", ...} e esperando o "comando_concluido" de cada uma.
Pressupõe o braço, a câmera e o realtime_3d_inference já rodando.
"""

import asyncio
import json
import math
import os
import statistics
import threading
import time

import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from moveit_msgs.msg import (
    AttachedCollisionObject,
    CollisionObject,
    PlanningScene,
    PlanningSceneWorld,
    RobotState,
)
from moveit_msgs.srv import ApplyPlanningScene
from std_msgs.msg import String
from std_srvs.srv import Trigger
from rcl_interfaces.msg import Parameter, ParameterType, ParameterValue
from rcl_interfaces.srv import SetParameters

import websockets

from rav_manipulator_moveit_config.srv import MoveToNamedState

DETECTIONS_TOPIC = "/rav_vision/detections_3d"
VISION_NODE = "rav_vision_3d"
MANIPULATOR_NODE = "rav_manipulator"
ARQUIVO_CALIBRACAO = os.path.expanduser("~/.ros/rav_alinhamento.json")
# Poses nomeadas do grupo rav_gripper: não mudam a pose do braço.
POSES_GARRA = ("open", "closed", "close_ibu", "close_pom", "close_aci")
# Mesmos nomes do manipulator_node.py (objeto anexado pelo pick).
GRASP_OBJECT_ID = "grasped_object"
TCP_LINK = "gripper_tcp"


def normalizar(rad: float) -> float:
    """Ângulo em (-pi, pi]."""
    return math.atan2(math.sin(rad), math.cos(rad))


def carregar_yaw_calibrado(local: str) -> float:
    """yaw_prateleira salvo pra 'local' (NaN se não calibrado).

    Formato: {"locais": {local: {"yaw": ...}}}; o campo antigo
    "yaw_prateleira" (antes de ter um por local) vale como reserva.
    """
    if not os.path.exists(ARQUIVO_CALIBRACAO):
        return float("nan")
    with open(ARQUIVO_CALIBRACAO) as f:
        dados = json.load(f)
    if local in dados.get("locais", {}):
        return float(dados["locais"][local]["yaw"])
    if "yaw_prateleira" in dados:
        return float(dados["yaw_prateleira"])
    return float("nan")


class TesteAlinhamento(Node):

    def __init__(self, nome: str = "teste_alinhamento"):
        super().__init__(nome)

        # "alinhar" (padrão) ou "calibrar_yaw" (só lê e salva o yaw atual
        # como yaw_prateleira -- robô posicionado de frente pra prateleira).
        self.declare_parameter("modo", "alinhar")
        self.declare_parameter("temi_url", "ws://172.20.10.3:8765")
        self.declare_parameter("local", "preprateleira")
        self.declare_parameter("classe", "ibuprotrat")
        # Pose do braço pra olhar o objeto (cada altura de prateleira pode
        # ter a sua; o orquestrador troca por produto).
        self.declare_parameter("cam_pose", "cam_pose")
        # +1: objeto em x>0 fica à esquerda do Temi -> gira +90 (anti-horário).
        # Se o Temi virar pro lado errado no 1o teste, usar -1.
        self.declare_parameter("lado_sign", 1)
        self.declare_parameter("tolerancia_m", 0.02)
        self.declare_parameter("amostras", 3)
        # Espera depois de chegar na cam_pose antes de aceitar detecções: a
        # visão (YOLO na CPU) processa com ~2 s de atraso e a TF dela atrasa;
        # com 1.5 s veio uma medição feita com a TF ainda do braço em home.
        self.declare_parameter("cam_pose_settle_s", 2.5)
        # Faixa de y do objeto (manipulator_world, m) aceita SÓ na conferência
        # antes do pick (depois do avanço, objeto em ~-0.67). No alinhamento
        # não filtra: antes de avançar o objeto está mais longe (~-0.83, às
        # vezes além de -1.0) e o filtro impedia de seguir com o robô já
        # alinhado -- o avanço é que traz o y pra dentro da faixa.
        self.declare_parameter("y_min_objeto", -1.0)
        self.declare_parameter("y_max_objeto", -0.45)
        # Com a CPU cheia a visão chegou a ~3.5 s por frame: 15 s davam só 2
        # detecções novas e o pick era abortado com o objeto à vista.
        self.declare_parameter("deteccao_timeout_s", 30.0)
        # Depois do deslocamento principal, quantas correções extras no
        # máximo (a ideia é acertar de primeira; isso é só rede de segurança).
        # (era 1: deslocamentos curtos andam menos que o pedido e a tarefa
        # desistia a ~3 cm do alvo, voltando pra base.)
        self.declare_parameter("max_correcoes", 3)
        # Medição sem detecção (objeto sumiu da câmera depois de girar/andar):
        # em vez de desistir e voltar pra base, anda 'reposicionar_m' pra
        # frente (de frente pra prateleira) só pra mexer a câmera e tenta
        # ver de novo, até 'reposicionar_tentativas' vezes.
        self.declare_parameter("reposicionar_m", 0.02)
        self.declare_parameter("reposicionar_tentativas", 2)
        # Yaw (rad, mapa do Temi) de frente pra prateleira. NaN = lê do
        # ARQUIVO_CALIBRACAO (gravado pelo modo calibrar_yaw).
        self.declare_parameter("yaw_prateleira", float("nan"))
        self.declare_parameter("tolerancia_yaw_graus", 1.5)
        # turnBy de 1-2° é impreciso: depois das tentativas, o app aceita o
        # giro se o erro ficar até isso (a medição seguinte compensa).
        self.declare_parameter("aceitar_giro_graus", 3.0)
        # Depois de alinhado, quanto andar pra frente (em direção à
        # prateleira). 0 = não avança.
        self.declare_parameter("avanco_final_m", 0.20)
        # Segurança de navegação só durante o avanço: em HIGH (o padrão do
        # robô) o Temi se recusa a andar em direção à prateleira. Volta ao
        # nível original assim que ele para. Vazio = não mexe.
        self.declare_parameter("avanco_seguranca", "DEFAULT")
        # Distância mínima a obstáculos (unidade do SDK do Temi; o robô está
        # em 10) só durante o avanço, restaurada depois. -1 = não mexe.
        # O Temi não aceitou mudar (pede permissão de configurações) -> -1.
        self.declare_parameter("avanco_obstaculo_cm", -1)
        self.declare_parameter("avanco_velocidade", 0.15)
        # Quanto antes do alvo parar (o Temi ainda desliza um pouco).
        self.declare_parameter("avanco_antecipacao_m", 0.01)
        self.declare_parameter("avanco_timeout_s", 40.0)
        # Pose da garra que fecha no objeto (por produto no produtos.yaml).
        self.declare_parameter("garra_fechar", "close_ibu")
        # > 0: depois de fechar a garra o braço fica onde pegou, a base
        # recua isso (ré, mesma velocidade/segurança do avanço) e só então
        # o braço vai pra ready -- prateleira de baixo, onde ir direto pra
        # cad_reference bateria na prateleira de cima. 0 = pick normal.
        self.declare_parameter("recuar_apos_pick_m", 0.0)
        # Depois de alinhado: pick + levar até o local de entrega + voltar
        # pra base. False = para no alinhamento (só teste).
        self.declare_parameter("fazer_pick_place", True)
        self.declare_parameter("local_place", "place")
        self.declare_parameter("local_base", "home base")
        # Distância do centro do Temi até a base do braço (origem de
        # manipulator_world), na direção da frente. Medido: 5 cm.
        self.declare_parameter("base_braco_offset_m", 0.05)
        # Correção de rumo enquanto anda: comando angular do skidJoy por rad
        # de erro. Se o app abortar com "desviou do rumo", inverter o sinal.
        self.declare_parameter("ganho_rumo", 1.0)

        # Calibração do "andar": o Temi passa do ponto por (velocidade x
        # atraso) -- posição chega atrasada + desliza depois do stop -- então
        # o app para 'antecipacao' antes do alvo, com
        #   antecipacao = andar_ultrapassagem_por_vel * velocidade.
        # Medido em 2026-10-05: pedido 0.291 m a velocidade 0.2 parou 0.27 m
        # além do ponto certo (o app parava em ~0.286) -> 0.275 / 0.2 = 1.375.
        # Recalibrar: novo = antigo + (passou_do_ponto_m / velocidade usada);
        # se ficar curto, o passou_do_ponto é negativo.
        self.declare_parameter("andar_ultrapassagem_por_vel", 1.375)
        self.declare_parameter("andar_velocidade_max", 0.2)
        # Abaixo disso o skidJoy pode nem tirar o Temi do lugar.
        self.declare_parameter("andar_velocidade_min", 0.08)
        # Distâncias de até andar_max_por_tempo_m andam por tempo, na
        # velocidade mínima:
        #   duração = metros / (vel_min * vel_real) + tempo_morto
        # vel_real = m/s reais por unidade de skidJoy; tempo_morto = o Temi
        # leva um tempo acelerando antes de andar de fato. Ajuste linear de
        # 9 andadas medidas pela visão (2026-10-22 e 10-28, 2.2-4.4 s,
        # 6-18 cm): 0.0531 m/s (vel_real 0.66) e 1.04 s perdidos, resíduo
        # de 0.8 cm (desvio padrão), dentro da tolerância de 2 cm.
        # NÃO usar o "final X m" do Temi pra isso: em distância curta a
        # odometria dele nem se mexe.
        self.declare_parameter("andar_vel_real", 0.66)
        self.declare_parameter("andar_tempo_morto_s", 1.04)
        # Pela odometria (antecipação) o Temi parava no meio: pedidos de
        # 17-23 cm andaram 4-13 cm (2026-10-22/28), aí precisava de um 2º
        # alinhamento. Por tempo acertou todas -> odometria só acima disso.
        self.declare_parameter("andar_max_por_tempo_m", 0.40)

        p = lambda nome: self.get_parameter(nome).value  # noqa: E731
        self.temi_url = str(p("temi_url"))
        self.local = str(p("local"))
        self.classe = str(p("classe"))
        self.cam_pose = str(p("cam_pose"))
        self.lado_sign = 1 if int(p("lado_sign")) >= 0 else -1
        self.tolerancia_m = float(p("tolerancia_m"))
        self.amostras = int(p("amostras"))
        self.cam_pose_settle_s = float(p("cam_pose_settle_s"))
        self.y_min_objeto = float(p("y_min_objeto"))
        self.y_max_objeto = float(p("y_max_objeto"))
        self.deteccao_timeout_s = float(p("deteccao_timeout_s"))
        self.modo = str(p("modo"))
        self.max_correcoes = int(p("max_correcoes"))
        self.reposicionar_m = float(p("reposicionar_m"))
        self.reposicionar_tentativas = int(p("reposicionar_tentativas"))
        self.yaw_prateleira = float(p("yaw_prateleira"))
        self.tolerancia_yaw = math.radians(float(p("tolerancia_yaw_graus")))
        self.base_braco_offset_m = float(p("base_braco_offset_m"))
        self.ganho_rumo = float(p("ganho_rumo"))
        self.aceitar_giro_graus = float(p("aceitar_giro_graus"))
        self.avanco_final_m = float(p("avanco_final_m"))
        self.avanco_seguranca = str(p("avanco_seguranca"))
        self.avanco_obstaculo_cm = int(p("avanco_obstaculo_cm"))
        self.avanco_velocidade = float(p("avanco_velocidade"))
        self.avanco_antecipacao_m = float(p("avanco_antecipacao_m"))
        self.avanco_timeout_s = float(p("avanco_timeout_s"))
        self.garra_fechar = str(p("garra_fechar"))
        self.recuar_apos_pick_m = float(p("recuar_apos_pick_m"))
        self.fazer_pick_place = bool(p("fazer_pick_place"))
        self.local_place = str(p("local_place"))
        self.local_base = str(p("local_base"))
        # yaw_prateleira explícito (parâmetro) vale pra qualquer local; NaN =
        # lê o calibrado do local em cada tarefa (carregar_yaw_calibrado).
        self.andar_k = float(p("andar_ultrapassagem_por_vel"))
        self.andar_vel_max = float(p("andar_velocidade_max"))
        self.andar_vel_min = float(p("andar_velocidade_min"))
        self.andar_vel_real = float(p("andar_vel_real"))
        self.andar_tempo_morto_s = float(p("andar_tempo_morto_s"))
        self.andar_max_por_tempo_m = float(p("andar_max_por_tempo_m"))

        # Última pose nomeada confirmada pelo move_group (None = desconhecida).
        # A base só anda/gira com isso em "home" -- ver comando_temi.
        self.braco_estado = None

        cb_group = ReentrantCallbackGroup()
        self._move_client = self.create_client(
            MoveToNamedState, "move_to_named_state", callback_group=cb_group
        )
        self._pick_client = self.create_client(
            Trigger, "pick_from_vision", callback_group=cb_group
        )
        self._scene_client = self.create_client(
            ApplyPlanningScene, "apply_planning_scene", callback_group=cb_group
        )
        self._vision_param_client = self.create_client(
            SetParameters, f"/{VISION_NODE}/set_parameters", callback_group=cb_group
        )
        self._manip_param_client = self.create_client(
            SetParameters, f"/{MANIPULATOR_NODE}/set_parameters",
            callback_group=cb_group,
        )

        # Lista de (stamp_s, x, y) da classe pedida, já em manipulator_world.
        self._lock = threading.Lock()
        self._xs = []
        self.create_subscription(
            String, DETECTIONS_TOPIC, self._on_detections, 10,
            callback_group=cb_group,
        )

    # ------------------------------------------------------------------
    # Visão
    # ------------------------------------------------------------------
    def _on_detections(self, msg: String):
        dados = json.loads(msg.data)
        stamp = dados["stamp_sec"] + dados["stamp_nanosec"] * 1e-9
        for det in dados["detections"]:
            pos = det.get("position_target_m")
            if det["class_name"] != self.classe or pos is None:
                continue
            with self._lock:
                self._xs.append((stamp, pos["x"], pos["y"]))

    def ler_objeto(self, amostras: int = 0, filtrar_y: bool = False):
        """Mediana de (x, y) de 'amostras' detecções tiradas a partir de agora
        (0 = o parâmetro 'amostras'). filtrar_y: só aceita y dentro de
        [y_min_objeto, y_max_objeto] (conferência antes do pick)."""
        amostras = amostras or self.amostras
        inicio = self.get_clock().now().nanoseconds / 1e9
        prazo = time.monotonic() + self.deteccao_timeout_s
        avisados = set()
        while time.monotonic() < prazo:
            with self._lock:
                novos = [(stamp, x, y) for stamp, x, y in self._xs if stamp >= inicio]
            if filtrar_y:
                for stamp, _, y in novos:
                    fora = not self.y_min_objeto <= y <= self.y_max_objeto
                    if fora and stamp not in avisados:
                        avisados.add(stamp)
                        self.get_logger().warn(
                            f"detecção ignorada pro pick: y={y:+.3f} fora de "
                            f"[{self.y_min_objeto}, {self.y_max_objeto}]"
                        )
                novos = [
                    (stamp, x, y) for stamp, x, y in novos
                    if self.y_min_objeto <= y <= self.y_max_objeto
                ]
            novos = [(x, y) for _, x, y in novos]
            if len(novos) >= amostras:
                novos = novos[:amostras]
                return (
                    statistics.median(x for x, _ in novos),
                    statistics.median(y for _, y in novos),
                )
            time.sleep(0.1)
        return None

    def plano_andar(self, metros: float) -> dict:
        """Velocidade e antecipação do 'andar' pra parar em 'metros'.

        Escolhe a velocidade pra antecipação ser ~metade do trajeto (em
        distância curta, andar rápido faria passar do ponto mesmo parando
        logo no início), limitada entre vel_min e vel_max.
        """
        velocidade = metros / (2.0 * self.andar_k) if self.andar_k > 0 else self.andar_vel_max
        velocidade = min(self.andar_vel_max, max(self.andar_vel_min, velocidade))
        antecipacao = self.andar_k * velocidade

        if metros > self.andar_max_por_tempo_m and antecipacao < 0.7 * metros:
            return {
                "metros": round(metros, 3),
                "velocidade": round(velocidade, 3),
                "antecipacao_m": round(antecipacao, 3),
            }

        # Até andar_max_por_tempo_m (ou curto demais pra parar pela
        # odometria): anda por tempo na velocidade mínima.
        duracao = (
            metros / (self.andar_vel_min * self.andar_vel_real)
            + self.andar_tempo_morto_s
        )
        self.get_logger().info(
            f"andar {metros:.3f} m por tempo: {duracao:.2f}s a velocidade "
            f"{self.andar_vel_min:.2f}"
        )
        return {
            "metros": round(metros, 3),
            "velocidade": round(self.andar_vel_min, 3),
            "duracao_s": round(duracao, 2),
        }

    # ------------------------------------------------------------------
    # Braço
    # ------------------------------------------------------------------
    def mover_braco(self, estado: str):
        # Durante o movimento (ou se falhar) a pose fica desconhecida -- a
        # não ser que seja só a garra abrindo/fechando.
        eh_garra = estado in POSES_GARRA
        braco_antes = self.braco_estado
        if not eh_garra:
            self.braco_estado = None
        if not self._move_client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError("serviço move_to_named_state não respondeu")
        done = threading.Event()
        future = self._move_client.call_async(MoveToNamedState.Request(state_name=estado))
        future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout=30.0):
            raise RuntimeError(f"timeout movendo o braço para '{estado}'")
        resultado = future.result()
        if not resultado.success:
            raise RuntimeError(f"braço não foi para '{estado}': {resultado.message}")
        self.braco_estado = braco_antes if eh_garra else estado
        self.get_logger().info(
            f"garra em '{estado}'" if eh_garra else f"braço em '{estado}'"
        )

    def _chamar(self, client, request, timeout_s: float, nome: str):
        if not client.wait_for_service(timeout_sec=5.0):
            raise RuntimeError(f"serviço '{nome}' não respondeu")
        done = threading.Event()
        future = client.call_async(request)
        future.add_done_callback(lambda _f: done.set())
        if not done.wait(timeout=timeout_s):
            raise RuntimeError(f"timeout esperando '{nome}'")
        return future.result()

    def pick(self):
        """Pick pela visão (vision_pick_bridge -> /pick do manipulator_node).

        Fecha a garra com 'garra_fechar'. Termina em cad_reference ou, com
        recuar_apos_pick_m > 0, parado onde pegou (braco_estado "pick").
        """
        fica_no_objeto = self.recuar_apos_pick_m > 0
        pose_final = "" if fica_no_objeto else "cad_reference"
        # Tem que valer: com o parâmetro velho o braço iria pra
        # cad_reference de dentro da prateleira de baixo.
        pedido = SetParameters.Request(parameters=[
            Parameter(name="pick_garra_fechar", value=ParameterValue(
                type=ParameterType.PARAMETER_STRING,
                string_value=self.garra_fechar)),
            Parameter(name="pick_pose_final", value=ParameterValue(
                type=ParameterType.PARAMETER_STRING, string_value=pose_final)),
        ])
        resultado = self._chamar(
            self._manip_param_client, pedido, 5.0,
            f"{MANIPULATOR_NODE}/set_parameters",
        )
        if not all(r.successful for r in resultado.results):
            raise RuntimeError("manipulator_node recusou os parâmetros do pick")
        self.get_logger().info(
            f"pick: garra '{self.garra_fechar}', depois "
            f"{'fica no objeto' if fica_no_objeto else pose_final}"
        )

        self.braco_estado = None
        resultado = self._chamar(
            self._pick_client, Trigger.Request(), 90.0, "pick_from_vision"
        )
        if not resultado.success:
            raise RuntimeError(f"pick falhou: {resultado.message}")
        self.braco_estado = "pick" if fica_no_objeto else "cad_reference"
        self.get_logger().info(f"pick ok: {resultado.message}")

    def filtrar_visao(self, classe: str):
        """target_class do realtime_3d_inference: só publica target_pose da
        classe pedida (com vários remédios na prateleira a ponte pegaria o
        de maior confiança). "" = sem filtro. Falha só avisa."""
        try:
            pedido = SetParameters.Request(parameters=[Parameter(
                name="target_class",
                value=ParameterValue(
                    type=ParameterType.PARAMETER_STRING, string_value=classe
                ),
            )])
            resultado = self._chamar(
                self._vision_param_client, pedido, 5.0, f"{VISION_NODE}/set_parameters"
            )
            if not resultado.results or not resultado.results[0].successful:
                raise RuntimeError("recusado")
            self.get_logger().info(f"visão filtrando classe '{classe or '(todas)'}'")
        except Exception as exc:
            self.get_logger().warn(f"não ajustou target_class='{classe}' na visão: {exc}")

    def tirar_objeto_da_cena(self):
        """Desanexa e remove da cena do MoveIt o objeto que o pick anexou
        na garra -- senão o planejamento continua achando que ele está lá."""
        anexado = AttachedCollisionObject()
        anexado.link_name = TCP_LINK
        anexado.object.id = GRASP_OBJECT_ID
        anexado.object.operation = CollisionObject.REMOVE
        mundo = CollisionObject()
        mundo.id = GRASP_OBJECT_ID
        mundo.operation = CollisionObject.REMOVE
        cena = PlanningScene(
            is_diff=True,
            robot_state=RobotState(attached_collision_objects=[anexado], is_diff=True),
            world=PlanningSceneWorld(collision_objects=[mundo]),
        )
        resultado = self._chamar(
            self._scene_client, ApplyPlanningScene.Request(scene=cena), 5.0,
            "apply_planning_scene",
        )
        if not resultado.success:
            self.get_logger().warn("apply_planning_scene recusou remover o objeto")


async def comando_temi(ws, node, comando: str, *, braco_ok=("home",), **campos):
    """Manda um comando e devolve a resposta (dict) do comando_concluido."""
    # Trava de segurança: todo comando que desloca a base exige o braço numa
    # pose segura (home, ou as que quem chama liberar explicitamente) --
    # fora disso ele pode bater em prateleira/parede no caminho.
    if comando not in ("pose", "obstaculo") and node.braco_estado not in braco_ok:
        raise RuntimeError(
            f"abortado: base ia executar '{comando}' com o braço em "
            f"'{node.braco_estado or 'pose desconhecida'}' "
            f"(precisa estar em {'/'.join(braco_ok)})"
        )
    await ws.send(json.dumps({"tipo": "comando", "comando": comando, **campos}))
    node.get_logger().info(f"Temi <- {comando} {campos}")
    async for raw in ws:
        msg = json.loads(raw)
        if msg.get("tipo") == "comando_concluido" and msg.get("comando") == comando:
            if not msg.get("success"):
                raise RuntimeError(f"Temi falhou em '{comando}': {msg.get('mensagem')}")
            node.get_logger().info(f"Temi -> {comando} ok: {msg.get('mensagem')}")
            return msg
    raise RuntimeError("conexão com o Temi caiu")


async def ler_yaw(ws, node) -> float:
    resp = await comando_temi(ws, node, "pose")
    return float(resp["yaw"])


async def calibrar_yaw(node: TesteAlinhamento):
    log = node.get_logger()
    async with websockets.connect(node.temi_url) as ws:
        resp = await comando_temi(ws, node, "pose")
    yaw = float(resp["yaw"])
    dados = {}
    if os.path.exists(ARQUIVO_CALIBRACAO):
        with open(ARQUIVO_CALIBRACAO) as f:
            dados = json.load(f)
    dados.setdefault("locais", {})[node.local] = {
        "yaw": yaw,
        "pose": {"x": resp["x"], "y": resp["y"], "yaw": yaw},
        "salvo_em": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    os.makedirs(os.path.dirname(ARQUIVO_CALIBRACAO), exist_ok=True)
    with open(ARQUIVO_CALIBRACAO, "w") as f:
        json.dump(dados, f, indent=2)
    log.info(
        f"yaw de '{node.local}' = {yaw:.4f} rad ({math.degrees(yaw):.1f}°) salvo em "
        f"{ARQUIVO_CALIBRACAO} (pose x={resp['x']:.3f} y={resp['y']:.3f})"
    )


async def rodar(node: TesteAlinhamento):
    log = node.get_logger()
    log.info(f"conectando no Temi em {node.temi_url}")
    async with websockets.connect(node.temi_url) as ws:
        await executar_tarefa(ws, node)


async def _sem_status(_etapa: str):
    pass


async def executar_tarefa(ws, node: TesteAlinhamento, status=_sem_status):
    """Sequência completa com node.classe / node.local / node.cam_pose.

    'status(etapa)' recebe as etapas do contrato do RavTotem: navegando,
    chegou, coletando, concluido (objeto entregue; a volta pra base vem
    depois). Erros sobem como exceção -- quem chama decide o que reportar.
    """
    loop = asyncio.get_running_loop()
    log = node.get_logger()

    async def em_thread(funcao, *args):
        return await loop.run_in_executor(None, funcao, *args)

    yaw_s = node.yaw_prateleira
    if math.isnan(yaw_s):
        yaw_s = carregar_yaw_calibrado(node.local)
    if math.isnan(yaw_s):
        raise RuntimeError(
            f"yaw de '{node.local}' não calibrado: posicione o robô de frente "
            f"pra prateleira e rode com -p modo:=calibrar_yaw -p local:={node.local}"
        )
    log.info(
        f"tarefa: '{node.classe}' em '{node.local}' (cam_pose '{node.cam_pose}'), "
        f"yaw_prateleira = {yaw_s:.4f} rad ({math.degrees(yaw_s):.1f}°)"
    )

    await em_thread(node.filtrar_visao, node.classe)
    try:
        await _executar_tarefa(ws, node, status, yaw_s, em_thread, log)
    finally:
        await em_thread(node.filtrar_visao, "")


async def _executar_tarefa(ws, node, status, yaw_s, em_thread, log):
    # Braço recolhido antes de qualquer deslocamento da base.
    await em_thread(node.mover_braco, "home")
    await status("navegando")
    await comando_temi(ws, node, "ir_para", local=node.local)
    await status("chegou")
    await status("coletando")

    s_anterior = None
    pedido_anterior = None
    for rodada in range(node.max_correcoes + 2):
        await em_thread(node.mover_braco, node.cam_pose)
        await asyncio.sleep(node.cam_pose_settle_s)
        objeto = await em_thread(node.ler_objeto)
        tentativa = 0
        while objeto is None and tentativa < node.reposicionar_tentativas:
            # Não viu o objeto: mexe a câmera (2 cm pra frente) e olha de novo.
            tentativa += 1
            log.warn(
                f"não vi '{node.classe}': andando {node.reposicionar_m:.3f} m "
                f"pra frente e tentando de novo "
                f"({tentativa}/{node.reposicionar_tentativas})"
            )
            await em_thread(node.mover_braco, "home")
            await comando_temi(
                ws, node, "andar", **node.plano_andar(node.reposicionar_m),
                yaw_rumo=yaw_s, ganho_rumo=node.ganho_rumo,
                seguranca=node.avanco_seguranca,
            )
            await em_thread(node.mover_braco, node.cam_pose)
            await asyncio.sleep(node.cam_pose_settle_s)
            objeto = await em_thread(node.ler_objeto)
        if objeto is None:
            raise RuntimeError(
                f"nenhuma detecção de '{node.classe}' com TF em "
                f"{node.deteccao_timeout_s}s (mesmo depois de {tentativa} "
                f"reposicionamento(s))"
            )
        x, y = objeto
        yaw = await ler_yaw(ws, node)

        # Geometria no chão, com "esquerda" positiva:
        #   alfa = quanto o robô está girado em relação à prateleira
        #   d    = distância do centro do Temi ao objeto, pra frente
        #   s    = deslocamento do objeto AO LONGO da prateleira
        alfa = normalizar(yaw - yaw_s)
        x_esq = node.lado_sign * x
        d = abs(y) + node.base_braco_offset_m
        s = d * math.sin(alfa) + x_esq * math.cos(alfa)
        log.info(
            f"medição {rodada}: x={x:+.3f} m, d={d:.3f} m, "
            f"yaw={yaw:.4f} -> erro de ângulo {math.degrees(alfa):+.1f}°, "
            f"deslocamento ao longo da prateleira s={s:+.3f} m"
        )

        if s_anterior is not None and pedido_anterior:
            # Pra calibrar o andar: quanto o robô andou de fato ao longo
            # da prateleira (medido pela visão) vs. o que foi pedido.
            andado = abs(s_anterior - s)
            log.info(
                f"calibração: pediu {pedido_anterior:.3f} m, andou "
                f"{andado:.3f} m ao longo da prateleira -> fator real "
                f"{andado / pedido_anterior:.2f}"
            )

        # Alinhado pelo x medido OU pelo s (posição ao longo da prateleira,
        # descontado o ângulo que sobrou): com x=0.021 e s=0.016 ele não
        # andava (s dentro) nem aceitava (x fora) e ficava girando o braço
        # cam_pose<->home no mesmo lugar até estourar as correções.
        if abs(alfa) <= node.tolerancia_yaw and (
            abs(x) <= node.tolerancia_m or abs(s) <= node.tolerancia_m
        ):
            log.info(
                f"ALINHADO: x={x:+.3f} m, ângulo {math.degrees(alfa):+.1f}° "
                f"depois de {rodada} deslocamento(s)"
            )
            if node.avanco_final_m > 0:
                # Aproxima da prateleira, reto (rumo = yaw_prateleira).
                await em_thread(node.mover_braco, "home")
                log.info(f"avançando {node.avanco_final_m:.3f} m em direção à prateleira")
                # Distância mínima a obstáculos reduzida só durante o avanço
                # (com a prateleira na frente o Temi freava: 2.5 cm de 15).
                obst_original = None
                if node.avanco_obstaculo_cm >= 0:
                    resp = await comando_temi(
                        ws, node, "obstaculo", cm=node.avanco_obstaculo_cm
                    )
                    obst_original = resp.get("antes")
                try:
                    # Pela odometria (getPosition), não por tempo: perto da
                    # prateleira o Temi freia (~0.6 cm/s) e o andar por tempo
                    # parava com 2.5 cm. Prazo longo pra ele chegar devagar.
                    await comando_temi(
                        ws, node, "andar",
                        metros=round(node.avanco_final_m, 3),
                        velocidade=node.avanco_velocidade,
                        antecipacao_m=node.avanco_antecipacao_m,
                        timeout_s=node.avanco_timeout_s,
                        yaw_rumo=yaw_s, ganho_rumo=node.ganho_rumo,
                        seguranca=node.avanco_seguranca,
                    )
                finally:
                    if obst_original is not None and obst_original >= 0:
                        await comando_temi(ws, node, "obstaculo", cm=int(obst_original))
                # Base parada: braço volta a olhar pro objeto (pronto pro pick).
                await em_thread(node.mover_braco, node.cam_pose)
                log.info(f"avanço concluído, braço em {node.cam_pose}")
            break
        if rodada > node.max_correcoes:
            raise RuntimeError(
                f"não alinhou depois de {rodada} deslocamento(s): "
                f"x={x:+.3f} m, ângulo {math.degrees(alfa):+.1f}°"
            )

        await em_thread(node.mover_braco, "home")

        pedido_anterior = None
        if abs(s) > node.tolerancia_m:
            rumo = normalizar(yaw_s + math.copysign(math.pi / 2, s))
            lado = "esquerda" if s > 0 else "direita"
            log.info(
                f"deslocamento {rodada + 1}: andar {abs(s):.3f} m pra {lado} "
                f"ao longo da prateleira"
            )
            # Giro pra andar pode ser mais frouxo: o andar corrige o rumo
            # pelo yaw no caminho.
            await comando_temi(
                ws, node, "girar_para", yaw=rumo,
                tolerancia_graus=2.0, aceitar_graus=node.aceitar_giro_graus,
            )
            plano = node.plano_andar(abs(s))
            await comando_temi(
                ws, node, "andar", **plano,
                yaw_rumo=rumo, ganho_rumo=node.ganho_rumo,
            )
            pedido_anterior = plano["metros"]
        # Sempre termina de frente pra prateleira (corrige o ângulo de
        # chegada mesmo quando não precisou andar).
        # Se sobrar erro (até aceitar_giro_graus), a próxima medição lê o
        # yaw real e compensa no s -- não precisa abortar.
        await comando_temi(
            ws, node, "girar_para", yaw=yaw_s,
            tolerancia_graus=1.0, aceitar_graus=node.aceitar_giro_graus,
        )
        s_anterior = s

    if not node.fazer_pick_place:
        log.info("fazer_pick_place=false: parando no alinhamento")
        return

    # ---------------- pick ----------------
    if node.braco_estado != node.cam_pose:
        await em_thread(node.mover_braco, node.cam_pose)
    # Garante detecção nova (pós-avanço) antes do pick: a ponte só aceita
    # detecções de até 5 s.
    await asyncio.sleep(node.cam_pose_settle_s)
    # Só confirma que há detecção nova (a ponte usa a mais recente); não
    # precisa da mediana de 3 como na medição do alinhamento.
    if await em_thread(node.ler_objeto, 1, True) is None:
        raise RuntimeError(
            f"sem detecção de '{node.classe}' pra fazer o pick com y em "
            f"[{node.y_min_objeto}, {node.y_max_objeto}]"
        )
    log.info("fazendo o pick")
    await em_thread(node.pick)

    if node.recuar_apos_pick_m > 0:
        # Prateleira de baixo: base recua com o braço ainda no objeto (de
        # frente pra prateleira, rumo yaw_s) antes de o braço sair dela.
        log.info(f"recuando {node.recuar_apos_pick_m:.3f} m com o objeto na garra")
        await comando_temi(
            ws, node, "andar",
            metros=-round(node.recuar_apos_pick_m, 3),
            velocidade=node.avanco_velocidade,
            antecipacao_m=node.avanco_antecipacao_m,
            timeout_s=node.avanco_timeout_s,
            yaw_rumo=yaw_s, ganho_rumo=node.ganho_rumo,
            seguranca=node.avanco_seguranca,
            braco_ok=("pick",),
        )

    # ---------------- levar até o place ----------------
    await em_thread(node.mover_braco, "ready")
    # Único trecho em que a base anda com o braço fora de home (pedido:
    # leva o objeto em ready).
    await comando_temi(
        ws, node, "ir_para", local=node.local_place, braco_ok=("ready",)
    )
    await em_thread(node.mover_braco, "place")
    await em_thread(node.mover_braco, "open")
    await em_thread(node.tirar_objeto_da_cena)
    log.info("objeto entregue")
    await status("concluido")

    # ---------------- voltar pra base ----------------
    await em_thread(node.mover_braco, "cad_reference")
    await em_thread(node.mover_braco, "home")
    await comando_temi(ws, node, "ir_para", local=node.local_base)
    log.info(f"TAREFA CONCLUÍDA: robô de volta em '{node.local_base}'")


def main():
    rclpy.init()
    node = TesteAlinhamento()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()

    try:
        if node.modo == "calibrar_yaw":
            asyncio.run(calibrar_yaw(node))
        else:
            asyncio.run(rodar(node))
    except KeyboardInterrupt:
        pass
    except Exception as exc:
        node.get_logger().error(f"teste interrompido: {exc}")
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
