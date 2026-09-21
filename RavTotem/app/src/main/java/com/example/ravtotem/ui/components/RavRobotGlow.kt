package com.example.ravtotem.ui.components

import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.scale
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.unit.Dp
import androidx.compose.ui.unit.dp
import com.example.ravtotem.R
import com.example.ravtotem.ui.theme.NeonCyan

// Silhueta do RAF com glow pulsante — usada na tela de boas-vindas e no
// acompanhamento de pedido, sempre com o mesmo tratamento visual.
@Composable
fun RavRobotGlow(
    modifier: Modifier = Modifier,
    robotHeight: Dp = 300.dp,
    glowSize: Dp = 380.dp
) {
    val transition = rememberInfiniteTransition(label = "glow")
    val glowAlpha by transition.animateFloat(
        initialValue = 0.25f,
        targetValue = 0.55f,
        animationSpec = infiniteRepeatable(
            animation = tween(1600),
            repeatMode = RepeatMode.Reverse
        ),
        label = "glowAlpha"
    )

    Box(modifier = modifier, contentAlignment = Alignment.Center) {
        Box(
            modifier = Modifier
                .size(glowSize)
                .scale(1f + glowAlpha * 0.06f)
                .background(
                    Brush.radialGradient(
                        listOf(NeonCyan.copy(alpha = glowAlpha * 0.4f), Color.Transparent)
                    )
                )
        )
        Image(
            painter = painterResource(id = R.drawable.ic_rav_robot),
            contentDescription = "Robô RAF",
            modifier = Modifier.height(robotHeight)
        )
    }
}
