package com.aicaption.ui.components

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import com.aicaption.data.local.CaptionEntity
import java.util.Locale

/** Nudge step (ms) used by the -/+ timing buttons of a caption row. */
private const val TIMING_STEP_MS = 100L

/** Sanity ceiling for an end time (24 h) so the stepper can never overflow. */
private val MAX_TIMING_MS = 24L * 60 * 60 * 1000

@Composable
fun CaptionListItem(
    caption: CaptionEntity,
    onTextChange: (String) -> Unit,
    onTimingChange: (startMs: Long, endMs: Long) -> Unit,
    modifier: Modifier = Modifier
) {
    var isEditing by remember { mutableStateOf(false) }
    var isTimingEditing by remember { mutableStateOf(false) }
    var editText by remember(caption.text) { mutableStateOf(caption.text) }

    Card(modifier = modifier.padding(vertical = 4.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surfaceVariant)) {
        Column(modifier = Modifier.padding(12.dp)) {
            // Timing Row (tap the row to open the timing steppers)
            Row(
                modifier = Modifier
                    .fillMaxWidth()
                    .clickable { isTimingEditing = !isTimingEditing },
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Text(formatTime(caption.startTimeMs), style = MaterialTheme.typography.labelSmall)
                Text(
                    text = if (isTimingEditing) "Done" else "Adjust timing",
                    style = MaterialTheme.typography.labelSmall
                )
                Text(formatTime(caption.endTimeMs), style = MaterialTheme.typography.labelSmall)
            }

            if (isTimingEditing) {
                TimingStepper(
                    label = "Start",
                    valueMs = caption.startTimeMs,
                    minMs = 0L,
                    maxMs = (caption.endTimeMs - TIMING_STEP_MS).coerceAtLeast(0L),
                    onValueChange = { startMs -> onTimingChange(startMs, caption.endTimeMs) }
                )
                TimingStepper(
                    label = "End",
                    valueMs = caption.endTimeMs,
                    minMs = (caption.startTimeMs + TIMING_STEP_MS).coerceAtMost(MAX_TIMING_MS),
                    maxMs = MAX_TIMING_MS,
                    onValueChange = { endMs -> onTimingChange(caption.startTimeMs, endMs) }
                )
            }

            Spacer(modifier = Modifier.height(4.dp))
            
            // Text / TextField
            if (isEditing) {
                TextField(
                    value = editText,
                    onValueChange = { editText = it },
                    singleLine = false,
                    modifier = Modifier.fillMaxWidth()
                )
                Row(modifier = Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.End) {
                    TextButton(onClick = { isEditing = false; editText = caption.text }) { Text("Cancel") }
                    TextButton(onClick = { onTextChange(editText); isEditing = false }) { Text("Save") }
                }
            } else {
                Text(caption.text, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.fillMaxWidth())
                TextButton(onClick = { isEditing = true }) { Text("Edit") }
            }
        }
    }
}

/** One -/+ stepper row for a caption boundary. Writes back through [onValueChange]. */
@Composable
private fun TimingStepper(
    label: String,
    valueMs: Long,
    minMs: Long,
    maxMs: Long,
    onValueChange: (Long) -> Unit
) {
    Row(
        modifier = Modifier.fillMaxWidth(),
        horizontalArrangement = Arrangement.SpaceBetween,
        verticalAlignment = Alignment.CenterVertically
    ) {
        Text(
            text = "$label  ${formatTime(valueMs)}",
            style = MaterialTheme.typography.labelMedium,
            modifier = Modifier.weight(1f)
        )
        TextButton(
            onClick = { onValueChange((valueMs - TIMING_STEP_MS).coerceAtLeast(minMs)) },
            enabled = valueMs > minMs
        ) { Text("-") }
        TextButton(
            onClick = { onValueChange((valueMs + TIMING_STEP_MS).coerceAtMost(maxMs)) },
            enabled = valueMs < maxMs
        ) { Text("+") }
    }
}

internal fun formatTime(ms: Long): String {
    val totalSeconds = ms / 1000
    val minutes = totalSeconds / 60
    val seconds = totalSeconds % 60
    val millis = (ms % 1000) / 100
    return String.format(Locale.getDefault(), "%02d:%02d.%01d", minutes, seconds, millis)
}
