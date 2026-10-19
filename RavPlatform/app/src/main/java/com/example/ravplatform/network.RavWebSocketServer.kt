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

    // {"tipo":"comando","comando":"ir_para"|"girar"|"girar_para"|"andar"|"pose", ...}
    //  ir_para: "local"; girar: "graus" (relativo); girar_para: "yaw" (rad, absoluto
    //  no mapa) + opcionais "tolerancia_graus" (1) e "aceitar_graus" (3); andar: "metros" + opcionais "velocidade", "antecipacao_m",
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