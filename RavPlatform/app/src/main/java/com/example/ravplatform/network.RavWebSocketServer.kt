package com.example.ravplatform.network

import com.example.ravplatform.nav.TemiComandos
import org.java_websocket.WebSocket
import org.java_websocket.handshake.ClientHandshake
import org.java_websocket.server.WebSocketServer
import org.json.JSONObject
import java.net.InetSocketAddress

/**
 * Servidor do tablet do Temi. Duas pontas se conectam aqui:
 *  - RavTotem: manda {"tipo":"pedido","pedidoId","produtoId"} e recebe
 *    {"tipo":"status","pedidoId","etapa"};
 *  - orquestrador (Linux, rav_task/orquestrador.py): se registra com
 *    {"tipo":"registrar","papel":"orquestrador"}, recebe as tarefas, manda
 *    {"tipo":"status_tarefa",...} (repassado ao Totem) e
 *    {"tipo":"orquestrador_livre"} quando termina; e comanda a base com
 *    {"tipo":"comando",...} (executados pelo TemiComandos).
 * Um pedido por vez: com o robô ocupado o Totem recebe "erro".
 */
class RavWebSocketServer(
    porta: Int,
    private val onLog: (String) -> Unit,
    private val comandos: TemiComandos? = null
) : WebSocketServer(InetSocketAddress(porta)) {

    private val trava = Any()
    private var orquestrador: WebSocket? = null
    private var ocupado = false
    private var pedidoAtual: String? = null
    private var totemAtual: WebSocket? = null

    override fun onStart() {
        onLog("Servidor ouvindo na porta $port")
    }

    override fun onOpen(conn: WebSocket, handshake: ClientHandshake) {
        onLog("Conectado: ${conn.remoteSocketAddress}")
    }

    override fun onClose(conn: WebSocket, code: Int, reason: String?, remote: Boolean) {
        synchronized(trava) {
            if (conn == orquestrador) {
                orquestrador = null
                onLog("Orquestrador (Linux) desconectado")
                if (ocupado) {
                    // Linux caiu no meio de um pedido: avisa o Totem e libera.
                    enviarStatusTotem("erro")
                    liberar()
                }
            } else if (conn == totemAtual) {
                totemAtual = null
                onLog("Totem desconectado")
            } else {
                onLog("Desconectado: ${conn.remoteSocketAddress}")
            }
        }
    }

    override fun onMessage(conn: WebSocket, message: String) {
        onLog("Recebido: $message")
        val json = JSONObject(message)
        when (json.optString("tipo")) {
            "comando" -> executarComando(conn, json)
            "registrar" -> registrar(conn, json)
            "pedido" -> receberPedido(conn, json)
            "status_tarefa" -> synchronized(trava) {
                if (json.optString("pedidoId") == pedidoAtual) {
                    enviarStatusTotem(json.optString("etapa"))
                }
            }
            "orquestrador_livre" -> synchronized(trava) {
                onLog("Robô livre para o próximo pedido")
                liberar()
            }
        }
    }

    private fun registrar(conn: WebSocket, json: JSONObject) {
        if (json.optString("papel") != "orquestrador") return
        synchronized(trava) {
            orquestrador = conn
            onLog("Orquestrador (Linux) registrado: ${conn.remoteSocketAddress}")
        }
    }

    private fun receberPedido(conn: WebSocket, json: JSONObject) {
        val pedidoId = json.optString("pedidoId")
        val produtoId = json.optInt("produtoId", -1)

        fun responder(etapa: String) {
            conn.send(JSONObject().apply {
                put("tipo", "status")
                put("pedidoId", pedidoId)
                put("etapa", etapa)
            }.toString())
            onLog("Enviado ao Totem: $etapa")
        }

        synchronized(trava) {
            val linux = orquestrador
            when {
                linux == null || !linux.isOpen -> {
                    onLog("Pedido $pedidoId recusado: orquestrador (Linux) não conectado")
                    responder("erro")
                }
                ocupado -> {
                    onLog("Pedido $pedidoId recusado: robô ocupado com $pedidoAtual")
                    responder("erro")
                }
                else -> {
                    ocupado = true
                    pedidoAtual = pedidoId
                    totemAtual = conn
                    responder("recebido")
                    linux.send(JSONObject().apply {
                        put("tipo", "tarefa")
                        put("pedidoId", pedidoId)
                        put("produtoId", produtoId)
                    }.toString())
                    onLog("Tarefa $pedidoId (produto $produtoId) enviada ao orquestrador")
                }
            }
        }
    }

    /** Chamar com a trava. */
    private fun enviarStatusTotem(etapa: String) {
        val totem = totemAtual ?: return
        if (!totem.isOpen) return
        totem.send(JSONObject().apply {
            put("tipo", "status")
            put("pedidoId", pedidoAtual)
            put("etapa", etapa)
        }.toString())
        onLog("Enviado ao Totem: $etapa")
    }

    /** Chamar com a trava. */
    private fun liberar() {
        ocupado = false
        pedidoAtual = null
        totemAtual = null
    }

    // {"tipo":"comando","comando":"ir_para"|"girar"|"girar_para"|"andar"|"pose", ...}
    //  ir_para: "local"; girar: "graus" (relativo); girar_para: "yaw" (rad, absoluto
    //  no mapa) + opcionais "tolerancia_graus" (1) e "aceitar_graus" (3); andar: "metros" (negativo = ré) + opcionais "velocidade", "antecipacao_m",
    //  "duracao_s", "yaw_rumo" (rad), "ganho_rumo", "seguranca" (DEFAULT/MEDIUM/HIGH,
    //  só durante o andar) e "timeout_s"; pose: devolve x, y, yaw; obstaculo: lê/define ("cm")
    //  a distância mínima a obstáculos e mostra a segurança atual.
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
            "pose" -> {
                val pose = executor.poseAtual()
                val resp = JSONObject().apply {
                    put("tipo", "comando_concluido")
                    put("comando", comando)
                    put("success", pose != null)
                    put("mensagem", if (pose != null) "ok" else "posição ainda desconhecida")
                    if (pose != null) {
                        put("x", pose.x.toDouble())
                        put("y", pose.y.toDouble())
                        put("yaw", pose.yaw.toDouble())
                        put("no_mapa", pose.isInMapArea ?: JSONObject.NULL)
                    }
                }
                conn.send(resp.toString())
                onLog("Enviado: $resp")
            }
            "obstaculo" -> {
                // Lê (e, se vier "cm", altera) a distância mínima a obstáculos
                // do Temi -- perto da prateleira ela pode bloquear o andar.
                val antes = try { executor.distanciaMinimaObstaculo() } catch (e: Exception) { -999 }
                val ret = if (json.has("cm")) {
                    try { executor.definirDistanciaMinimaObstaculo(json.getInt("cm")) } catch (e: Exception) { -999 }
                } else null
                val depois = try { executor.distanciaMinimaObstaculo() } catch (e: Exception) { -999 }
                val resp = JSONObject().apply {
                    put("tipo", "comando_concluido")
                    put("comando", comando)
                    put("success", true)
                    put("mensagem", "distância mínima: antes=$antes depois=$depois ret=$ret")
                    put("antes", antes)
                    put("depois", depois)
                    put("ret", ret ?: JSONObject.NULL)
                    put("seguranca", executor.seguranca())
                }
                conn.send(resp.toString())
                onLog("Enviado: $resp")
            }
            "girar_para" -> executor.girarPara(
                yawRad = json.optDouble("yaw").toFloat(),
                toleranciaGraus = json.optDouble("tolerancia_graus", 1.0).toFloat(),
                aceitarGraus = json.optDouble("aceitar_graus", 3.0).toFloat(),
                onFim = ::responder
            )
            "andar" -> executor.andarFrente(
                metros = json.optDouble("metros", 0.0).toFloat(),
                velocidade = json.optDouble(
                    "velocidade", TemiComandos.VELOCIDADE_ANDAR_PADRAO.toDouble()
                ).toFloat(),
                antecipacao = json.optDouble("antecipacao_m", 0.0).toFloat(),
                duracaoS = json.optDouble("duracao_s", 0.0).toFloat(),
                yawRumo = json.optDouble("yaw_rumo", Double.NaN).toFloat(),
                ganhoRumo = json.optDouble("ganho_rumo", 0.0).toFloat(),
                segurancaTemporaria = json.optString("seguranca", "").ifEmpty { null },
                timeoutS = json.optDouble("timeout_s", 0.0).toFloat(),
                onFim = ::responder
            )
            else -> responder(false, "comando desconhecido: '$comando'")
        }
    }

    override fun onError(conn: WebSocket?, ex: Exception) {
        onLog("Erro: ${ex.message}")
    }
}