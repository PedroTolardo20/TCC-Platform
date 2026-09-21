package com.example.ravplatform

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
//import com.example.ravplatform.nav.NavegacaoStub
import com.example.ravplatform.nav.TemiNavegacao
import com.example.ravplatform.network.RavWebSocketServer
import com.example.ravplatform.ui.theme.RavPlatformTheme
import kotlinx.coroutines.flow.MutableStateFlow

class MainActivity : ComponentActivity() {

    private val logs = MutableStateFlow<List<String>>(emptyList())
    private var servidor: RavWebSocketServer? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)

        servidor = RavWebSocketServer(
            porta = 8765,
            navegacao = TemiNavegacao(),
            onLog = { linha -> logs.value = logs.value + linha }
        ).apply {
            isReuseAddr = true
            start()
        }

        setContent {
            RavPlatformTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val linhas by logs.collectAsState()
                    TelaServidor(linhas)
                }
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
fun TelaServidor(logs: List<String>) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .padding(24.dp)
    ) {
        Text(
            text = "RAV Platform — Servidor",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold
        )
        Spacer(Modifier.height(16.dp))
        LazyColumn(verticalArrangement = Arrangement.spacedBy(6.dp)) {
            items(logs) { linha ->
                Text(text = linha, style = MaterialTheme.typography.bodyMedium)
            }
        }
    }
}