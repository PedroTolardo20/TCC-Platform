package com.example.ravplatform.network

import com.example.ravplatform.data.PONTO_ENTREGA
import com.example.ravplatform.data.localDoProduto
import com.example.ravplatform.nav.NavegacaoController
import com.example.ravplatform.nav.TemiComandos
import org.java_websocket.WebSocket
import org.java_websocket.handshake.ClientHandshake
import org.java_websocket.server.WebSocketServer
import org.json.JSONObject
import java.net.InetSocketAddress

class RavWebSocketServer(
    porta: Int,
    private val navegacao: NavegacaoController,
    private val onLog: (String) -> Unit,
    // Comandos avulsos de movimento (teste de alinhamento disparado pelo
    // Linux); null = servidor só aceita pedidos do Totem.
    private val comandos: TemiComandos? = null
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
        if (json.optString("tipo") == "comando") {
            executarComando(conn, json)
            return
        }
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
        navegacao.executarPedido(local.pontoNavegacao, local.classeYolo, PONTO_ENTREGA) { etapa ->
            enviarStatus(etapa)
        }
    }

    // {"tipo":"comando","comando":"ir_para"|"girar"|"andar", "local"/"graus"/"metros"}
    // -> responde {"tipo":"comando_concluido","comando":...,"success":...,"mensagem":...}
    private fun executarComando(conn: WebSocket, json: JSONObject) {
        val comando = json.optString("comando")

        fun responder(sucesso: Boolean, mensagem: String) {
            val resp = JSONObject().apply {
                put("tipo", "comando_concluido")
                put("comando", comando)
                put("success", sucesso)
                put("mensagem", mensagem)
            }
            conn.send(resp.toString())
            onLog("Enviado: $resp")
        }

        val executor = comandos
        if (executor == null) {
            responder(false, "comandos avulsos desabilitados neste servidor")
            return
        }

        when (comando) {
            "ir_para" -> executor.irPara(json.optString("local"), ::responder)
            "girar" -> executor.girar(json.optInt("graus"), ::responder)
            "andar" -> executor.andarFrente(json.optDouble("metros", 0.0).toFloat(), ::responder)
            else -> responder(false, "comando desconhecido: '$comando'")
        }
    }

    override fun onError(conn: WebSocket?, ex: Exception) {
        onLog("Erro: ${ex.message}")
    }
}