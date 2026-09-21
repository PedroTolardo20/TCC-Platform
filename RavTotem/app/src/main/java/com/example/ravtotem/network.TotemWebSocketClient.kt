package com.example.ravtotem.network

import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import org.json.JSONObject
import java.util.UUID

class TotemWebSocketClient(
    private val urlServidor: String
) {
    private val client = OkHttpClient()
    private var webSocket: WebSocket? = null

    // Etapa atual do pedido. Valores: as etapas do contrato
    // ("recebido", "navegando", "chegou", "coletando", "concluido", "erro"),
    // mais "conectando" enquanto a conexão é estabelecida, e null quando inativo.
    private val _etapa = MutableStateFlow<String?>(null)
    val etapa: StateFlow<String?> = _etapa.asStateFlow()

    fun enviarPedido(produtoId: Int) {
        _etapa.value = "conectando"
        val request = Request.Builder().url(urlServidor).build()
        webSocket = client.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                val pedido = JSONObject().apply {
                    put("tipo", "pedido")
                    put("pedidoId", UUID.randomUUID().toString().take(8))
                    put("produtoId", produtoId)
                }
                webSocket.send(pedido.toString())
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                val json = JSONObject(text)
                if (json.optString("tipo") == "status") {
                    _etapa.value = json.optString("etapa")
                }
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                _etapa.value = "erro"
            }
        })
    }

    fun fechar() {
        webSocket?.close(1000, null)
        webSocket = null
        _etapa.value = null
    }
}