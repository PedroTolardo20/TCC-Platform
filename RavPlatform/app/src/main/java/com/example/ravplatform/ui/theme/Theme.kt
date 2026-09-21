package com.example.ravplatform.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

// Mesmo tratamento do RavTotem: visual "RAF" escuro fixo, independente do
// wallpaper/tema do tablet (sem dynamicColor).
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
fun RavPlatformTheme(
    content: @Composable () -> Unit
) {
    MaterialTheme(
        colorScheme = RavDarkColorScheme,
        typography = Typography,
        content = content
    )
}
