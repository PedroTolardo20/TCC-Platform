package com.example.ravplatform.nav

import android.util.Log
import com.robotemi.sdk.Robot
import com.robotemi.sdk.listeners.OnGoToLocationStatusChangedListener
import com.robotemi.sdk.listeners.OnRobotReadyListener

/**
 * Implementação real do NavegacaoController usando o Temi SDK.
 * Substitui o NavegacaoStub quando o app roda dentro do app da temi.
 *
 * Mapeia o status do goTo da temi para as etapas do nosso contrato:
 *   start / calculating / going -> "navegando"
 *   complete                    -> "chegou"
 *   abort                       -> "erro"
 *
 * As etapas "coletando" e "concluido" NÃO saem daqui — virão
 * do manipulador (Linux / ROS 2) numa etapa futura.
 */
class TemiNavegacao :
    NavegacaoController,
    OnGoToLocationStatusChangedListener,
    OnRobotReadyListener {

    private val robot: Robot = Robot.getInstance()

    private var pontoAtual: String? = null
    private var onEtapaAtual: ((String) -> Unit)? = null
    private var ultimaEtapa: String? = null

    init {
        robot.addOnRobotReadyListener(this)
        robot.addOnGoToLocationStatusChangedListener(this)
    }

    override fun executarPedido(pontoNavegacao: String, onEtapa: (String) -> Unit) {
        pontoAtual = pontoNavegacao
        onEtapaAtual = onEtapa
        ultimaEtapa = null
        Log.d(TAG, "Enviando temi para: $pontoNavegacao")
        robot.goTo(pontoNavegacao)
    }

    override fun onGoToLocationStatusChanged(
        location: String,
        status: String,
        descriptionId: Int,
        description: String
    ) {
        Log.d(TAG, "Status goTo: local=$location status=$status descId=$descriptionId desc=$description")

        if (location != pontoAtual) return

        val etapa = when (status) {
            OnGoToLocationStatusChangedListener.START,
            OnGoToLocationStatusChangedListener.CALCULATING,
            OnGoToLocationStatusChangedListener.GOING -> "navegando"
            OnGoToLocationStatusChangedListener.COMPLETE -> "chegou"
            OnGoToLocationStatusChangedListener.ABORT -> "erro"
            else -> null
        }

        if (etapa != null && etapa != ultimaEtapa) {
            ultimaEtapa = etapa
            onEtapaAtual?.invoke(etapa)
        }
    }

    override fun onRobotReady(isReady: Boolean) {
        Log.d(TAG, "Robot pronto: $isReady")
    }

    /** Chamar quando o servidor for desligado, para remover os listeners. */
    fun encerrar() {
        robot.removeOnGoToLocationStatusChangedListener(this)
        robot.removeOnRobotReadyListener(this)
    }

    companion object {
        private const val TAG = "TemiNavegacao"
    }
}