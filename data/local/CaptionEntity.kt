package com.aicaption.data.local

import androidx.room.Entity
import androidx.room.PrimaryKey
import java.util.UUID

@Entity(tableName = "captions")
data class CaptionEntity(
    @PrimaryKey val id: String = UUID.randomUUID().toString(),
    val projectId: String,
    val startTimeMs: Long,
    val endTimeMs: Long,
    val text: String,
    val language: String = "en",
    val confidence: Float = 1.0f
)
