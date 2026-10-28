"""Orquestrador da tarefa: espera o pedido do RavTotem e executa tudo.

Fica conectado ao RavPlatform (WebSocket do tablet do Temi, porta 8765)
como "orquestrador". Fluxo de um pedido:

  RavTotem --pedido(produtoId)--> RavPlatform --tarefa--> orquestrador
  orquestrador --status_tarefa(etapa)--> RavPlatform --status--> RavTotem

Pra cada tarefa: produtoId -> (classe, local, cam_pose) pelo
config/produtos.yaml e roda executar_tarefa() (o mesmo fluxo do
teste_alinhamento: alinhar, pick, entregar no place, voltar pra base).
Terminou (ou falhou e se recolheu), avisa "orquestrador_livre" e espera o
próximo pedido. Se a conexão cair, reconecta sozinho.

Pressupõe braço, câmera, visão e vision_pick_bridge rodando (ver
launch/rav_robo.launch.py, que sobe tudo).
"""

import asyncio
import json
import os
import threading

import rclpy
import yaml
from ament_index_python.packages import get_package_share_directory
from rclpy.executors import MultiThreadedExecutor

import websockets

from rav_task.teste_alinhamento import (
    TesteAlinhamento,
    comando_temi,
    executar_tarefa,
)

RECONECTAR_S = 3.0


class Orquestrador(TesteAlinhamento):

    def __init__(self):
        super().__init__("rav_orquestrador")
        self.declare_parameter(
            "produtos_yaml",
            os.path.join(
                get_package_share_directory("rav_task"), "config", "produtos.yaml"
            ),
        )
        caminho = str(self.get_parameter("produtos_yaml").value)
        with open(caminho) as f:
            catalogo = yaml.safe_load(f)
        self.produtos = {int(k): v for k, v in catalogo["produtos"].items()}
        self.local_place = catalogo.get("local_place", self.local_place)
        self.local_base = catalogo.get("local_base", self.local_base)
        self.get_logger().info(
            f"catálogo {caminho}: "
            + ", ".join(f"{k}={v['classe']}@{v['local']}" for k, v in self.produtos.items())
        )


async def recolher(ws, node, em_thread):
    """Depois de uma falha: braço pra home e, se deu, base de volta pra base."""
    log = node.get_logger()
    try:
        await em_thread(node.tirar_objeto_da_cena)
        await em_thread(node.mover_braco, "home")
    except Exception as exc:
        log.error(f"não consegui recolher o braço ({exc}); robô fica parado")
        return
    try:
        await comando_temi(ws, node, "ir_para", local=node.local_base)
        log.info(f"recolhido: de volta em '{node.local_base}'")
    except Exception as exc:
        log.error(f"não consegui voltar pra base: {exc}")


async def atender(ws, node: Orquestrador, msg: dict):
    loop = asyncio.get_running_loop()
    log = node.get_logger()
    pedido_id = msg.get("pedidoId")
    produto_id = msg.get("produtoId")

    async def em_thread(funcao, *args):
        return await loop.run_in_executor(None, funcao, *args)

    async def status(etapa: str):
        await ws.send(json.dumps(
            {"tipo": "status_tarefa", "pedidoId": pedido_id, "etapa": etapa}
        ))
        log.info(f"[pedido {pedido_id}] etapa: {etapa}")

    try:
        produto = node.produtos.get(int(produto_id)) if produto_id is not None else None
        if produto is None:
            log.error(f"[pedido {pedido_id}] produto {produto_id} fora do catálogo")
            await status("erro")
            return

        node.classe = produto["classe"]
        node.local = produto["local"]
        node.cam_pose = produto.get("cam_pose", "cam_pose")
        with node._lock:
            node._xs.clear()
        log.info(f"[pedido {pedido_id}] {produto.get('nome', node.classe)}")

        try:
            await executar_tarefa(ws, node, status)
        except Exception as exc:
            log.error(f"[pedido {pedido_id}] falhou: {exc}")
            await status("erro")
            await recolher(ws, node, em_thread)
    finally:
        await ws.send(json.dumps({"tipo": "orquestrador_livre"}))


async def servir(node: Orquestrador):
    log = node.get_logger()
    while True:
        try:
            async with websockets.connect(node.temi_url) as ws:
                await ws.send(json.dumps({"tipo": "registrar", "papel": "orquestrador"}))
                log.info(f"conectado ao RavPlatform ({node.temi_url}); esperando pedidos")
                async for raw in ws:
                    msg = json.loads(raw)
                    if msg.get("tipo") == "tarefa":
                        await atender(ws, node, msg)
                        log.info("esperando o próximo pedido")
        except (OSError, websockets.exceptions.WebSocketException) as exc:
            log.warn(f"sem conexão com o RavPlatform ({exc}); tentando de novo")
        await asyncio.sleep(RECONECTAR_S)


async def principal(node: Orquestrador):
    """servir() + vigia: Ctrl+C/SIGTERM derrubam o contexto do rclpy, mas o
    laço do WebSocket continuaria vivo (conectado ao tablet, aceitando
    pedidos sem conseguir executar). O vigia encerra tudo junto."""
    tarefa = asyncio.create_task(servir(node))
    while rclpy.ok() and not tarefa.done():
        await asyncio.sleep(0.5)
    tarefa.cancel()
    try:
        await tarefa
    except asyncio.CancelledError:
        pass


def main():
    rclpy.init()
    node = Orquestrador()
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()
    try:
        asyncio.run(principal(node))
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
