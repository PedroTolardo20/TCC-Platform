package com.example.ravplatform.nav

import android.os.Handler
import android.os.Looper
import android.util.Log
import com.robotemi.sdk.Robot
import com.robotemi.sdk.listeners.OnGoToLocationStatusChangedListener
import com.robotemi.sdk.listeners.OnMovementStatusChangedListener
import com.robotemi.sdk.navigation.listener.OnCurrentPositionChangedListener
import com.robotemi.sdk.navigation.model.Position
import com.robotemi.sdk.navigation.model.SafetyLevel
import kotlin.math.PI
import kotlin.math.abs
import kotlin.math.hypot
import kotlin.math.roundToInt

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
    // Manter rumo enquanto anda: yaw absoluto (rad, mapa) a seguir, e ganho
    // rad de erro -> comando angular do skidJoy. NaN = não corrige.
    private var yawRumo = Float.NaN
    private var ganhoRumo = 0f
    // Segurança de navegação original, restaurada quando o andar termina
    // (null = o andar não mexeu nela).
    private var segurancaOriginal: SafetyLevel? = null

    // Girar até um yaw absoluto do mapa (malha fechada: turnBy + confere).
    private var girandoPara = false
    private var yawAlvo = 0f
    private var tentativasGiro = 0
    private var toleranciaGiroGraus = 1f
    private var aceitarGiroGraus = 3f

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

    /** Pose atual no mapa (x, y em m; yaw em rad), ou null se desconhecida. */
    fun poseAtual(): Position? = poseAgora()

    fun distanciaMinimaObstaculo(): Int = robot.minimumObstacleDistance

    /** Retorna o código de retorno do serviço do Temi (0 = ok, se seguir o padrão). */
    fun definirDistanciaMinimaObstaculo(cm: Int): Int {
        robot.minimumObstacleDistance = cm
        return robot.minimumObstacleDistance
    }

    fun seguranca(): String = try { robot.navigationSafety.toString() } catch (e: Exception) { "?" }

    /**
     * Consulta a pose direto no serviço do Temi (getPosition). O listener
     * OnCurrentPositionChangedListener só dispara com o robô andando --
     * parado ficava em (0, 0, 0). Se a consulta falhar ou vier zerada,
     * usa a última recebida pelo listener.
     */
    private fun poseAgora(): Position? {
        val consultada = try {
            robot.getPosition()
        } catch (e: Exception) {
            Log.w(TAG, "getPosition falhou: ${e.message}")
            null
        }
        if (consultada != null &&
            (consultada.x != 0f || consultada.y != 0f || consultada.yaw != 0f)
        ) {
            posicaoAtual = consultada
        }
        return posicaoAtual
    }

    /**
     * Gira até o yaw ABSOLUTO 'yawRad' do mapa: turnBy pelo erro, espera a
     * pose atualizar, confere e repete até |erro| <= toleranciaGraus.
     * Diferente do girar(): não acumula erro de giros anteriores.
     *
     * turnBy de 1-2° é impreciso (o Temi oscila em volta do alvo), então
     * depois de MAX_TENTATIVAS_GIRO aceita o que tiver se |erro| <=
     * aceitarGraus -- quem chama mede o yaw de novo e compensa o resto.
     */
    fun girarPara(
        yawRad: Float,
        toleranciaGraus: Float,
        aceitarGraus: Float,
        onFim: (Boolean, String) -> Unit
    ) {
        if (!iniciar(onFim)) return
        if (poseAgora() == null) {
            terminar(false, "posição do Temi ainda desconhecida (mapa carregado?)")
            return
        }
        yawAlvo = yawRad
        toleranciaGiroGraus = toleranciaGraus
        aceitarGiroGraus = maxOf(aceitarGraus, toleranciaGraus)
        tentativasGiro = 0
        girandoPara = true
        handler.post(passoGirarPara)
    }

    private val passoGirarPara = Runnable {
        val yaw = poseAgora()?.yaw ?: return@Runnable
        val erroGraus = Math.toDegrees(normalizar(yawAlvo - yaw).toDouble()).toFloat()
        when {
            abs(erroGraus) <= toleranciaGiroGraus -> {
                girandoPara = false
                terminar(true, "yaw %.4f rad (alvo %.4f, erro %.1f°, %d giro(s))"
                    .format(yaw, yawAlvo, erroGraus, tentativasGiro))
            }
            tentativasGiro >= MAX_TENTATIVAS_GIRO -> {
                girandoPara = false
                val aceitou = abs(erroGraus) <= aceitarGiroGraus
                terminar(aceitou, "yaw %.4f rad (alvo %.4f, erro %.1f° após %d giros%s)"
                    .format(yaw, yawAlvo, erroGraus, tentativasGiro,
                        if (aceitou) ", aceito" else " -- acima de %.1f°".format(aceitarGiroGraus)))
            }
            else -> {
                tentativasGiro++
                // turnBy só aceita graus inteiros; erro < 1° arredondaria pra 0.
                var graus = erroGraus.roundToInt()
                if (graus == 0) graus = if (erroGraus > 0) 1 else -1
                Log.d(TAG, "girarPara: erro $erroGraus° -> turnBy($graus)")
                girando = true
                robot.turnBy(graus, VELOCIDADE_GIRO)
            }
        }
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
        yawRumo: Float,
        ganhoRumo: Float,
        segurancaTemporaria: String?,
        timeoutS: Float,
        onFim: (Boolean, String) -> Unit
    ) {
        if (!iniciar(onFim)) return
        if (metros <= 0f) {
            terminar(true, "distância 0 ignorada")
            return
        }
        val inicio = poseAgora()
        if (inicio == null) {
            terminar(false, "posição do Temi ainda desconhecida (mapa carregado?)")
            return
        }
        inicioAndar = inicio
        metrosAlvo = metros
        velocidadeAndar = velocidade.coerceIn(0.05f, 1f)
        antecipacaoAndar = antecipacao.coerceAtLeast(0f)
        porTempo = duracaoS > 0f
        this.yawRumo = yawRumo
        this.ganhoRumo = ganhoRumo
        if (!segurancaTemporaria.isNullOrEmpty()) {
            // Em HIGH o Temi se recusa a andar em direção à prateleira
            // (andou 4 mm de 15 cm pedidos); só o avanço final pede isso.
            try {
                val nivel = SafetyLevel.valueOf(segurancaTemporaria.uppercase())
                segurancaOriginal = robot.navigationSafety
                robot.navigationSafety = nivel
                Log.d(TAG, "segurança $segurancaOriginal -> $nivel durante o andar")
            } catch (e: Exception) {
                Log.w(TAG, "segurança '$segurancaTemporaria' inválida: ${e.message}")
            }
        }
        prazoAndar = System.currentTimeMillis() + when {
            porTempo -> (duracaoS * 1000).toLong()
            // Prazo explícito: perto de obstáculo o Temi anda bem mais devagar
            // que o normal (freia), e o padrão abaixo desistiria antes.
            timeoutS > 0f -> (timeoutS * 1000).toLong()
            else -> ((metros / VELOCIDADE_ANDAR_MIN_M_S) * 1000).toLong() + 3000
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
                desviouDoRumo() -> {
                    pararAndar()
                    terminar(false, "desviou mais de %.0f° do rumo andando -- sinal do ganho_rumo invertido?"
                        .format(DESVIO_MAX_RUMO_GRAUS))
                }
                else -> {
                    // skidJoy só vale por um instante: tem que ser repetido.
                    robot.skidJoy(velocidadeAndar, correcaoRumo())
                    handler.postDelayed(this, PERIODO_SKIDJOY_MS)
                }
            }
        }
    }

    private fun erroRumo(): Float? {
        if (yawRumo.isNaN()) return null
        val yaw = poseAgora()?.yaw ?: return null
        return normalizar(yawRumo - yaw)
    }

    /** Comando angular do skidJoy pra voltar pro rumo (proporcional, limitado). */
    private fun correcaoRumo(): Float {
        val erro = erroRumo() ?: return 0f
        return (ganhoRumo * erro).coerceIn(-ANGULAR_MAX_RUMO, ANGULAR_MAX_RUMO)
    }

    private fun desviouDoRumo(): Boolean {
        val erro = erroRumo() ?: return false
        return abs(Math.toDegrees(erro.toDouble())) > DESVIO_MAX_RUMO_GRAUS
    }

    /** Ângulo em (-pi, pi]. */
    private fun normalizar(rad: Float): Float {
        var a = rad
        while (a > PI) a -= (2 * PI).toFloat()
        while (a <= -PI) a += (2 * PI).toFloat()
        return a
    }

    private fun distanciaDesde(inicio: Position): Float {
        val atual = poseAgora() ?: inicio
        return hypot(atual.x - inicio.x, atual.y - inicio.y)
    }

    private fun pararAndar() {
        handler.removeCallbacks(passoAndar)
        inicioAndar = null
        robot.stopMovement()
        segurancaOriginal?.let {
            robot.navigationSafety = it
            Log.d(TAG, "segurança restaurada para $it")
        }
        segurancaOriginal = null
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
                if (girandoPara) {
                    // Espera a pose do mapa refletir o giro antes de conferir.
                    handler.postDelayed(passoGirarPara, ESPERA_YAW_MS)
                } else {
                    terminar(true, "giro concluído")
                }
            }
            OnMovementStatusChangedListener.STATUS_ABORT -> {
                girando = false
                girandoPara = false
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

        private const val MAX_TENTATIVAS_GIRO = 5
        private const val ESPERA_YAW_MS = 800L
        private const val ANGULAR_MAX_RUMO = 0.3f
        private const val DESVIO_MAX_RUMO_GRAUS = 15.0
    }
}
