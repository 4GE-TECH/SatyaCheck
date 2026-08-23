package com.satyacheck

import android.media.AudioFormat
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.AutomaticGainControl
import android.media.audiofx.NoiseSuppressor
import android.util.Log
import java.io.File
import java.io.RandomAccessFile
import java.nio.ByteBuffer
import java.nio.ByteOrder
import kotlin.concurrent.thread
import kotlin.math.abs

/**
 * Records a single WAV file for enrollment, and reports live levels while it does.
 *
 * Separate from `CallAudioService` on purpose. That one streams overlapping windows to the
 * backend during a call and lives in a foreground service; this writes one contiguous file
 * while the user is looking at the screen. Sharing the code would mean one class doing two
 * unrelated jobs with a mode flag.
 *
 * WHY THE LEVEL METER MATTERS MORE THAN IT LOOKS
 *
 * The single most common enrollment failure is a recording that is technically valid and
 * acoustically useless — too quiet, too far from the mic, or the wrong person talking. The
 * backend's quality gate then rejects it, or worse accepts it and produces a voiceprint that
 * false-mismatches the real person later. A live meter makes that visible *before* the
 * upload rather than after.
 *
 * The three voice-processing effects are disabled here for the same reason as in
 * `CallAudioService`: AGC in particular flattens exactly the level dynamics that make one
 * speaker distinguishable from another, and an enrollment recorded through AGC is a
 * voiceprint of the processing as much as of the person.
 */
object VoiceRecorder {

    private const val TAG = "SatyaCheck/Record"
    const val SAMPLE_RATE = 16_000

    /** Receives level updates so the UI can show a meter. */
    interface Listener {
        /** `level` is 0..1 peak amplitude; `seconds` is elapsed recording time. */
        fun onLevel(level: Double, seconds: Double)
        fun onRecorderError(reason: String)
    }

    @Volatile
    var listener: Listener? = null

    private var recorder: AudioRecord? = null
    private var worker: Thread? = null
    @Volatile private var running = false
    private var target: File? = null

    val isRecording: Boolean get() = running

    /**
     * Start recording to `file`. Returns false if the microphone could not be opened.
     *
     * MIC, not VOICE_COMMUNICATION: enrollment happens with no call in progress, and the
     * in-call source routes through call pre-processing that is wrong here.
     */
    fun start(file: File): Boolean {
        if (running) return true

        val minBuffer = AudioRecord.getMinBufferSize(
            SAMPLE_RATE, AudioFormat.CHANNEL_IN_MONO, AudioFormat.ENCODING_PCM_16BIT
        )
        if (minBuffer <= 0) {
            listener?.onRecorderError("16 kHz mono capture is unsupported on this device")
            return false
        }

        val record = try {
            AudioRecord(
                MediaRecorder.AudioSource.MIC,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                minBuffer * 4
            )
        } catch (t: Throwable) {
            Log.e(TAG, "AudioRecord construction failed", t)
            listener?.onRecorderError("could not open the microphone")
            return false
        }

        if (record.state != AudioRecord.STATE_INITIALIZED) {
            record.release()
            listener?.onRecorderError("microphone unavailable")
            return false
        }

        disableEffects(record.audioSessionId)

        target = file
        recorder = record
        running = true
        record.startRecording()

        worker = thread(name = "satyacheck-enroll", isDaemon = true) {
            writeWav(record, file, minBuffer * 2)
        }
        Log.i(TAG, "recording to ${file.name}")
        return true
    }

    /** Stop and finalise the WAV. Returns the file, or null if nothing usable was written. */
    fun stop(): File? {
        if (!running) return target
        running = false
        worker?.join(2_000)
        worker = null

        recorder?.let { r ->
            runCatching { if (r.recordingState == AudioRecord.RECORDSTATE_RECORDING) r.stop() }
            runCatching { r.release() }
        }
        recorder = null
        releaseEffects()

        val file = target
        target = null
        Log.i(TAG, "stopped; ${file?.length() ?: 0} bytes")
        // Header alone is 44 bytes; anything near that captured no audio.
        return if (file != null && file.length() > 1_000) file else null
    }

