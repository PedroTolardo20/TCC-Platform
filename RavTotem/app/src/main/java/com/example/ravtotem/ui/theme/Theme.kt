package com.example.ravtotem.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Totem é um quiosque de marca própria: sempre o mesmo visual "RAF" escuro,
// independente do wallpaper/tema do tablet (por isso sem dynamicColor).
private val RavDarkColorScheme = darkColorScheme(
    primary = NeonCyan,
    onPrimary = DeepSpace,
    primaryContainer = SpaceSurfaceHigh,
    onPrimaryContainer = NeonCyan,
    secondary = FeiBlue,
    onSecondary = Color.White,
    tertiary = NeonViolet,
    onTertiary = Color.White,
    error = ErrorNeon,
    onError = Color.White,
    background = DeepSpace,
    onBackground = TextPrimary,
    surface = SpaceSurface,
    onSurface = TextPrimary,
    surfaceVariant = SpaceSurfaceHigh,
    onSurfaceVariant = TextSecondary,
    outline = SpaceOutline,
    outlineVariant = SpaceOutline
)

@Composable
fun RavTotemTheme(
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = RavDarkColorScheme,
        typography = Typography,
        content = content
    )
}
