package com.example.ravtotem.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
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
import com.example.ravtotem.ui.components.FuturisticBackground
import com.example.ravtotem.ui.components.RavRobotGlow
import com.example.ravtotem.ui.theme.ErrorNeon
import com.example.ravtotem.ui.theme.NeonCyan
import com.example.ravtotem.ui.theme.SpaceOutline
import com.example.ravtotem.ui.theme.SuccessNeon
import com.example.ravtotem.ui.theme.TextSecondary

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

    FuturisticBackground {
        Row(
            modifier = Modifier
                .fillMaxSize()
                .padding(32.dp)
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    text = "ACOMPANHAMENTO",
                    style = MaterialTheme.typography.labelLarge,
                    color = NeonCyan
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text = product.nome,
                    style = MaterialTheme.typography.headlineSmall,
                    color = MaterialTheme.colorScheme.onBackground,
                    fontWeight = FontWeight.Bold
                )

                Spacer(Modifier.height(40.dp))

                when {
                    erro -> Text(
                        text = "Não foi possível conectar ao robô. Verifique a conexão e tente novamente.",
                        style = MaterialTheme.typography.titleMedium,
                        color = ErrorNeon
                    )
                    conectando -> Row(verticalAlignment = Alignment.CenterVertically) {
                        CircularProgressIndicator(
                            modifier = Modifier.size(20.dp),
                            strokeWidth = 2.dp,
                            color = NeonCyan
                        )
                        Spacer(Modifier.width(12.dp))
                        Text(
                            "Conectando ao robô...",
                            style = MaterialTheme.typography.titleMedium,
                            color = MaterialTheme.colorScheme.onBackground
                        )
                    }
                    else -> etapasPedido.forEachIndexed { index, chave ->
                        EtapaItem(
                            texto = rotulos[chave] ?: chave,
                            concluida = index < indiceAtual,
                            atual = index == indiceAtual && !concluido,
                            ultimaConcluida = index == indiceAtual && concluido,
                            ultimaEtapa = index == etapasPedido.lastIndex
                        )
                    }
                }

                Spacer(Modifier.weight(1f))

                if (concluido || erro) {
                    Button(
                        onClick = onNovoPedido,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = if (erro) ErrorNeon else NeonCyan,
                            contentColor = MaterialTheme.colorScheme.onPrimary
                        ),
                        shape = RoundedCornerShape(16.dp),
                        modifier = Modifier.fillMaxWidth().height(60.dp)
                    ) {
                        Text(
                            text = if (erro) "VOLTAR" else "NOVO PEDIDO",
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }

            Spacer(Modifier.width(24.dp))

            RavRobotGlow(
                modifier = Modifier
                    .weight(0.9f)
                    .fillMaxHeight(),
                robotHeight = 440.dp,
                glowSize = 520.dp
            )
        }
    }
}

@Composable
private fun EtapaItem(
    texto: String,
    concluida: Boolean,
    atual: Boolean,
    ultimaConcluida: Boolean,
    ultimaEtapa: Boolean
) {
    val ativa = concluida || atual || ultimaConcluida
    val corPonto = when {
        ultimaConcluida -> SuccessNeon
        ativa -> NeonCyan
        else -> SpaceOutline
    }

    Row(verticalAlignment = Alignment.Top) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Box(
                modifier = Modifier
                    .size(18.dp)
                    .clip(CircleShape)
                    .background(corPonto)
            )
            if (!ultimaEtapa) {
                Box(
                    modifier = Modifier
                        .width(2.dp)
                        .height(36.dp)
                        .background(if (concluida) NeonCyan else SpaceOutline)
                )
            }
        }
        Spacer(Modifier.width(16.dp))
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.padding(bottom = if (ultimaEtapa) 0.dp else 18.dp)
        ) {
            Text(
                text = texto,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = if (atual) FontWeight.Bold else FontWeight.Normal,
                color = if (ativa) MaterialTheme.colorScheme.onBackground else TextSecondary
            )
            if (atual) {
                Spacer(Modifier.width(12.dp))
                CircularProgressIndicator(modifier = Modifier.size(16.dp), strokeWidth = 2.dp, color = NeonCyan)
            }
        }
    }
}
