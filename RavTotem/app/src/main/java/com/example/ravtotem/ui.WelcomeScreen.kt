package com.example.ravtotem.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.example.ravtotem.R
import com.example.ravtotem.ui.components.FuturisticBackground
import com.example.ravtotem.ui.components.RavRobotGlow
import com.example.ravtotem.ui.theme.NeonCyan
import com.example.ravtotem.ui.theme.TextSecondary

@Composable
fun WelcomeScreen(
    onStartOrder: () -> Unit
) {
    FuturisticBackground {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(32.dp),
            horizontalAlignment = Alignment.CenterHorizontally
        ) {
            // Selo da FEI: arte neon já com traço grosso (legível mesmo com
            // o texto "centro universitário" incluso).
            Image(
                painter = painterResource(id = R.drawable.logo_fei),
                contentDescription = "Centro Universitário FEI",
                modifier = Modifier
                    .align(Alignment.End)
                    .height(88.dp)
                    .aspectRatio(886f / 729f)
            )

            Spacer(Modifier.weight(1f))

            RavRobotGlow()

            Spacer(Modifier.height(40.dp))

            Text(
                text = "R A F",
                style = MaterialTheme.typography.displaySmall,
                color = MaterialTheme.colorScheme.onBackground,
                textAlign = TextAlign.Center
            )

            Spacer(Modifier.height(8.dp))

            Text(
                text = "Robô Autônomo de Farmácia",
                style = MaterialTheme.typography.titleMedium,
                color = TextSecondary,
                textAlign = TextAlign.Center
            )

            Spacer(Modifier.height(4.dp))

            Text(
                text = "Trabalho de conclusão de curso",
                style = MaterialTheme.typography.labelLarge,
                color = TextSecondary.copy(alpha = 0.7f),
                textAlign = TextAlign.Center
            )

            Spacer(Modifier.weight(1f))
            Spacer(Modifier.height(28.dp))

            Button(
                onClick = onStartOrder,
                colors = ButtonDefaults.buttonColors(
                    containerColor = NeonCyan,
                    contentColor = MaterialTheme.colorScheme.onPrimary
                ),
                shape = RoundedCornerShape(16.dp),
                modifier = Modifier
                    .fillMaxWidth()
                    .height(60.dp)
            ) {
                Text(
                    text = "FAZER PEDIDO",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}
