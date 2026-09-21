package com.example.ravtotem.ui.components

import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.BoxScope
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.size
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp
import com.example.ravtotem.ui.theme.DeepSpace
import com.example.ravtotem.ui.theme.NeonCyan
import com.example.ravtotem.ui.theme.NeonViolet
import com.example.ravtotem.ui.theme.SpaceSurface

// Fundo compartilhado das 3 telas do totem: gradiente escuro + dois "glows"
// (ciano em cima, violeta embaixo) simulando luz de HUD sem depender de blur.
@Composable
fun FuturisticBackground(content: @Composable BoxScope.() -> Unit) {
    Box(
        modifier = Modifier
            .fillMaxSize()
            .background(Brush.verticalGradient(listOf(DeepSpace, SpaceSurface, DeepSpace)))
    ) {
        Box(
            modifier = Modifier
                .align(Alignment.TopCenter)
                .offset(y = (-180).dp)
                .size(480.dp)
                .background(
                    Brush.radialGradient(listOf(NeonCyan.copy(alpha = 0.16f), Color.Transparent))
                )
        )
        Box(
            modifier = Modifier
                .align(Alignment.BottomCenter)
                .offset(y = 220.dp)
                .size(420.dp)
                .background(
                    Brush.radialGradient(listOf(NeonViolet.copy(alpha = 0.12f), Color.Transparent))
                )
        )
        content()
    }
}
