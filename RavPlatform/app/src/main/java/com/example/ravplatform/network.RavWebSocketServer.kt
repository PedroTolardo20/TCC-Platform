package com.example.ravplatform.network

import com.example.ravplatform.data.localDoProduto
import com.example.ravplatform.nav.NavegacaoController
import org.java_websocket.WebSocket
import org.java_websocket.handshake.ClientHandshake
import org.java_websocket.server.WebSocketServer
import org.json.JSONObject
import java.net.InetSocketAddress

class RavWebSocketServer(
    porta: Int,
    private val navegacao: NavegacaoController,
    private val onLog: (String) -> Unit
) : WebSocketServer(InetSocketAddress(porta)) {

    override fun onStart() {
        onLog("Servidor ouvindo na porta $port")
    }

    override fun onOpen(conn: WebSocket, handshake: ClientHandshake) {
        onLog("Totem conectado: ${conn.remoteSocketAddress}")
    }

    override fun onClose(conn: WebSocket, code: Int, reason: String?, remote: Boolean) {
        onLog("Totem desconectado")
    }

    override fun onMessage(conn: WebSocket, message: String) {
        onLog("Recebido: $message")
        val json = JSONObject(message)
        if (json.optString("tipo") != "pedido") return

        val pedidoId = json.optString("pedidoId")
        val produtoId = json.optInt("produtoId", -1)

        fun enviarStatus(etapa: String) {
            val resp = JSONObject().apply {
                put("tipo", "status")
                put("pedidoId", pedidoId)
                put("etapa", etapa)
            }
            conn.send(resp.toString())
            onLog("Enviado: $etapa")
        }

        val local = localDoProduto(produtoId)
        if (local == null) {
            enviarStatus("erro")
            onLog("Produto $produtoId nao encontrado no catalogo")
            return
        }

        enviarStatus("recebido")
        onLog("Navegando para ${local.pontoNavegacao} (YOLO: ${local.classeYolo})")
        navegacao.executarPedido(local.pontoNavegacao) { etapa ->
            enviarStatus(etapa)
        }
    }

    override fun onError(conn: WebSocket?, ex: Exception) {
        onLog("Erro: ${ex.message}")
    }
}