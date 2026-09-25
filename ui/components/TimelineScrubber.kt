package com.aicaption.ui.components

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Slider
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier

/**
 * Timeline bar for the editor. Shows `current / duration` and seeks while dragging.
 * The playhead position is driven by [EditorViewModel][com.aicaption.ui.screens.editor.EditorViewModel]
 * polling ExoPlayer, so the thumb follows playback as well as the user's finger.
 */
@Composable
fun TimelineScrubber(
    currentPositionMs: Long,
    durationMs: Long,
    onSeek: (Long) -> Unit,
    modifier: Modifier = Modifier
) {
    val duration = durationMs.coerceAtLeast(0L)
    var isDragging by remember { mutableStateOf(false) }
    var dragFraction by remember { mutableStateOf(0f) }

    val fraction = when {
        duration <= 0L -> 0f
        isDragging -> dragFraction
        else -> (currentPositionMs.coerceIn(0L, duration).toFloat() / duration.toFloat())
    }

    Column(
        modifier = modifier,
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center
    ) {
        Text(
            text = "${formatTime(currentPositionMs.coerceAtLeast(0L))} / ${formatTime(duration)}",
            style = MaterialTheme.typography.labelMedium
        )
        Slider(
            value = fraction.coerceIn(0f, 1f),
            onValueChange = { value ->
                isDragging = true
                dragFraction = value
                if (duration > 0L) onSeek((value * duration).toLong().coerceIn(0L, duration))
            },
            onValueChangeFinished = { isDragging = false },
            enabled = duration > 0L,
            modifier = Modifier.fillMaxWidth()
        )
    }
}
