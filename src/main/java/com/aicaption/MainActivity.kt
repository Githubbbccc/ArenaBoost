package com.aicaption

import android.content.Intent
import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.core.content.IntentCompat
import com.aicaption.ui.screens.editor.EditorScreen
import com.aicaption.ui.theme.AiCaptionTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            AiCaptionTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    EditorScreen(
                        videoUri = videoUriFrom(intent),
                        onBack = { finish() }
                    )
                }
            }
        }
    }

    /** A shared/viewed video wins; otherwise the sample clip so a fresh install has something to play. */
    private fun videoUriFrom(intent: Intent?): Uri = when (intent?.action) {
        Intent.ACTION_SEND ->
            IntentCompat.getParcelableExtra(intent, Intent.EXTRA_STREAM, Uri::class.java) ?: SAMPLE_VIDEO
        Intent.ACTION_VIEW -> intent.data ?: SAMPLE_VIDEO
        else -> SAMPLE_VIDEO
    }

    private companion object {
        val SAMPLE_VIDEO: Uri =
            Uri.parse("https://storage.googleapis.com/gtv-videos-bucket/sample/ForBiggerBlazes.mp4")
    }
}
