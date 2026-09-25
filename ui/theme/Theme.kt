package com.aicaption.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.runtime.Composable
import androidx.compose.ui.graphics.Color

private val AiCaptionColorScheme = darkColorScheme(
    primary = Color(0xFF8B5CF6),
    secondary = Color(0xFF22D3EE),
    background = Color(0xFF0B0D14),
    surface = Color(0xFF161A26),
    surfaceVariant = Color(0xFF1E2333),
    onPrimary = Color(0xFF0B0D14),
    onSecondary = Color(0xFF0B0D14),
    onBackground = Color(0xFFE6E8F0),
    onSurface = Color(0xFFE6E8F0),
    onSurfaceVariant = Color(0xFFB9C0D4)
)

@Composable
fun AiCaptionTheme(content: @Composable () -> Unit) {
    MaterialTheme(colorScheme = AiCaptionColorScheme, content = content)
}
