package com.aicaption

import com.aicaption.data.local.CaptionEntity
import com.aicaption.ui.components.formatTime
import com.aicaption.ui.screens.editor.findActiveCaption
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import java.util.Locale

/**
 * Pure-logic tests for the Phase 3 editor rules: which caption is on screen at a given
 * playhead position, and how a caption timestamp is rendered.
 */
class CaptionEditorLogicTest {

    // formatTime() is locale sensitive (String.format) - pin it so the test is deterministic.
    private lateinit var originalLocale: Locale

    @Before
    fun pinLocale() {
        originalLocale = Locale.getDefault()
        Locale.setDefault(Locale.US)
    }

    @After
    fun restoreLocale() {
        Locale.setDefault(originalLocale)
    }

    private val first = CaptionEntity(
        projectId = "project-1",
        startTimeMs = 1000,
        endTimeMs = 4000,
        text = "This is a test caption."
    )

    private val second = CaptionEntity(
        projectId = "project-1",
        startTimeMs = 5000,
        endTimeMs = 8000,
        text = "Edit me in the list below!"
    )

    private val captions = listOf(first, second)

    @Test
    fun formatTimeRendersMinutesSecondsAndTenths() {
        assertEquals("00:00.0", formatTime(0L))
        assertEquals("00:01.0", formatTime(1000L))
        assertEquals("00:03.9", formatTime(3999L))
        assertEquals("00:06.5", formatTime(6500L))
        assertEquals("01:23.0", formatTime(83000L))
        assertEquals("10:00.0", formatTime(600_000L))
    }

    @Test
    fun activeCaptionIsTheOneWhoseWindowContainsThePlayhead() {
        assertEquals(first, findActiveCaption(captions, 2500L))
        assertEquals(second, findActiveCaption(captions, 6000L))
    }

    @Test
    fun activeCaptionWindowEndpointsAreInclusive() {
        assertEquals(first, findActiveCaption(captions, 1000L))
        assertEquals(first, findActiveCaption(captions, 4000L))
        assertEquals(second, findActiveCaption(captions, 5000L))
        assertEquals(second, findActiveCaption(captions, 8000L))
    }

    @Test
    fun noActiveCaptionOutsideAnyWindow() {
        assertNull(findActiveCaption(captions, 0L))
        assertNull(findActiveCaption(captions, 999L))
        assertNull(findActiveCaption(captions, 4500L))
        assertNull(findActiveCaption(captions, 9000L))
        assertNull(findActiveCaption(emptyList(), 2500L))
    }

    @Test
    fun activeCaptionIsTheFirstMatchWhenWindowsOverlap() {
        val overlapping = first.copy(id = "overlap", startTimeMs = 2000, endTimeMs = 6000)
        assertEquals(first, findActiveCaption(listOf(first, overlapping), 2500L))
    }
}
