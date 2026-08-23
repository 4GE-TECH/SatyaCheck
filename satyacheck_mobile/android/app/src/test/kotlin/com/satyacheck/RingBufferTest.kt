package com.satyacheck

import org.junit.Assert.assertArrayEquals
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Unit tests for the chunking arithmetic.
 *
 * `RingBuffer` is deliberately free of Android imports so it can be tested on the JVM with
 * `./gradlew test` — no device, no emulator. It is the only part of the capture path whose
 * correctness does not depend on hardware, and getting the overlap wrong is a bug that
 * would show up as "the scam detector misses phrases at chunk boundaries", which is very
 * hard to diagnose from a live call.
 */
class RingBufferTest {

    private val rate = 16_000

    /** Samples counting up from `from`, so a window's contents identify its position. */
    private fun ramp(count: Int, from: Int = 0) =
        ShortArray(count) { ((from + it) % Short.MAX_VALUE).toShort() }

    @Test
    fun `emits nothing until a full window has arrived`() {
        val ring = RingBuffer(rate)
        // Two seconds against a three-second window.
        assertTrue(ring.append(ramp(rate * 2)).isEmpty())
        assertEquals(rate * 2, ring.available)
    }

    @Test
    fun `emits one window of exactly the configured length`() {
        val ring = RingBuffer(rate)
        val windows = ring.append(ramp(rate * 3))

        assertEquals(1, windows.size)
        assertEquals(rate * 3, windows[0].size)
    }

    @Test
    fun `consecutive windows overlap by one second`() {
        // The property the whole class exists for: a phrase spanning a boundary must appear
        // whole in at least one window. With a 3s window and 1s overlap, window two starts
        // 2s (the stride) into window one, and its first second repeats window one's last.
        val ring = RingBuffer(rate)
        val first = ring.append(ramp(rate * 3)).single()
        val second = ring.append(ramp(rate * 2, from = rate * 3)).single()

        val tailOfFirst = first.copyOfRange(rate * 2, rate * 3)
        val headOfSecond = second.copyOfRange(0, rate)

        assertArrayEquals(
            "the last second of window one is not the first second of window two",
            tailOfFirst,
            headOfSecond,
        )
    }

    @Test
    fun `a single long append yields every window it contains`() {
        // Happens on the first read after start, and whenever the reader thread is
        // descheduled. Returning only the first window would silently drop audio under
        // exactly the load that causes it.
        val ring = RingBuffer(rate)
        // 9s: windows at 0-3, 2-5, 4-7, 6-9.
        val windows = ring.append(ramp(rate * 9))

        assertEquals(4, windows.size)
        windows.forEach { assertEquals(rate * 3, it.size) }
    }

    @Test
    fun `windows advance by the stride not the window length`() {
        val ring = RingBuffer(rate)
        val windows = ring.append(ramp(rate * 7))

        // Window two begins at the stride (2s), so its first sample is the 32000th.
        assertEquals(
            (rate * 2).toShort(),
            windows[1][0],
        )
    }

    @Test
    fun `drain returns the tail when it is long enough to score`() {
        val ring = RingBuffer(rate)
        ring.append(ramp(rate * 2))

        val tail = ring.drain(minSeconds = 1.5)

        // The end of a call is often where the payment demand lands, so a usable tail must
        // not be discarded.
        assertEquals(rate * 2, tail?.size)
        assertEquals(0, ring.available)
    }

    @Test
    fun `drain discards a fragment too short to score`() {
        val ring = RingBuffer(rate)
        ring.append(ramp(rate / 2)) // 0.5s

        // CLAUDE.md: refusing to score is a feature. The backend's quality gate rejects
        // anything under 1.5s anyway, so sending it wastes a request and invites a
        // confident number on nothing.
        assertNull(ring.drain(minSeconds = 1.5))
        assertEquals(0, ring.available)
    }

    @Test
    fun `many small appends produce the same windows as one large one`() {
        // AudioRecord delivers whatever size it likes; chunking must not depend on it.
        val chunked = RingBuffer(rate)
        val bulk = RingBuffer(rate)

        val produced = mutableListOf<ShortArray>()
        var offset = 0
        repeat(64) {
            val piece = ramp(rate / 8, from = offset) // 125 ms at a time
            offset += rate / 8
            produced += chunked.append(piece)
        }
        val expected = bulk.append(ramp(rate * 8))

        assertEquals(expected.size, produced.size)
        expected.zip(produced).forEach { (a, b) -> assertArrayEquals(a, b) }
    }

    @Test
    fun `respects the count argument and ignores the rest of the array`() {
        // AudioRecord.read returns how many samples it actually wrote; the array is a
        // reused scratch buffer whose tail is stale audio from the previous read.
        val ring = RingBuffer(rate)
        val scratch = ramp(rate * 4)

        assertTrue(ring.append(scratch, count = rate * 2).isEmpty())
        assertEquals(rate * 2, ring.available)
    }

    @Test
    fun `an empty or negative read is ignored`() {
        val ring = RingBuffer(rate)
        assertTrue(ring.append(ShortArray(0)).isEmpty())
        assertTrue(ring.append(ramp(10), count = 0).isEmpty())
        assertTrue(ring.append(ramp(10), count = -1).isEmpty())
        assertEquals(0, ring.available)
    }

    @Test
    fun `clear drops buffered audio`() {
        val ring = RingBuffer(rate)
        ring.append(ramp(rate * 2))
        ring.clear()
        assertEquals(0, ring.available)
    }
}
