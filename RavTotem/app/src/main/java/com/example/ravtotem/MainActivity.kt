package com.example.ravtotem

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import com.example.ravtotem.data.Product
import com.example.ravtotem.data.mockProducts
import com.example.ravtotem.network.TotemWebSocketClient
import com.example.ravtotem.ui.ProductSelectionScreen
import com.example.ravtotem.ui.StatusScreen
import com.example.ravtotem.ui.WelcomeScreen
import com.example.ravtotem.ui.theme.RavTotemTheme

class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            RavTotemTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    RavTotemApp()
                }
            }
        }
    }
}

enum class Tela {
    BOAS_VINDAS,
    PRODUTOS,
    STATUS
}

// IP do servidor do Platform. No emulador, 10.0.2.2 = a máquina host (seu Mac).
// No tablet real, troque pelo IP do tablet do Platform na rede local.
private const val URL_SERVIDOR = "ws://192.168.50.137:8765"

@Composable
fun RavTotemApp() {
    var telaAtual by remember { mutableStateOf(Tela.BOAS_VINDAS) }
    var produtoSelecionado by remember { mutableStateOf<Product?>(null) }

    val client = remember { TotemWebSocketClient(URL_SERVIDOR) }
    val etapa by client.etapa.collectAsState()

    when (telaAtual) {
        Tela.BOAS_VINDAS -> WelcomeScreen(
            onStartOrder = {
                produtoSelecionado = null
                telaAtual = Tela.PRODUTOS
            }
        )

        Tela.PRODUTOS -> ProductSelectionScreen(
            products = mockProducts,
            selectedProduct = produtoSelecionado,
            onProductClick = { produto ->
                produtoSelecionado = if (produtoSelecionado == produto) null else produto
            },
            onFinalizar = {
                produtoSelecionado?.let { client.enviarPedido(it.id) }
                telaAtual = Tela.STATUS
            }
        )

        Tela.STATUS -> produtoSelecionado?.let { produto ->
            StatusScreen(
                product = produto,
                etapa = etapa,
                onNovoPedido = {
                    client.fechar()
                    produtoSelecionado = null
                    telaAtual = Tela.BOAS_VINDAS
                }
            )
        }
    }
}