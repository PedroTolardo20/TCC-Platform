package com.example.ravplatform.network

import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import org.json.JSONObject
import java.net.URI

// Cliente WebSocket pro start_task (Linux/ROS2). Ao abrir a conexão já manda
// o pedido (classeYolo) e o aviso de chegada na coleta -- pelo momento em
// que isso é instanciado (ver TemiNavegacao.iniciarColeta), as duas coisas
// já são verdade ao mesmo tempo.
class StartTaskClient(
    urlServidor: String,
    private val classeYolo: String,
    private val onLog: (String) -> Unit,
    private val onPickConcluido: (Boolean, String) -> Unit,
    private val onPlaceConcluido: (Boolean, String) -> Unit,
    // start_task pede pra girar a base (graus, positivo = anti-horário) até
    // o objeto ficar alinhado com o braço; responder com enviarGiroConcluido.
    private val onGirarBase: (Int) -> Unit,
    private val onErro: (String) -> Unit
) : WebSocketClient(URI(urlServidor)) {

    override fun onOpen(handshakedata: ServerHandshake?) {
        onLog("Conectado ao start_task")
        enviar(JSONObject().apply {
            put("tipo", "pedido")
            put("classeYolo", classeYolo)
        })
        enviar(JSONObject().apply { put("tipo", "chegou_pickup") })
    }

    override fun onMessage(message: String) {
        onLog("start_task: $message")
        val json = JSONObject(message)
        when (json.optString("tipo")) {
            "pick_concluido" -> onPickConcluido(
                json.optBoolean("success"), json.optString("mensagem")
            )
            "place_concluido" -> onPlaceConcluido(
                json.optBoolean("success"), json.optString("mensagem")
            )
            "girar_base" -> onGirarBase(json.optInt("graus"))
        }
    }

    override fun onClose(code: Int, reason: String?, remote: Boolean) {
        onLog("Desconectado do start_task ($reason)")
    }

    override fun onError(ex: Exception?) {
        val motivo = ex?.message ?: "erro desconhecido"
        onLog("Erro start_task: $motivo")
        onErro(motivo)
    }

    fun enviarChegouPlace() {
        enviar(JSONObject().apply { put("tipo", "chegou_place") })
    }

    fun enviarGiroConcluido(sucesso: Boolean, mensagem: String) {
        enviar(JSONObject().apply {
            put("tipo", "giro_concluido")
            put("success", sucesso)
            put("mensagem", mensagem)
        })
    }

    private fun enviar(json: JSONObject) {
        send(json.toString())
        onLog("Enviado: $json")
    }
}
