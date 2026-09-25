package com.aicaption.ui.screens.editor

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import androidx.media3.common.MediaItem
import androidx.media3.common.Player
import androidx.media3.exoplayer.ExoPlayer
import com.aicaption.data.local.CaptionDao
import com.aicaption.data.local.CaptionEntity
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.SharingStarted
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.stateIn
import kotlinx.coroutines.isActive
import kotlinx.coroutines.launch
import java.util.UUID
import javax.inject.Inject

@HiltViewModel
class EditorViewModel @Inject constructor(
    @ApplicationContext private val context: Context,
    private val captionDao: CaptionDao
) : ViewModel() {

    val player: ExoPlayer = ExoPlayer.Builder(context).build()
    
    // Simple project ID for this session. In full app, this comes from Project creation.
    private val currentProjectId = UUID.randomUUID().toString()

    private val _currentPosition = MutableStateFlow(0L)
    val currentPosition: StateFlow<Long> = _currentPosition.asStateFlow()

    private val _duration = MutableStateFlow(0L)
    val duration: StateFlow<Long> = _duration.asStateFlow()

    private val _isPlaying = MutableStateFlow(false)
    val isPlaying: StateFlow<Boolean> = _isPlaying.asStateFlow()

    // Reactive list of captions from Room
    val captions: StateFlow<List<CaptionEntity>> = captionDao.getCaptionsForProject(currentProjectId)
        .stateIn(viewModelScope, SharingStarted.WhileSubscribed(5000), emptyList())

    // Computed property: Find the caption that should be showing right now
    val activeCaption: CaptionEntity?
        get() = findActiveCaption(captions.value, _currentPosition.value)

    init {
        player.addListener(object : Player.Listener {
            override fun onIsPlayingChanged(isPlaying: Boolean) { _isPlaying.value = isPlaying }
        })

        viewModelScope.launch {
            while (isActive) {
                if (player.isPlaying) {
                    _currentPosition.value = player.currentPosition
                    _duration.value = player.duration.coerceAtLeast(0L)
                }
                delay(TIMELINE_UPDATE_INTERVAL_MS)
            }
        }
    }

    fun loadVideo(uri: Uri) {
        val mediaItem = MediaItem.fromUri(uri)
        player.setMediaItem(mediaItem)
        player.prepare()
        player.playWhenReady = true
        
        // Add a dummy caption for testing the overlay
        viewModelScope.launch {
            if (captions.value.isEmpty()) {
                captionDao.insertOrUpdateCaption(
                    CaptionEntity(
                        projectId = currentProjectId,
                        startTimeMs = 1000,
                        endTimeMs = 4000,
                        text = "This is a test caption."
                    )
                )
                captionDao.insertOrUpdateCaption(
                    CaptionEntity(
                        projectId = currentProjectId,
                        startTimeMs = 5000,
                        endTimeMs = 8000,
                        text = "Edit me in the list below!"
                    )
                )
            }
        }
    }

    fun seekTo(positionMs: Long) { player.seekTo(positionMs); _currentPosition.value = positionMs }
    fun togglePlayPause() { if (player.isPlaying) player.pause() else player.play() }
    fun onPause() { player.pause() }
    fun onResume() { if (_isPlaying.value) player.play() }

    fun updateCaptionText(id: String, newText: String) {
        viewModelScope.launch {
            val caption = captions.value.find { it.id == id } ?: return@launch
            captionDao.insertOrUpdateCaption(caption.copy(text = newText))
        }
    }

    fun updateCaptionTiming(id: String, startMs: Long, endMs: Long) {
        viewModelScope.launch {
            val caption = captions.value.find { it.id == id } ?: return@launch
            captionDao.insertOrUpdateCaption(caption.copy(startTimeMs = startMs, endTimeMs = endMs))
        }
    }

    override fun onCleared() { super.onCleared(); player.release() }

    companion object { private const val TIMELINE_UPDATE_INTERVAL_MS = 50L }
}

/**
 * The timestamp rule behind [EditorViewModel.activeCaption]: the caption on screen is the
 * first caption whose [startTimeMs]..[endTimeMs] window contains [positionMs] (endpoints
 * included). Kept as a pure top-level function so the rule can be unit tested without a
 * player or a database.
 */
internal fun findActiveCaption(captions: List<CaptionEntity>, positionMs: Long): CaptionEntity? =
    captions.find { positionMs in it.startTimeMs..it.endTimeMs }
