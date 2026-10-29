"""Simulador pra testar teste_alinhamento/orquestrador sem o robô.

Faz o papel de: app RavPlatform (WebSocket com os comandos da base e o
repasse de pedido), Temi (pose no mapa, giros e andar), braço
(move_to_named_state), pick (pick_from_vision), cena do MoveIt e visão
(/rav_vision/detections_3d), tudo com geometria de verdade no chão.

Uso (num terminal com o workspace carregado):
  python3 src/rav_task/test/sim_temi.py --erro-chegada 2 --fator-andar 0.6 --produto 1
e, em outro:
  ros2 run rav_task orquestrador --ros-args \\
    -r move_to_named_state:=/sim_move -r pick_from_vision:=/sim_pick \\
    -r apply_planning_scene:=/sim_scene -r /rav_vision/detections_3d:=/sim_det \\
    -r /rav_manipulator/set_parameters:=/sim_manip_params \\
    -p temi_url:=ws://127.0.0.1:8797 -p yaw_prateleira:=0.7 -p cam_pose_settle_s:=0.3
(--produto 0 = não manda tarefa; serve pro teste_alinhamento.)
"""

import argparse
import asyncio
import json
import math
import random
import signal
import threading
import time

import rclpy
from moveit_msgs.srv import ApplyPlanningScene
from rcl_interfaces.msg import SetParametersResult
from rcl_interfaces.srv import SetParameters
from rclpy.node import Node
from std_msgs.msg import String
from std_srvs.srv import Trigger

import websockets

from rav_manipulator_moveit_config.srv import MoveToNamedState

POSES_GARRA = ("open", "closed", "close_ibu", "close_pom", "close_aci")
YAW_PRATELEIRA = 0.7


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--erro-chegada", type=float, default=2.0, help="graus")
    ap.add_argument("--fator-andar", type=float, default=1.0,
                    help="quanto o Temi anda do que foi pedido")
    ap.add_argument("--produto", type=int, default=0)
    ap.add_argument("--classe", default="ibuprotrat")
    ap.add_argument("--deteccao-ruim", action="store_true",
                    help="primeiras detecções com y absurdo (TF velha)")
    ap.add_argument("--sumir", action="store_true",
                    help="objeto some da câmera depois do 1º deslocamento e "
                         "volta no próximo andar (testa o reposicionamento)")
    ap.add_argument("--porta", type=int, default=8797)
    args = ap.parse_args()

    # Objeto 12 cm à esquerda do ponto de chegada, a 0.85 m na frente.
    rob = {"x": 2.0, "y": 1.0, "yaw": YAW_PRATELEIRA + math.radians(args.erro_chegada)}
    c, s = math.cos(YAW_PRATELEIRA), math.sin(YAW_PRATELEIRA)
    obj = (rob["x"] + 0.85 * c - 0.12 * s, rob["y"] + 0.85 * s + 0.12 * c)
    estado = {"braco": "home", "ruins": 6 if args.deteccao_ruim else 0,
              "oculto": False, "sumir": args.sumir}

    rclpy.init()
    n = Node("sim_temi")

    def mover(req, res):
        print(f"  [braço] -> {req.state_name}", flush=True)
        if req.state_name not in POSES_GARRA:
            estado["braco"] = req.state_name
        res.success, res.message = True, "ok"
        return res

    def pick(_req, res):
        print("  [pick] pick_from_vision", flush=True)
        estado["braco"] = "cad_reference"
        res.success, res.message = True, "pick ok"
        return res

    def cena(_req, res):
        print("  [cena] objeto removido", flush=True)
        res.success = True
        return res

    n.create_service(MoveToNamedState, "/sim_move", mover)
    n.create_service(Trigger, "/sim_pick", pick)
    n.create_service(ApplyPlanningScene, "/sim_scene", cena)

    def params_braco(req, res):
        print("  [braço] parâmetros: " + ", ".join(
            f"{p.name}={p.value.string_value!r}" for p in req.parameters), flush=True)
        res.results = [SetParametersResult(successful=True) for _ in req.parameters]
        return res

    n.create_service(SetParameters, "/sim_manip_params", params_braco)
    pub = n.create_publisher(String, "/sim_det", 10)

    def publicar():
        while rclpy.ok():
            dx, dy = obj[0] - rob["x"], obj[1] - rob["y"]
            cy, sy = math.cos(rob["yaw"]), math.sin(rob["yaw"])
            frente = cy * dx + sy * dy
            esquerda = -sy * dx + cy * dy
            dets = []
            if estado["braco"].startswith("cam_pose") and not estado["oculto"]:
                y = -(frente - 0.05)
                if estado["ruins"] > 0:
                    estado["ruins"] -= 1
                    y = -0.146
                dets = [{"class_name": args.classe,
                         "position_target_m": {"x": esquerda, "y": y, "z": 0.1}}]
            t = n.get_clock().now().nanoseconds / 1e9
            pub.publish(String(data=json.dumps({
                "stamp_sec": int(t), "stamp_nanosec": int((t % 1) * 1e9),
                "detections": dets,
            })))
            time.sleep(0.2)

    threading.Thread(target=publicar, daemon=True).start()
    threading.Thread(target=rclpy.spin, args=(n,), daemon=True).start()

    def nz(a):
        return math.atan2(math.sin(a), math.cos(a))

    async def conexao(ws):
        async for raw in ws:
            m = json.loads(raw)
            tipo = m.get("tipo")
            if tipo == "registrar":
                print(f"  [platform] orquestrador registrado", flush=True)
                if args.produto:
                    await ws.send(json.dumps({"tipo": "tarefa", "pedidoId": "sim1",
                                              "produtoId": args.produto}))
                continue
            if tipo == "status_tarefa":
                print(f"  [totem] etapa: {m['etapa']}", flush=True)
                continue
            if tipo == "orquestrador_livre":
                print("  [platform] orquestrador livre", flush=True)
                continue
            cmd, extra = m["comando"], {}
            if cmd == "pose":
                extra = dict(rob)
            elif cmd == "girar_para":
                rob["yaw"] = nz(m["yaw"] + math.radians(random.uniform(-0.8, 0.8)))
            elif cmd == "andar":
                d = m["metros"] * args.fator_andar
                if estado["oculto"]:
                    estado["oculto"] = False
                elif estado["sumir"] and abs(m["metros"]) > 0.05:
                    estado["oculto"], estado["sumir"] = True, False
                rob["x"] += d * math.cos(rob["yaw"])
                rob["y"] += d * math.sin(rob["yaw"])
            elif cmd == "obstaculo":
                extra = {"antes": 10, "depois": 10}
            print(f"  [temi] {cmd} {m.get('metros', '')} (braço={estado['braco']})", flush=True)
            await ws.send(json.dumps({"tipo": "comando_concluido", "comando": cmd,
                                      "success": True, "mensagem": "ok", **extra}))

    async def servidor():
        async with websockets.serve(conexao, "127.0.0.1", args.porta):
            await asyncio.Future()

    # SIGTERM (timeout, kill) encerra como Ctrl+C -- senão o simulador
    # ficava vivo depois dos testes, gastando CPU.
    signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
    try:
        asyncio.run(servidor())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
