package com.example.ravplatform.nav

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

interface NavegacaoController {
    // Executa a ida ao ponto e a coleta, reportando cada etapa via onEtapa.
    // No robô real: goTo() do Temi SDK + callback de chegada; coleta vem do Linux.
    fun executarPedido(pontoNavegacao: String, onEtapa: (String) -> Unit)
}

// Implementação SIMULADA para desenvolver/testar no emulador (sem o robô).
// No tablet do robô, troca por uma implementação que usa o Temi SDK de verdade.
class NavegacaoStub : NavegacaoController {
    private val escopo = CoroutineScope(Dispatchers.IO)

    override fun executarPedido(pontoNavegacao: String, onEtapa: (String) -> Unit) {
        escopo.launch {
            delay(2000); onEtapa("navegando")
            delay(2000); onEtapa("chegou")
            delay(2000); onEtapa("coletando")  // no real, vem do Linux
            delay(2000); onEtapa("concluido")  // no real, vem do Linux
        }
    }
}