package com.satyacheck

/**
 * M3 — accumulates PCM samples and emits fixed windows with overlap.
 *
 * The architecture calls for 3-second chunks with 1-second overlap, so consecutive windows
 * share their edges and a phrase spanning a boundary is never cut in half.
 *
 * WHY OVERLAP MATTERS HERE
 *
 * "turant pachas hazaar bhejo" takes about two seconds to say. Sliced at a hard 3-second
 * boundary it can land as "turant pachas" and "hazaar bhejo" — two fragments, neither of
 * which is a payment demand. The overlap means every phrase appears whole in at least one
 * window.
 *
 * Pure arithmetic on a ShortArray: no Android imports, no audio APIs, no I/O. That is
 * deliberate — this is the one part of the capture path whose correctness can be reasoned
 * about (and unit tested) without a device.
 *
 * Not thread-safe. AudioRecord delivers on a single reader thread; `CallAudioService` owns
 * one instance and never shares it.
 */
class RingBuffer(
    private val sampleRate: Int = 16_000,
    windowSeconds: Double = 3.0,
    overlapSeconds: Double = 1.0,
) {
    /** Samples per emitted window. */
    val windowSamples: Int = (sampleRate * windowSeconds).toInt()

    /** Samples of the previous window retained at the front of the next one. */
    private val overlapSamples: Int = (sampleRate * overlapSeconds).toInt()

    /** How far the window advances each time — 2s for a 3s window with 1s overlap. */
    private val strideSamples: Int = windowSamples - overlapSamples

    init {
        require(windowSamples > 0) { "window must be longer than zero samples" }
        require(overlapSamples in 0 until windowSamples) {
            "overlap ($overlapSamples) must be shorter than the window ($windowSamples)"
        }
    }

    private var buffer = ShortArray(windowSamples * 2)
    private var length = 0

    /** Samples currently held but not yet emitted. */
    val available: Int get() = length

    /**
     * Add `count` samples from `samples` and return every complete window they made.
     *
     * Usually returns zero or one window. It can return more when a single read is longer
     * than the stride, which happens on the first read after the recorder starts and
     * whenever the reader thread is descheduled — dropping the extras there would silently
     * lose audio under exactly the load that causes it.
     */
    fun append(samples: ShortArray, count: Int = samples.size): List<ShortArray> {
        if (count <= 0) return emptyList()

        ensureCapacity(length + count)
        System.arraycopy(samples, 0, buffer, length, count)
        length += count

        val windows = mutableListOf<ShortArray>()
        while (length >= windowSamples) {
            windows += buffer.copyOfRange(0, windowSamples)

            // Slide forward by the stride, keeping the overlap tail for the next window.
            System.arraycopy(buffer, strideSamples, buffer, 0, length - strideSamples)
            length -= strideSamples
        }
        return windows
    }

    /**
     * Return whatever is left, if it is worth sending, and clear the buffer.
     *
     * Call at end of call. The tail is often the most incriminating part — the UPI ID, the
     * "don't tell anyone" — so discarding it silently would lose the evidence the whole
     * system exists to find. A fragment shorter than `minSeconds` is dropped instead,
     * because the backend's quality gate refuses to score below 1.5s anyway and a confident
     * number on 0.4 seconds of noise is worse than no number.
     */
    fun drain(minSeconds: Double = 1.5): ShortArray? {
        val minSamples = (sampleRate * minSeconds).toInt()
        val tail = if (length >= minSamples) buffer.copyOfRange(0, length) else null
        length = 0
        return tail
    }

    /** Discard everything. Used when a session ends or restarts. */
    fun clear() {
        length = 0
    }

    private fun ensureCapacity(needed: Int) {
        if (needed <= buffer.size) return
        var size = buffer.size
        while (size < needed) size *= 2
        buffer = buffer.copyOf(size)
    }
}
