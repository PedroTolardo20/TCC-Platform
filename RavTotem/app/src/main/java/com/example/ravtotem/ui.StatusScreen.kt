package com.example.ravtotem.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.material3.Button
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.example.ravtotem.data.Product

private val etapasPedido = listOf("recebido", "navegando", "chegou", "coletando", "concluido")

private val rotulos = mapOf(
    "recebido" to "Pedido recebido",
    "navegando" to "Robô a caminho do produto",
    "chegou" to "Robô chegou ao destino",
    "coletando" to "Coletando o produto",
    "concluido" to "Pedido concluído"
)

@Composable
fun StatusScreen(
    product: Product,
    etapa: String?,
    onNovoPedido: () -> Unit
) {
    val indiceAtual = etapasPedido.indexOf(etapa)
    val concluido = etapa == "concluido"
    val erro = etapa == "erro"
    val conectando = etapa == "conectando" || etapa == null

    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(32.dp)
    ) {
        Text(
            text = "Acompanhe seu pedido",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold
        )
        Spacer(Modifier.height(8.dp))
        Text(
            text = product.nome,
            style = MaterialTheme.typography.titleMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant
        )

        Spacer(Modifier.height(32.dp))

        when {
            erro -> Text(
                text = "Não foi possível conectar ao robô. Verifique a conexão e tente novamente.",
                style = MaterialTheme.typography.titleMedium,
                color = MaterialTheme.colorScheme.error
            )
            conectando -> Row(verticalAlignment = Alignment.CenterVertically) {
                CircularProgressIndicator(modifier = Modifier.size(20.dp), strokeWidth = 2.dp)
                Spacer(Modifier.width(12.dp))
                Text("Conectando ao robô...", style = MaterialTheme.typography.titleMedium)
            }
            else -> etapasPedido.forEachIndexed { index, chave ->
                EtapaItem(
                    texto = rotulos[chave] ?: chave,
                    concluida = index < indiceAtual,
                    atual = index == indiceAtual && !concluido,
                    ultimaConcluida = index == indiceAtual && concluido
                )
                Spacer(Modifier.height(20.dp))
            }
        }

        Spacer(Modifier.weight(1f))

        if (concluido || erro) {
            Button(
                onClick = onNovoPedido,
                modifier = Modifier.fillMaxWidth().height(56.dp)
            ) {
                Text(
                    text = if (erro) "Voltar" else "Novo pedido",
                    style = MaterialTheme.typography.titleMedium
                )
            }
        }
    }
}

@Composable
private fun EtapaItem(
    texto: String,
    concluida: Boolean,
    atual: Boolean,
    ultimaConcluida: Boolean
) {
    val ativa = concluida || atual || ultimaConcluida
    val cor = if (ativa) MaterialTheme.colorScheme.primary
    else MaterialTheme.colorScheme.outlineVariant

    Row(verticalAlignment = Alignment.CenterVertically) {
        Box(
            modifier = Modifier
                .size(20.dp)
                .clip(CircleShape)
                .background(cor)
        )
        Spacer(Modifier.width(16.dp))
        Text(
            text = texto,
            style = MaterialTheme.typography.titleMedium,
            fontWeight = if (atual) FontWeight.Bold else FontWeight.Normal,
            color = if (ativa) MaterialTheme.colorScheme.onSurface
            else MaterialTheme.colorScheme.onSurfaceVariant
        )
        if (atual) {
            Spacer(Modifier.width(12.dp))
            CircularProgressIndicator(modifier = Modifier.size(18.dp), strokeWidth = 2.dp)
        }
    }
}