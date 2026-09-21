package com.example.ravplatform

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.lazy.rememberLazyListState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontFamily
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
//import com.example.ravplatform.nav.NavegacaoStub
import com.example.ravplatform.nav.TemiNavegacao
import com.example.ravplatform.network.RavWebSocketServer
import com.example.ravplatform.ui.components.FuturisticBackground
import com.example.ravplatform.ui.theme.NeonCyan
import com.example.ravplatform.ui.theme.RavPlatformTheme
import com.example.ravplatform.ui.theme.SpaceOutline
import com.example.ravplatform.ui.theme.SpaceSurface
import com.example.ravplatform.ui.theme.SuccessNeon
import com.example.ravplatform.ui.theme.TextSecondary
import kotlinx.coroutines.flow.MutableStateFlow

private const val PORTA_SERVIDOR = 8765

class MainActivity : ComponentActivity() {

    private val logs = MutableStateFlow<List<String>>(emptyList())
    private var servidor: RavWebSocketServer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        servidor = RavWebSocketServer(
            porta = PORTA_SERVIDOR,
            navegacao = TemiNavegacao(),
            onLog = { linha -> logs.value = logs.value + linha }
        ).apply {
            isReuseAddr = true
            start()
        }

        setContent {
            RavPlatformTheme {
                val linhas by logs.collectAsState()
                TelaServidor(logs = linhas, porta = PORTA_SERVIDOR)
            }
        }
    }

    override fun onDestroy() {
        super.onDestroy()
        try {
            servidor?.stop()
        } catch (_: Exception) {
        }
    }
}

@Composable
fun TelaServidor(logs: List<String>, porta: Int) {
    FuturisticBackground {
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(24.dp)
        ) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Image(
                    painter = painterResource(id = R.drawable.ic_rav_robot),
                    contentDescription = "Robô RAF",
                    modifier = Modifier.height(56.dp)
                )
                Spacer(Modifier.width(16.dp))
                Column {
                    Text(
                        text = "RAF",
                        style = MaterialTheme.typography.labelLarge,
                        color = NeonCyan
                    )
                    Text(
                        text = "Servidor de Navegação",
                        style = MaterialTheme.typography.headlineSmall,
                        color = MaterialTheme.colorScheme.onBackground,
                        fontWeight = FontWeight.Bold
                    )
                }
                Spacer(Modifier.weight(1f))
                StatusPill(porta = porta)
            }

            Spacer(Modifier.height(20.dp))

            Box(
                modifier = Modifier
                    .fillMaxSize()
                    .clip(RoundedCornerShape(16.dp))
                    .background(SpaceSurface)
                    .border(1.dp, SpaceOutline, RoundedCornerShape(16.dp))
                    .padding(16.dp)
            ) {
                val listState = rememberLazyListState()
                LaunchedEffect(logs.size) {
                    if (logs.isNotEmpty()) listState.animateScrollToItem(logs.size - 1)
                }
                LazyColumn(state = listState) {
                    items(logs) { linha ->
                        Text(
                            text = linha,
                            style = MaterialTheme.typography.bodyLarge,
                            fontFamily = FontFamily.Monospace,
                            color = TextSecondary,
                            modifier = Modifier.padding(vertical = 3.dp)
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun StatusPill(porta: Int) {
    Row(
        verticalAlignment = Alignment.CenterVertically,
        modifier = Modifier
            .clip(RoundedCornerShape(20.dp))
            .background(SpaceSurface)
            .border(1.dp, SpaceOutline, RoundedCornerShape(20.dp))
            .padding(horizontal = 14.dp, vertical = 8.dp)
    ) {
        Box(
            modifier = Modifier
                .size(8.dp)
                .clip(CircleShape)
                .background(SuccessNeon)
        )
        Spacer(Modifier.width(8.dp))
        Text(
            text = "OUVINDO :$porta",
            style = MaterialTheme.typography.labelLarge,
            color = TextSecondary
        )
    }
}
