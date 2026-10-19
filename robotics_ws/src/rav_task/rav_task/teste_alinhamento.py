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
  6. alinhado: braço -> home e anda 'avanco_final_m' (15 cm) pra frente,
     mantendo o rumo de frente pra prateleira; depois braço -> cam_pose

yaw_prateleira = yaw do Temi exatamente de frente pra prateleira, medido
uma vez com:  ros2 run rav_task teste_alinhamento --ros-args -p modo:=calibrar_yaw
(salvo em ~/.ros/rav_alinhamento.json e lido daí nas próximas execuções).

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
from std_msgs.msg import String

import websockets

from rav_manipulator_moveit_config.srv import MoveToNamedState

DETECTIONS_TOPIC = "/rav_vision/detections_3d"
ARQUIVO_CALIBRACAO = os.path.expanduser("~/.ros/rav_alinhamento.json")


def normalizar(rad: float) -> float:
    """Ângulo em (-pi, pi]."""
    return math.atan2(math.sin(rad), math.cos(rad))


class TesteAlinhamento(Node):

    def __init__(self):
        super().__init__("teste_alinhamento")

        # "alinhar" (padrão) ou "calibrar_yaw" (só lê e salva o yaw atual
        # como yaw_prateleira -- robô posicionado de frente pra prateleira).
        self.declare_parameter("modo", "alinhar")
        self.declare_parameter("temi_url", "ws://172.20.10.3:8765")
        self.declare_parameter("local", "preprateleira")
        self.declare_parameter("classe", "ibuprotrat")
        # +1: objeto em x>0 fica à esquerda do Temi -> gira +90 (anti-horário).
        # Se o Temi virar pro lado errado no 1o teste, usar -1.
        self.declare_parameter("lado_sign", 1)
        self.declare_parameter("tolerancia_m", 0.02)
        self.declare_parameter("amostras", 3)
        self.declare_parameter("cam_pose_settle_s", 1.5)
        self.declare_parameter("deteccao_timeout_s", 15.0)
        # Depois do deslocamento principal, quantas correções extras no
        # máximo (a ideia é acertar de primeira; isso é só rede de segurança).
        self.declare_parameter("max_correcoes", 1)
        # Yaw (rad, mapa do Temi) de frente pra prateleira. NaN = lê do
        # ARQUIVO_CALIBRACAO (gravado pelo modo calibrar_yaw).
        self.declare_parameter("yaw_prateleira", float("nan"))
        self.declare_parameter("tolerancia_yaw_graus", 1.5)
        # turnBy de 1-2° é impreciso: depois das tentativas, o app aceita o
        # giro se o erro ficar até isso (a medição seguinte compensa).
        self.declare_parameter("aceitar_giro_graus", 3.0)
        # Depois de alinhado, quanto andar pra frente (em direção à
        # prateleira). 0 = não avança.
        self.declare_parameter("avanco_final_m", 0.15)
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
        # Distâncias curtas andam por tempo: m/s reais por unidade de
        # skidJoy. Medido em 2026-10-05: 1.09s a velocidade 0.08 deslocou o
        # objeto 0.037 m na visão (pedido 0.087) -> 0.037/1.09/0.08 = 0.43.
        # NÃO usar o "final X m" do Temi pra isso: em distância curta a
        # odometria dele nem se mexe (reportou 0.000). Recalibrar pelo
        # "fator real" do loop: novo = antigo * fator_real.
        self.declare_parameter("andar_vel_real", 0.43)

        p = lambda nome: self.get_parameter(nome).value  # noqa: E731
        self.temi_url = str(p("temi_url"))
        self.local = str(p("local"))
        self.classe = str(p("classe"))
        self.lado_sign = 1 if int(p("lado_sign")) >= 0 else -1
        self.tolerancia_m = float(p("tolerancia_m"))
        self.amostras = int(p("amostras"))
        self.cam_pose_settle_s = float(p("cam_pose_settle_s"))
        self.deteccao_timeout_s = float(p("deteccao_timeout_s"))
        self.modo = str(p("modo"))
        self.max_correcoes = int(p("max_correcoes"))
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
        if math.isnan(self.yaw_prateleira) and os.path.exists(ARQUIVO_CALIBRACAO):
            with open(ARQUIVO_CALIBRACAO) as f:
                self.yaw_prateleira = float(json.load(f)["yaw_prateleira"])
        self.andar_k = float(p("andar_ultrapassagem_por_vel"))
        self.andar_vel_max = float(p("andar_velocidade_max"))
        self.andar_vel_min = float(p("andar_velocidade_min"))
        self.andar_vel_real = float(p("andar_vel_real"))

        # Última pose nomeada confirmada pelo move_group (None = desconhecida).
        # A base só anda/gira com isso em "home" -- ver comando_temi.
        self.braco_estado = None

        cb_group = ReentrantCallbackGroup()
        self._move_client = self.create_client(
            MoveToNamedState, "move_to_named_state", callback_group=cb_group
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
            if det["class_name"] == self.classe and pos is not None:
                with self._lock:
                    self._xs.append((stamp, pos["x"], pos["y"]))

    def ler_objeto(self):
        """Mediana de (x, y) de 'amostras' detecções tiradas a partir de agora."""
        inicio = self.get_clock().now().nanoseconds / 1e9
        prazo = time.monotonic() + self.deteccao_timeout_s
        while time.monotonic() < prazo:
            with self._lock:
                novos = [(x, y) for stamp, x, y in self._xs if stamp >= inicio]
            if len(novos) >= self.amostras:
                novos = novos[: self.amostras]
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

        if antecipacao < 0.7 * metros:
            return {
                "metros": round(metros, 3),
                "velocidade": round(velocidade, 3),
                "antecipacao_m": round(antecipacao, 3),
            }

        # Curto demais pra parar pela odometria (pararia antes de sair do
        # lugar): anda por tempo na velocidade mínima.
        duracao = metros / (self.andar_vel_min * self.andar_vel_real)
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
        # Durante o movimento (ou se falhar) a pose fica desconhecida.
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
        self.braco_estado = estado
        self.get_logger().info(f"braço em '{estado}'")


async def comando_temi(ws, node, comando: str, **campos):
    """Manda um comando e devolve a resposta (dict) do comando_concluido."""
    # Trava de segurança: todo comando que desloca a base exige o braço em
    # home -- fora disso ele pode bater em prateleira/parede no caminho.
    if comando not in ("pose", "obstaculo") and node.braco_estado != "home":
        raise RuntimeError(
            f"abortado: base ia executar '{comando}' com o braço em "
            f"'{node.braco_estado or 'pose desconhecida'}' (precisa estar em home)"
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
    os.makedirs(os.path.dirname(ARQUIVO_CALIBRACAO), exist_ok=True)
    with open(ARQUIVO_CALIBRACAO, "w") as f:
        json.dump({
            "yaw_prateleira": yaw,
            "pose": {"x": resp["x"], "y": resp["y"], "yaw": yaw},
            "salvo_em": time.strftime("%Y-%m-%d %H:%M:%S"),
        }, f, indent=2)
    log.info(
        f"yaw_prateleira = {yaw:.4f} rad ({math.degrees(yaw):.1f}°) salvo em "
        f"{ARQUIVO_CALIBRACAO} (pose x={resp['x']:.3f} y={resp['y']:.3f})"
    )


async def rodar(node: TesteAlinhamento):
    loop = asyncio.get_running_loop()
    log = node.get_logger()

    async def em_thread(funcao, *args):
        return await loop.run_in_executor(None, funcao, *args)

    if math.isnan(node.yaw_prateleira):
        raise RuntimeError(
            "yaw_prateleira não calibrado: posicione o robô de frente pra "
            "prateleira e rode com -p modo:=calibrar_yaw"
        )
    yaw_s = node.yaw_prateleira
    log.info(f"yaw_prateleira = {yaw_s:.4f} rad ({math.degrees(yaw_s):.1f}°)")

    log.info(f"conectando no Temi em {node.temi_url}")
    async with websockets.connect(node.temi_url) as ws:
        # Braço recolhido antes de qualquer deslocamento da base.
        await em_thread(node.mover_braco, "home")
        await comando_temi(ws, node, "ir_para", local=node.local)

        s_anterior = None
        pedido_anterior = None
        for rodada in range(node.max_correcoes + 2):
            await em_thread(node.mover_braco, "cam_pose")
            await asyncio.sleep(node.cam_pose_settle_s)
            objeto = await em_thread(node.ler_objeto)
            if objeto is None:
                raise RuntimeError(
                    f"nenhuma detecção de '{node.classe}' com TF em "
                    f"{node.deteccao_timeout_s}s"
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

            if abs(x) <= node.tolerancia_m and abs(alfa) <= node.tolerancia_yaw:
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
                    await em_thread(node.mover_braco, "cam_pose")
                    log.info("avanço concluído, braço em cam_pose")
                return
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
