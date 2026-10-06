package com.example.ravplatform.nav

import android.os.Handler
import android.os.Looper
import android.util.Log
import com.robotemi.sdk.Robot
import com.robotemi.sdk.listeners.OnGoToLocationStatusChangedListener
import com.robotemi.sdk.listeners.OnMovementStatusChangedListener
import com.robotemi.sdk.navigation.listener.OnCurrentPositionChangedListener
import com.robotemi.sdk.navigation.model.Position
import kotlin.math.abs
import kotlin.math.hypot

/**
 * Comandos de movimento avulsos do Temi, disparados pelo Linux via
 * RavWebSocketServer (mensagens tipo "comando") -- usados pelo teste de
 * alinhamento (rav_task/teste_alinhamento.py). Um comando por vez; cada um
 * chama onFim(sucesso, mensagem) exatamente uma vez quando termina.
 *
 * Independente do TemiNavegacao: os listeners daqui só reagem enquanto um
 * comando deste objeto está em andamento.
 */
class TemiComandos :
    OnGoToLocationStatusChangedListener,
    OnMovementStatusChangedListener,
    OnCurrentPositionChangedListener {

    private val robot: Robot = Robot.getInstance()
    private val handler = Handler(Looper.getMainLooper())

    private var onFim: ((Boolean, String) -> Unit)? = null
    private var localAtual: String? = null
    private var girando = false

    // Andar em linha reta: skidJoy em loop até a odometria do mapa mostrar
    // a distância pedida (o SDK não tem "anda X metros").
    private var posicaoAtual: Position? = null
    private var inicioAndar: Position? = null
    private var metrosAlvo = 0f
    private var velocidadeAndar = VELOCIDADE_ANDAR_PADRAO
    private var antecipacaoAndar = 0f
    private var porTempo = false
    private var prazoAndar = 0L

    init {
        robot.addOnGoToLocationStatusChangedListener(this)
        robot.addOnMovementStatusChangedListener(this)
        robot.addOnCurrentPositionChangedListener(this)
    }

    fun irPara(local: String, onFim: (Boolean, String) -> Unit) {
        if (!iniciar(onFim)) return
        localAtual = local
        Log.d(TAG, "goTo($local)")
        robot.goTo(local)
    }

    /** Gira no lugar; positivo = anti-horário (esquerda), visto de cima. */
    fun girar(graus: Int, onFim: (Boolean, String) -> Unit) {
        if (!iniciar(onFim)) return
        if (graus == 0) {
            terminar(true, "giro de 0 graus ignorado")
            return
        }
        girando = true
        Log.d(TAG, "turnBy($graus)")
        robot.turnBy(graus, VELOCIDADE_GIRO)
    }

    /**
     * Anda 'metros' para frente (sentido para onde o Temi está virado).
     * A posição do Temi chega atrasada e ele ainda desliza depois do
     * stopMovement, então:
     *  - duracaoS > 0: anda por tempo (distância curta, onde a posição
     *    atrasada não dá pra usar);
     *  - senão: para 'antecipacao' metros antes do alvo pela odometria.
     * Os dois parâmetros são calibrados do lado do Linux (teste_alinhamento.py).
     */
    fun andarFrente(
        metros: Float,
        velocidade: Float,
        antecipacao: Float,
        duracaoS: Float,
        onFim: (Boolean, String) -> Unit
    ) {
        if (!iniciar(onFim)) return
        if (metros <= 0f) {
            terminar(true, "distância 0 ignorada")
            return
        }
        val inicio = posicaoAtual
        if (inicio == null) {
            terminar(false, "posição do Temi ainda desconhecida (mapa carregado?)")
            return
        }
        inicioAndar = inicio
        metrosAlvo = metros
        velocidadeAndar = velocidade.coerceIn(0.05f, 1f)
        antecipacaoAndar = antecipacao.coerceAtLeast(0f)
        porTempo = duracaoS > 0f
        prazoAndar = System.currentTimeMillis() + if (porTempo) {
            (duracaoS * 1000).toLong()
        } else {
            ((metros / VELOCIDADE_ANDAR_MIN_M_S) * 1000).toLong() + 3000
        }
        Log.d(TAG, "andar $metros m (vel $velocidadeAndar, antecipação $antecipacaoAndar, " +
            "duração ${duracaoS}s) a partir de (${inicio.x}, ${inicio.y})")
        handler.post(passoAndar)
    }

    private val passoAndar = object : Runnable {
        override fun run() {
            val inicio = inicioAndar ?: return
            val andado = distanciaDesde(inicio)

            val chegou = if (porTempo) {
                System.currentTimeMillis() >= prazoAndar
            } else {
                andado >= metrosAlvo - antecipacaoAndar - TOLERANCIA_ANDAR_M
            }

            when {
                chegou -> {
                    pararAndar()
                    // Espera o Temi assentar e a posição atualizar pra medir
                    // onde ele realmente parou -- é esse número que serve
                    // pra calibrar a antecipação.
                    handler.postDelayed({
                        val distFinal = distanciaDesde(inicio)
                        terminar(
                            true,
                            "parou com %.3f m, final %.3f m (pedido %.3f m)"
                                .format(andado, distFinal, metrosAlvo)
                        )
                    }, ESPERA_ASSENTAR_MS)
                }
                System.currentTimeMillis() > prazoAndar -> {
                    pararAndar()
                    terminar(false, "timeout andando: %.3f de %.3f m".format(andado, metrosAlvo))
                }
                else -> {
                    // skidJoy só vale por um instante: tem que ser repetido.
                    robot.skidJoy(velocidadeAndar, 0f)
                    handler.postDelayed(this, PERIODO_SKIDJOY_MS)
                }
            }
        }
    }

    private fun distanciaDesde(inicio: Position): Float {
        val atual = posicaoAtual ?: inicio
        return hypot(atual.x - inicio.x, atual.y - inicio.y)
    }

    private fun pararAndar() {
        handler.removeCallbacks(passoAndar)
        inicioAndar = null
        robot.stopMovement()
    }

    override fun onCurrentPositionChanged(position: Position) {
        posicaoAtual = position
    }

    override fun onGoToLocationStatusChanged(
        location: String,
        status: String,
        descriptionId: Int,
        description: String
    ) {
        if (location != localAtual) return
        when (status) {
            OnGoToLocationStatusChangedListener.COMPLETE -> {
                localAtual = null
                terminar(true, "chegou em '$location'")
            }
            OnGoToLocationStatusChangedListener.ABORT -> {
                localAtual = null
                terminar(false, "goTo('$location') abortado: $description")
            }
        }
    }

    override fun onMovementStatusChanged(type: String, status: String) {
        if (!girando || type != OnMovementStatusChangedListener.TYPE_TURN_BY) return
        when (status) {
            OnMovementStatusChangedListener.STATUS_COMPLETE -> {
                girando = false
                terminar(true, "giro concluído")
            }
            OnMovementStatusChangedListener.STATUS_ABORT -> {
                girando = false
                terminar(false, "turnBy abortado")
            }
        }
    }

    private fun iniciar(onFim: (Boolean, String) -> Unit): Boolean {
        if (this.onFim != null) {
            onFim(false, "outro comando ainda em andamento")
            return false
        }
        this.onFim = onFim
        return true
    }

    private fun terminar(sucesso: Boolean, mensagem: String) {
        Log.d(TAG, "fim: sucesso=$sucesso $mensagem")
        val callback = onFim
        onFim = null
        callback?.invoke(sucesso, mensagem)
    }

    fun encerrar() {
        pararAndar()
        robot.removeOnGoToLocationStatusChangedListener(this)
        robot.removeOnMovementStatusChangedListener(this)
        robot.removeOnCurrentPositionChangedListener(this)
    }

    companion object {
        private const val TAG = "TemiComandos"
        private const val VELOCIDADE_GIRO = 0.5f

        // skidJoy vai de -1 a 1. Padrão se o comando não mandar velocidade.
        const val VELOCIDADE_ANDAR_PADRAO = 0.2f
        private const val ESPERA_ASSENTAR_MS = 2000L
        // Usado só pro timeout (estimativa conservadora da velocidade real).
        private const val VELOCIDADE_ANDAR_MIN_M_S = 0.03f
        private const val PERIODO_SKIDJOY_MS = 100L
        private const val TOLERANCIA_ANDAR_M = 0.005f
    }
}
