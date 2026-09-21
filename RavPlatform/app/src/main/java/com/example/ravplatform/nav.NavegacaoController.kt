package com.example.ravplatform.nav

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

interface NavegacaoController {
    // Vai até o ponto de coleta, aciona o pick (via start_task, no Linux),
    // vai até o ponto de entrega e aciona o place -- reportando cada etapa
    // via onEtapa. No robô real: goTo() do Temi SDK pras duas pernas de
    // navegação; pick/place vêm do start_task (ROS2) por WebSocket.
    fun executarPedido(
        pontoColeta: String,
        classeYolo: String,
        pontoEntrega: String,
        onEtapa: (String) -> Unit
    )
}

// Implementação SIMULADA para desenvolver/testar no emulador (sem o robô).
// No tablet do robô, troca por uma implementação que usa o Temi SDK de verdade.
class NavegacaoStub : NavegacaoController {
    private val escopo = CoroutineScope(Dispatchers.IO)

    override fun executarPedido(
        pontoColeta: String,
        classeYolo: String,
        pontoEntrega: String,
        onEtapa: (String) -> Unit
    ) {
        escopo.launch {
            delay(2000); onEtapa("navegando")
            delay(2000); onEtapa("chegou")
            delay(2000); onEtapa("coletando")  // no real: cam_pose + pick_from_vision
            delay(2000); onEtapa("coletando")  // no real: 2a perna até o place
            delay(2000); onEtapa("concluido")  // no real: place concluído
        }
    }
}
