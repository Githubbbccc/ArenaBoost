package com.aicaption.data.local

import android.content.Context
import androidx.room.Database
import androidx.room.Room
import androidx.room.RoomDatabase
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Database(entities = [CaptionEntity::class], version = 1)
abstract class AppDatabase : RoomDatabase() {
    abstract fun captionDao(): CaptionDao
}

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {
    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): AppDatabase {
        return Room.databaseBuilder(context, AppDatabase::class.java, "aicaption_db").build()
    }

    @Provides
    fun provideCaptionDao(db: AppDatabase): CaptionDao = db.captionDao()
}