    // --- internals ------------------------------------------------------------

    private fun writeWav(record: AudioRecord, file: File, bufferBytes: Int) {
        val scratch = ShortArray(bufferBytes / 2)
        var totalSamples = 0L

        try {
            file.outputStream().use { out ->
                // Placeholder header — the sizes are only known once recording stops, so
                // it is patched in place afterwards.
                out.write(wavHeader(0))

                while (running) {
                    val read = try {
                        record.read(scratch, 0, scratch.size)
                    } catch (t: Throwable) {
                        Log.e(TAG, "read failed", t)
                        break
                    }
                    if (read <= 0) continue

                    val bytes = ByteBuffer.allocate(read * 2).order(ByteOrder.LITTLE_ENDIAN)
                    var peak = 0
                    for (i in 0 until read) {
                        bytes.putShort(scratch[i])
                        val magnitude = abs(scratch[i].toInt())
                        if (magnitude > peak) peak = magnitude
                    }
                    out.write(bytes.array())
                    totalSamples += read

                    listener?.onLevel(
                        peak / 32767.0,
                        totalSamples.toDouble() / SAMPLE_RATE,
                    )
                }
            }
            patchHeader(file, totalSamples * 2)
        } catch (t: Throwable) {
            Log.e(TAG, "write failed", t)
            listener?.onRecorderError("could not write the recording")
        }
    }

    /** 44-byte canonical WAV header for 16-bit mono PCM. */
    private fun wavHeader(dataBytes: Long): ByteArray {
        val buffer = ByteBuffer.allocate(44).order(ByteOrder.LITTLE_ENDIAN)
        buffer.put("RIFF".toByteArray())
        buffer.putInt((36 + dataBytes).toInt())
        buffer.put("WAVE".toByteArray())
        buffer.put("fmt ".toByteArray())
        buffer.putInt(16)                       // PCM chunk size
        buffer.putShort(1)                      // format 1 = PCM
        buffer.putShort(1)                      // mono
        buffer.putInt(SAMPLE_RATE)
        buffer.putInt(SAMPLE_RATE * 2)          // byte rate
        buffer.putShort(2)                      // block align
        buffer.putShort(16)                     // bits per sample
        buffer.put("data".toByteArray())
        buffer.putInt(dataBytes.toInt())
        return buffer.array()
    }

    /** Rewrite the two length fields now that the real size is known. */
    private fun patchHeader(file: File, dataBytes: Long) {
        RandomAccessFile(file, "rw").use { raf ->
            raf.seek(0)
            raf.write(wavHeader(dataBytes))
        }
    }

    private var aec: AcousticEchoCanceler? = null
    private var ns: NoiseSuppressor? = null
    private var agc: AutomaticGainControl? = null

    private fun disableEffects(sessionId: Int) {
        runCatching {
            if (AcousticEchoCanceler.isAvailable()) {
                aec = AcousticEchoCanceler.create(sessionId)?.apply { enabled = false }
            }
            if (NoiseSuppressor.isAvailable()) {
                ns = NoiseSuppressor.create(sessionId)?.apply { enabled = false }
            }
            // AGC is the important one here: it normalises loudness, and loudness dynamics
            // are part of what distinguishes one speaker from another.
            if (AutomaticGainControl.isAvailable()) {
                agc = AutomaticGainControl.create(sessionId)?.apply { enabled = false }
            }
        }.onFailure { Log.w(TAG, "could not disable effects", it) }
    }

    private fun releaseEffects() {
        runCatching { aec?.release() }
        runCatching { ns?.release() }
        runCatching { agc?.release() }
        aec = null; ns = null; agc = null
    }
}
