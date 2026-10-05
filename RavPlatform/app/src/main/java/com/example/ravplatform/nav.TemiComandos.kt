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

    /** Anda 'metros' para frente (sentido para onde o Temi está virado). */
    fun andarFrente(metros: Float, onFim: (Boolean, String) -> Unit) {
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
        prazoAndar = System.currentTimeMillis() +
            ((metros / VELOCIDADE_ANDAR_MIN_M_S) * 1000).toLong() + 3000
        Log.d(TAG, "andar $metros m a partir de (${inicio.x}, ${inicio.y})")
        handler.post(passoAndar)
    }

    private val passoAndar = object : Runnable {
        override fun run() {
            val inicio = inicioAndar ?: return
            val atual = posicaoAtual ?: inicio
            val andado = hypot(atual.x - inicio.x, atual.y - inicio.y)

            when {
                andado >= metrosAlvo - TOLERANCIA_ANDAR_M -> {
                    pararAndar()
                    terminar(true, "andou %.3f m (pedido %.3f m)".format(andado, metrosAlvo))
                }
                System.currentTimeMillis() > prazoAndar -> {
                    pararAndar()
                    terminar(false, "timeout andando: %.3f de %.3f m".format(andado, metrosAlvo))
                }
                else -> {
                    // skidJoy só vale por um instante: tem que ser repetido.
                    robot.skidJoy(VELOCIDADE_ANDAR, 0f)
                    handler.postDelayed(this, PERIODO_SKIDJOY_MS)
                }
            }
        }
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

        // skidJoy vai de -1 a 1; baixo pra não passar do ponto em
        // distâncias de poucos centímetros.
        private const val VELOCIDADE_ANDAR = 0.2f
        // Usado só pro timeout (estimativa conservadora da velocidade real).
        private const val VELOCIDADE_ANDAR_MIN_M_S = 0.03f
        private const val PERIODO_SKIDJOY_MS = 100L
        private const val TOLERANCIA_ANDAR_M = 0.005f
    }
}
