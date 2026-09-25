package com.aicaption.ui.components

import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.viewinterop.AndroidView
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView

/**
 * Hosts the ExoPlayer [PlayerView] inside Compose. Playback controls live in the editor
 * UI, so the view's own controller is disabled - the caption overlay must stay clickable.
 */
@Composable
fun VideoPlayerView(
    player: ExoPlayer,
    modifier: Modifier = Modifier
) {
    AndroidView(
        modifier = modifier,
        factory = { context ->
            PlayerView(context).apply {
                this.player = player
                useController = false
                setShutterBackgroundColor(android.graphics.Color.BLACK)
            }
        },
        onRelease = { view -> view.player = null }
    )
}
