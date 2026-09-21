package com.example.ravplatform.nav

import android.util.Log
import com.example.ravplatform.network.StartTaskClient
import com.robotemi.sdk.Robot
import com.robotemi.sdk.listeners.OnGoToLocationStatusChangedListener
import com.robotemi.sdk.listeners.OnRobotReadyListener

// URL do servidor WebSocket do start_task (Linux/ROS2), aberto pelo
// start_task.launch.py na porta 8766. TROCAR pelo IP real do computador do
// robô na rede local antes de rodar de verdade.
private const val URL_START_TASK = "ws://SEU_IP_DO_LINUX:8766"

private enum class Fase {
    OCIOSO, INDO_COLETA, COLETANDO, INDO_ENTREGA, ENTREGANDO
}

/**
 * Implementação real do NavegacaoController usando o Temi SDK + start_task.
 * Substitui o NavegacaoStub quando o app roda dentro do app da temi.
 *
 * Fluxo: goTo(coleta) -> "navegando"/"chegou" -> abre StartTaskClient (manda
 * classeYolo + chegou_pickup) -> "coletando" -> aguarda pick_concluido ->
 * goTo(entrega) (silencioso, continua em "coletando") -> chegou -> manda
 * chegou_place -> aguarda place_concluido -> "concluido" (ou "erro" em
 * qualquer falha no caminho).
 */
class TemiNavegacao :
    NavegacaoController,
    OnGoToLocationStatusChangedListener,
    OnRobotReadyListener {

    private val robot: Robot = Robot.getInstance()

    private var pontoAtual: String? = null
    private var onEtapaAtual: ((String) -> Unit)? = null
    private var ultimaEtapa: String? = null

    private var fase: Fase = Fase.OCIOSO
    private var classeYoloAtual: String? = null
    private var pontoEntregaAtual: String? = null
    private var startTask: StartTaskClient? = null

    init {
        robot.addOnRobotReadyListener(this)
        robot.addOnGoToLocationStatusChangedListener(this)
    }

    override fun executarPedido(
        pontoColeta: String,
        classeYolo: String,
        pontoEntrega: String,
        onEtapa: (String) -> Unit
    ) {
        onEtapaAtual = onEtapa
        classeYoloAtual = classeYolo
        pontoEntregaAtual = pontoEntrega
        ultimaEtapa = null
        fase = Fase.INDO_COLETA
        pontoAtual = pontoColeta
        Log.d(TAG, "Enviando temi para coleta: $pontoColeta")
        robot.goTo(pontoColeta)
    }

    override fun onGoToLocationStatusChanged(
        location: String,
        status: String,
        descriptionId: Int,
        description: String
    ) {
        Log.d(TAG, "Status goTo: local=$location status=$status fase=$fase")

        if (location != pontoAtual) return

        when (status) {
            OnGoToLocationStatusChangedListener.START,
            OnGoToLocationStatusChangedListener.CALCULATING,
            OnGoToLocationStatusChangedListener.GOING -> {
                // Só reporta "navegando" na perna de coleta -- a perna até o
                // local de entrega fica escondida dentro de "coletando"
                // pra não mudar o contrato de etapas que o Totem já entende.
                if (fase == Fase.INDO_COLETA) reportar("navegando")
            }

            OnGoToLocationStatusChangedListener.COMPLETE -> when (fase) {
                Fase.INDO_COLETA -> {
                    reportar("chegou")
                    iniciarColeta()
                }
                Fase.INDO_ENTREGA -> {
                    fase = Fase.ENTREGANDO
                    startTask?.enviarChegouPlace()
                }
                else -> Unit
            }

            OnGoToLocationStatusChangedListener.ABORT ->
                falhar("navegação abortada em '$location'")
        }
    }

    private fun iniciarColeta() {
        fase = Fase.COLETANDO
        reportar("coletando")

        val classeYolo = classeYoloAtual
        if (classeYolo == null) {
            falhar("classeYolo não definida")
            return
        }

        startTask = StartTaskClient(
            urlServidor = URL_START_TASK,
            classeYolo = classeYolo,
            onLog = { linha -> Log.d(TAG, linha) },
            onPickConcluido = { sucesso, mensagem ->
                if (sucesso) irParaEntrega() else falhar("pick falhou: $mensagem")
            },
            onPlaceConcluido = { sucesso, mensagem ->
                if (sucesso) reportar("concluido") else falhar("place falhou: $mensagem")
                encerrarStartTask()
            },
            onErro = { mensagem -> falhar("start_task: $mensagem") }
        ).apply { connect() }
    }

    private fun irParaEntrega() {
        val pontoEntrega = pontoEntregaAtual
        if (pontoEntrega == null) {
            falhar("ponto de entrega não definido")
            return
        }
        fase = Fase.INDO_ENTREGA
        pontoAtual = pontoEntrega
        Log.d(TAG, "Enviando temi para entrega: $pontoEntrega")
        robot.goTo(pontoEntrega)
    }

    private fun reportar(etapa: String) {
        if (etapa == ultimaEtapa) return
        ultimaEtapa = etapa
        onEtapaAtual?.invoke(etapa)
    }

    private fun falhar(motivo: String) {
        Log.e(TAG, "Pedido falhou: $motivo")
        reportar("erro")
        fase = Fase.OCIOSO
        encerrarStartTask()
    }

    private fun encerrarStartTask() {
        try {
            startTask?.close()
        } catch (_: Exception) {
        }
        startTask = null
    }

    override fun onRobotReady(isReady: Boolean) {
        Log.d(TAG, "Robot pronto: $isReady")
    }

    /** Chamar quando o servidor for desligado, para remover os listeners. */
    fun encerrar() {
        robot.removeOnGoToLocationStatusChangedListener(this)
        robot.removeOnRobotReadyListener(this)
        encerrarStartTask()
    }

    companion object {
        private const val TAG = "TemiNavegacao"
    }
}
