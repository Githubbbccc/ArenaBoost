package com.aicaption.data.local

import androidx.room.*
import kotlinx.coroutines.flow.Flow

@Dao
interface CaptionDao {
    @Query("SELECT * FROM captions WHERE projectId = :projectId ORDER BY startTimeMs ASC")
    fun getCaptionsForProject(projectId: String): Flow<List<CaptionEntity>>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insertOrUpdateCaption(caption: CaptionEntity)

    @Delete
    suspend fun deleteCaption(caption: CaptionEntity)
}
