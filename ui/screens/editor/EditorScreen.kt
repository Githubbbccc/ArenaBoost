package com.aicaption.ui.screens.editor

import android.net.Uri
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.autoMirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Pause
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner
import com.aicaption.ui.components.CaptionListItem
import com.aicaption.ui.components.CaptionOverlay
import com.aicaption.ui.components.TimelineScrubber
import com.aicaption.ui.components.VideoPlayerView

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EditorScreen(
    videoUri: Uri,
    onBack: () -> Unit,
    viewModel: EditorViewModel = hiltViewModel()
) {
    LaunchedEffect(videoUri) { viewModel.loadVideo(videoUri) }

    val currentPosition by viewModel.currentPosition.collectAsState()
    val duration by viewModel.duration.collectAsState()
    val isPlaying by viewModel.isPlaying.collectAsState()
    val captions by viewModel.captions.collectAsState()

    // Lifecycle management for audio leak fix
    val lifecycleOwner = LocalLifecycleOwner.current
    DisposableEffect(lifecycleOwner) {
        val observer = LifecycleEventObserver { _, event ->
            when (event) {
                Lifecycle.Event.ON_PAUSE -> viewModel.onPause()
                Lifecycle.Event.ON_RESUME -> viewModel.onResume()
                else -> {}
            }
        }
        lifecycleOwner.lifecycle.addObserver(observer)
        onDispose { lifecycleOwner.lifecycle.removeObserver(observer) }
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Caption Editor") },
                navigationIcon = {
                    IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") }
                }
            )
        }
    ) { paddingValues ->
        Column(modifier = Modifier.fillMaxSize().padding(paddingValues)) {
            
            // 1. Video + Overlay Area
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .padding(16.dp),
                contentAlignment = Alignment.Center
            ) {
                VideoPlayerView(player = viewModel.player, modifier = Modifier.fillMaxSize())
                CaptionOverlay(activeCaption = viewModel.activeCaption) // Overlay draws here
            }

            // 2. Controls & Timeline
            Column(
                modifier = Modifier.fillMaxWidth().padding(bottom = 16.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                IconButton(onClick = { viewModel.togglePlayPause() }, modifier = Modifier.size(48.dp)) {
                    Icon(
                        imageVector = if (isPlaying) Icons.Default.Pause else Icons.Default.PlayArrow,
                        contentDescription = if (isPlaying) "Pause" else "Play"
                    )
                }
                TimelineScrubber(
                    currentPositionMs = currentPosition,
                    durationMs = duration,
                    onSeek = { viewModel.seekTo(it) },
                    modifier = Modifier.fillMaxWidth()
                )
            }

            // 3. Caption List Area
            LazyColumn(
                modifier = Modifier.fillMaxWidth().weight(1f).padding(horizontal = 16.dp),
                verticalArrangement = Arrangement.spacedBy(4.dp)
            ) {
                if (captions.isEmpty()) {
                    item {
                        Text(
                            text = "No captions yet - Phase 4 will fill this list from AI transcription.",
                            style = MaterialTheme.typography.bodyMedium,
                            modifier = Modifier.fillMaxWidth().padding(vertical = 8.dp)
                        )
                    }
                }
                items(captions, key = { it.id }) { caption ->
                    CaptionListItem(
                        caption = caption,
                        onTextChange = { newText -> viewModel.updateCaptionText(caption.id, newText) },
                        onTimingChange = { start, end -> viewModel.updateCaptionTiming(caption.id, start, end) }
                    )
                }
            }
        }
    }
}
