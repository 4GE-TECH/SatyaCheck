package com.satyacheck

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.media.AudioDeviceInfo
import android.media.AudioFormat
import android.media.AudioManager
import android.media.AudioRecord
import android.media.MediaRecorder
import android.media.audiofx.AcousticEchoCanceler
import android.media.audiofx.AutomaticGainControl
import android.media.audiofx.NoiseSuppressor
import android.os.Build
import android.os.IBinder
import android.os.SystemClock
import android.util.Log
import androidx.core.content.ContextCompat
import java.util.UUID
import kotlin.concurrent.thread

/**
 * M3 + M4 — capture call audio for the duration of a call and hand 3-second windows onward.
 *
 * A foreground service, because the user will leave the app the moment they answer. A plain
 * background thread is killed within seconds, and from Android 11 the microphone is muted
 * outright for anything not in the foreground.
 *
 * HOW THE FAR END IS ACTUALLY CAPTURED — the constraint that shapes everything here
 *
 * You cannot tap the call stream. `AudioSource.VOICE_CALL` requires CAPTURE_AUDIO_OUTPUT, a
 * signature-level permission held only by the OEM, and since Android 10 third-party call
 * recording is closed off deliberately. Apps that still record calls do it one of two ways:
 * as an AccessibilityService (Play Store policy violation) or acoustically.
 *
 * This does it acoustically: force the call to speakerphone and record the room with
 * VOICE_COMMUNICATION. The caller's voice comes out of the speaker and back in through the
 * mic. That has real consequences worth stating plainly:
 *
 *   - the user's own voice is captured too, so the transcript is both sides of the call
 *   - quality depends on the handset and the room
 *   - forcing speakerphone is *visible* to the user, which is arguably honest rather than a
 *     defect — a scam screener that silently records calls is a different product
 *
 * THE THREE EFFECTS ARE DISABLED ON PURPOSE
 *
 * AcousticEchoCanceler, NoiseSuppressor and AutomaticGainControl all exist to make voice
 * *calls* sound better, and all three destroy the signal this app measures. AEC in
 * particular is designed to remove exactly what we want: sound emitted by this device's own
 * speaker, which is the far end. AGC flattens the level dynamics an anti-spoof model reads.
 * Leaving them on would degrade the far end into the noise floor.
 */
class CallAudioService : Service() {

    companion object {
        private const val TAG = "SatyaCheck/Audio"
        private const val CHANNEL_ID = "com.satyacheck.capture"
        private const val NOTIFICATION_ID = 4201

        const val SAMPLE_RATE = 16_000

        /**
         * Consecutive failed reads before a source is declared dead.
         *
         * At 16 kHz mono a read is roughly 160 ms, so ~48 reads is about eight seconds of
         * nothing. Long enough to ride out a transient route change when the call audio
         * switches to speaker, short enough that the user is told inside one call rather
         * than after it.
         */
        private const val BARREN_LIMIT = 48

        /**
         * Peak PCM value below which a buffer counts as silence.
         *
         * Not zero: a live microphone always carries a little self-noise, so exact zeros
         * mean the OS substituted silence rather than that the room was quiet.
         */
        private const val SILENCE_FLOOR = 2

        /** Silent probe buffers tolerated before a source is rejected (~1s). */
        private const val SILENT_PROBE_LIMIT = 6

        /** Consecutive silent read buffers (~5s) before the user is told. */
        private const val SILENT_RUN_LIMIT = 32

        @Volatile
        var listener: AudioChunkListener? = null

        /** The session id shared by every chunk of the current call. */
        @Volatile
        var sessionId: String? = null
            private set

        fun start(context: Context) {
            val intent = Intent(context, CallAudioService::class.java)
            ContextCompat.startForegroundService(context, intent)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, CallAudioService::class.java))
        }
    }

    /** Receives each captured window. Implemented by the Dart bridge in MainActivity. */
    interface AudioChunkListener {
        fun onChunk(sessionId: String, index: Int, pcm16: ShortArray, sampleRate: Int)
        fun onCaptureError(reason: String)
    }

    private var recorder: AudioRecord? = null
    private var captureThread: Thread? = null
    @Volatile private var running = false

    private var echoCanceler: AcousticEchoCanceler? = null
    private var noiseSuppressor: NoiseSuppressor? = null
    private var gainControl: AutomaticGainControl? = null

    private var previousAudioMode = AudioManager.MODE_NORMAL
    private var previousSpeakerphone = false

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (running) return START_STICKY

        startForeground(NOTIFICATION_ID, buildNotification())

        if (ContextCompat.checkSelfPermission(this, android.Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            Log.e(TAG, "RECORD_AUDIO not granted; cannot capture")
            listener?.onCaptureError("microphone permission not granted")
            stopSelf()
            return START_NOT_STICKY
        }

        sessionId = UUID.randomUUID().toString()
        Log.i(TAG, "onStartCommand: session=$sessionId listener=${listener != null}")
        forceSpeakerphone()
        beginCapture()
        return START_STICKY
    }

    override fun onDestroy() {
        endCapture()
        restoreAudioRoute()
        sessionId = null
        CallStateReceiver.reset()
        super.onDestroy()
    }

    // --- capture ---------------------------------------------------------------

    private fun beginCapture() {
        val minBuffer = AudioRecord.getMinBufferSize(
            SAMPLE_RATE,
            AudioFormat.CHANNEL_IN_MONO,
            AudioFormat.ENCODING_PCM_16BIT
        )
        if (minBuffer <= 0) {
            Log.e(TAG, "device reports no usable buffer size for 16 kHz mono PCM")
            listener?.onCaptureError("16 kHz mono capture unsupported on this device")
            stopSelf()
            return
        }

        // Four times the minimum. At the minimum, one descheduled read overruns the buffer
        // and the dropped samples are silent — audio simply goes missing mid-call.
        val bufferSize = minBuffer * 4

        // Which microphone source depends on whether a call is actually up.
        //
        // VOICE_COMMUNICATION is the right source *during* a call: it coexists with the
        // telephony stack on the most devices. But it is a call-audio configuration, and
        // outside a call — the "Test without a call" path — it routes through the same
        // pre-processing chain and returns audio Whisper cannot read. Measured: a capture
        // at 88% of full scale that transcribed to nothing, with avg_logprob -1.25 (the
        // gate's floor is -1.0), i.e. the decoder guessing rather than hearing.
        //
        // MIC is the plain, unprocessed source and is what a test capture wants.
        val inCall = try {
            val audio = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            audio.mode == AudioManager.MODE_IN_CALL ||
                audio.mode == AudioManager.MODE_IN_COMMUNICATION
        } catch (t: Throwable) {
            false
        }
        // MIC on a call too — deliberately, not as a fallback.
        //
        // VOICE_COMMUNICATION is the intuitive choice and it is the wrong one here. It
        // exists for VoIP, where the far end arrives over the network and the speaker
        // output is echo to be removed. Its acoustic echo canceller is built to delete
        // exactly what comes out of the earpiece or speaker — which, on a speakerphone
        // call, is the remote party's voice, the one voice this app exists to screen.
        //
        // What that produced on this device: an 18-second call yielding 0 windows, then
        // 30-second calls yielding 2 where 5 were due. Audio arrived at roughly half
        // real-time because only the near end survived cancellation, so the far side of
        // every conversation was being erased before it reached the ring buffer, and every
        // call came back unverified.
        //
        // Android does not hand the cellular downlink to a third-party app under any
        // source — VOICE_CALL needs CAPTURE_AUDIO_OUTPUT, which is signature|privileged —
        // so acoustic capture off the speaker is the only path that exists. MIC, with the
        // effects disabled below, is the source that leaves it intact.
        val source = MediaRecorder.AudioSource.MIC
        Log.i(TAG, "audio source = MIC (${if (inCall) "in call" else "no call"})")

        // Try the call-audio source first, then fall back to the plain microphone.
        //
        // Measured on this device (Galaxy S23 FE, Android 16): VOICE_COMMUNICATION on a
        // live cellular call constructs, initialises and reports RECORDSTATE_RECORDING —
        // and then never delivers a sample. An 18-second call produced 0 chunks with no
        // error anywhere. Android has not permitted third-party capture of the remote
        // party since Android 10 (AudioSource.VOICE_CALL needs CAPTURE_AUDIO_OUTPUT, which
        // is signature|privileged), so the object succeeds and the audio simply never
        // arrives.
        //
        // MIC on speakerphone does work, because it picks the remote voice out of the air.
        // That is a worse channel — it costs real cosine against the enrolled voiceprint —
        // but a degraded signal that exists beats a clean one that does not.
        //
        // `openRecorder` therefore proves a source by reading from it before we commit,
        // rather than trusting state flags that lie here.
        val record = openRecorder(source, bufferSize)
            ?: (if (inCall) openRecorder(MediaRecorder.AudioSource.VOICE_COMMUNICATION, bufferSize) else null)

        if (record == null) {
            Log.e(TAG, "no audio source produced samples")
            listener?.onCaptureError("microphone unavailable, possibly held by the dialer")
            stopSelf()
            return
        }

        recorder = record
        running = true

        captureThread = thread(name = "satyacheck-capture", isDaemon = true) {
            readLoop(record, bufferSize)
        }
        Log.i(TAG, "capture started, session=$sessionId buffer=$bufferSize")
    }

    /**
     * Open a source and prove it actually delivers audio before committing to it.
     *
     * Every state flag AudioRecord exposes can report success on a source that yields
     * nothing: on Android 16, VOICE_COMMUNICATION during a cellular call initialises,
     * reports RECORDSTATE_RECORDING, and then never produces a sample. The only reliable
     * test is to read from it, so that is what this does.
     *
     * Returns a started recorder, or null if the source could not be opened or stayed
     * silent. The ~200 ms of audio consumed by the probe is discarded; that is the cost of
     * knowing the source works, and it is paid once at the start of a call.
     */
    private fun openRecorder(source: Int, bufferSize: Int): AudioRecord? {
        val name = if (source == MediaRecorder.AudioSource.VOICE_COMMUNICATION) {
            "VOICE_COMMUNICATION"
        } else {
            "MIC"
        }

        val record = try {
            AudioRecord(
                source,
                SAMPLE_RATE,
                AudioFormat.CHANNEL_IN_MONO,
                AudioFormat.ENCODING_PCM_16BIT,
                bufferSize
            )
        } catch (t: Throwable) {
            Log.e(TAG, "$name: AudioRecord construction failed", t)
            return null
        }

        if (record.state != AudioRecord.STATE_INITIALIZED) {
            Log.w(TAG, "$name: did not initialise (state=${record.state})")
            record.release()
            return null
        }

        disableVoiceEffects(record.audioSessionId)

        try {
            record.startRecording()
        } catch (t: Throwable) {
            Log.w(TAG, "$name: startRecording threw", t)
            record.release()
            return null
        }

        if (record.recordingState != AudioRecord.RECORDSTATE_RECORDING) {
            Log.w(TAG, "$name: not recording after start (state=${record.recordingState})")
            record.stopSafely()
            return null
        }

        // The part that actually decides it: does a sample arrive?
        val probe = ShortArray(bufferSize / 2)
        var silentReads = 0
        val deadline = SystemClock.elapsedRealtime() + 1_200
        while (SystemClock.elapsedRealtime() < deadline) {
            val n = try {
                record.read(probe, 0, probe.size)
            } catch (t: Throwable) {
                Log.w(TAG, "$name: read threw during probe", t)
                break
            }
            if (n > 0) {
                // Sample COUNT is not evidence of audio. During a telephony call Android
                // gives the microphone exclusively to the dialer and hands every other app
                // digital silence — not an error, not a short read, just zeros. Measured
                // here: 576,000 consecutive samples from a live call, every one of them 0.
                // Checking `n > 0` passed that with flying colours, which is why the whole
                // stack reported success while nothing was being heard.
                var peak = 0
                for (i in 0 until n) {
                    val v = kotlin.math.abs(probe[i].toInt())
                    if (v > peak) peak = v
                }
                if (peak > SILENCE_FLOOR) {
                    Log.i(TAG, "$name: delivering audio ($n samples, peak=$peak)")
                    return record
                }
                silentReads++
                if (silentReads >= SILENT_PROBE_LIMIT) {
                    Log.w(TAG, "$name: returned only silence (peak<=$SILENCE_FLOOR over " +
                        "$silentReads reads); the OS is muting this source")
                    record.stopSafely()
                    return null
                }
            }
        }

        Log.w(TAG, "$name: opened but delivered no audio; trying the next source")
        record.stopSafely()
        return null
    }

    /** Stop and release without letting teardown throw over the real error. */
    private fun AudioRecord.stopSafely() {
        runCatching { if (recordingState == AudioRecord.RECORDSTATE_RECORDING) stop() }
        runCatching { release() }
    }

    private fun readLoop(record: AudioRecord, bufferSize: Int) {
        // 9-second windows, not 3.
        //
        // Whisper does not stay silent on too-little audio — it invents fluent sentences.
        // Measured on this project's own eval clips, the same recording sliced three ways:
        //
        //   3s windows -> "alert can product us from with the minger next week"  (invented)
        //   9s window  -> "never send money to unknown people and always verify" (correct)
        //
        // The backend's ASR gate does not catch this: it checks no_speech_prob and
        // repetition, and a fluent hallucination trips neither, so the garbage reaches
        // retrieval and the markers as if it were speech. Sending 3-second chunks would
        // feed the scoring pipeline noise and call it evidence.
        //
        // Waiting costs almost nothing: faster-whisper pads every input to a 30-second mel
        // window, so decoding 9 seconds costs about what decoding 3 seconds costs.
        //
        // 3s of overlap keeps a phrase spanning a boundary whole in at least one window.
        val ring = RingBuffer(
            sampleRate = SAMPLE_RATE,
            windowSeconds = 9.0,
            overlapSeconds = 3.0,
        )
        val scratch = ShortArray(bufferSize / 2)
        var index = 0
        var barren = 0
        var totalRead = 0L
        var reads = 0
        var silentRun = 0

        while (running) {
            val read = try {
                record.read(scratch, 0, scratch.size)
            } catch (t: Throwable) {
                Log.e(TAG, "read failed", t)
                break
            }

            if (read <= 0) {
                // Do not swallow ERROR_INVALID_OPERATION. It used to be treated as normal
                // teardown noise and skipped silently, which meant a source that never
                // delivered a sample span this loop for the whole call and looked exactly
                // like a healthy one — the bug that produced "0 chunk(s)" with no warning.
                if (running) {
                    barren++
                    if (barren == 1 || barren % 64 == 0) {
                        Log.w(TAG, "read returned $read (${barren} in a row)")
                    }
                    if (barren >= BARREN_LIMIT) {
                        Log.e(TAG, "no audio after $barren reads; giving up on this source")
                        listener?.onCaptureError("no audio is reaching the app from this call")
                        break
                    }
                }
                continue
            }
            barren = 0

            totalRead += read
            reads++

            var chunkPeak = 0
            for (i in 0 until read) {
                val v = kotlin.math.abs(scratch[i].toInt())
                if (v > chunkPeak) chunkPeak = v
            }
            if (chunkPeak <= SILENCE_FLOOR) {
                silentRun++
                if (silentRun == SILENT_RUN_LIMIT) {
                    Log.e(TAG, "microphone has returned pure silence for " +
                        "${silentRun * scratch.size / SAMPLE_RATE}s — Android is muting " +
                        "this app for the duration of the call")
                    listener?.onCaptureError(
                        "Android is blocking microphone access during this call"
                    )
                }
            } else {
                silentRun = 0
            }
            // Heartbeat: the in-call path produced "0 chunk(s)" with no warning anywhere,
            // and every explanation for that (dead listener, null session, failing reads)
            // was disproved in turn. Print the actual state instead of inferring it.
            if (reads % 32 == 0) {
                Log.i(
                    TAG,
                    "heartbeat reads=$reads samples=$totalRead (${totalRead / SAMPLE_RATE}s) " +
                        "peak=$chunkPeak silentRun=$silentRun " +
                        "ring=${ring.available} session=${sessionId != null} " +
                        "listener=${listener != null} emitted=$index"
                )
            }

            val session = sessionId
            if (session == null) {
                if (reads % 32 == 0) Log.w(TAG, "session id is null; dropping window")
                continue
            }
            for (window in ring.append(scratch, read)) {
                val l = listener
                if (l == null) {
                    Log.w(TAG, "window ready but no listener attached; dropping")
                    continue
                }
                l.onChunk(session, index++, window, SAMPLE_RATE)
            }
        }

        // The tail is often where the payment demand lands. Send it if it is long enough
        // to be worth scoring.
        ring.drain()?.let { tail ->
            sessionId?.let { session -> listener?.onChunk(session, index, tail, SAMPLE_RATE) }
        }
        Log.i(TAG, "capture loop ended after $index chunk(s)")
    }

    private fun endCapture() {
        running = false
        captureThread?.join(1_000)
        captureThread = null

        recorder?.let { record ->
            runCatching { if (record.recordingState == AudioRecord.RECORDSTATE_RECORDING) record.stop() }
                .onFailure { Log.w(TAG, "stop failed", it) }
            runCatching { record.release() }
        }
        recorder = null

        releaseVoiceEffects()
    }

    // --- audio routing (M4) ------------------------------------------------------

    /**
     * Route the call to the speaker so the far end is audible to the microphone.
     *
     * MODE_IN_COMMUNICATION must be set before the speakerphone flag; setting the flag in
     * MODE_NORMAL is silently ignored on most devices. The previous values are saved and
     * restored, because leaving a phone stuck on speakerphone after a call is a genuinely
     * obnoxious bug.
     */
    private fun forceSpeakerphone() {
        val audio = getSystemService(Context.AUDIO_SERVICE) as AudioManager
        previousAudioMode = audio.mode
        @Suppress("DEPRECATION")
        previousSpeakerphone = audio.isSpeakerphoneOn

        // Only when a call is actually up. Forcing MODE_IN_COMMUNICATION with no call
        // switches the whole device into a call-audio configuration — it puts the mic
        // through call pre-processing and can mute other apps' playback — which is both
        // wrong for a test capture and the reason those captures came back unintelligible.
        if (audio.mode != AudioManager.MODE_IN_CALL &&
            audio.mode != AudioManager.MODE_IN_COMMUNICATION
        ) {
            Log.i(TAG, "no call in progress; leaving the audio route alone")
            return
        }

        // `isSpeakerphoneOn = true` alone is not enough and was reporting success falsely.
        // It has been deprecated since API 31, and on a modern release it is a no-op for an
        // ordinary app — which is why this used to log "speakerphone forced on for the
        // call" while the handset stayed on the earpiece. Set the communication device
        // instead, then read the route back rather than trusting the setter.
        var onSpeaker = false
        runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                val speaker = audio.availableCommunicationDevices.firstOrNull {
                    it.type == AudioDeviceInfo.TYPE_BUILTIN_SPEAKER
                }
                if (speaker != null) {
                    onSpeaker = audio.setCommunicationDevice(speaker)
                }
            }
            if (!onSpeaker) {
                @Suppress("DEPRECATION")
                audio.isSpeakerphoneOn = true
                @Suppress("DEPRECATION")
                onSpeaker = audio.isSpeakerphoneOn
            }
        }.onFailure { Log.w(TAG, "could not force speakerphone", it) }

        if (onSpeaker) {
            Log.i(TAG, "speakerphone on for the call")
        } else {
            // Expected on a cellular call. Android gives the telephony audio route to the
            // default dialer's InCallService; a third-party app cannot take it. Nothing to
            // fix in code — but the user has to know, because on the earpiece path the
            // remote voice never reaches our microphone and the call scores on our side of
            // the conversation only.
            Log.w(TAG, "could not route to speaker; the dialer owns the cellular call route")
            OverlayManager.show(this, "Tap Speaker so the caller can be heard")
        }
    }

    private fun restoreAudioRoute() {
        val audio = getSystemService(Context.AUDIO_SERVICE) as AudioManager
        runCatching {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
                runCatching { audio.clearCommunicationDevice() }
            }
            @Suppress("DEPRECATION")
            audio.isSpeakerphoneOn = previousSpeakerphone
            audio.mode = previousAudioMode
        }.onFailure { Log.w(TAG, "could not restore audio route", it) }
    }

    // --- effects ------------------------------------------------------------------

    /**
     * Turn off the three voice-call enhancements. See the class docstring: each of them
     * removes part of the signal this app measures, and AEC removes the far end entirely.
     *
     * Availability varies by device. `isAvailable()` returning false is normal, not an error.
     */
    private fun disableVoiceEffects(audioSessionId: Int) {
        runCatching {
            if (AcousticEchoCanceler.isAvailable()) {
                echoCanceler = AcousticEchoCanceler.create(audioSessionId)?.apply { enabled = false }
            }
            if (NoiseSuppressor.isAvailable()) {
                noiseSuppressor = NoiseSuppressor.create(audioSessionId)?.apply { enabled = false }
            }
            if (AutomaticGainControl.isAvailable()) {
                gainControl = AutomaticGainControl.create(audioSessionId)?.apply { enabled = false }
            }
        }.onFailure { Log.w(TAG, "could not disable voice effects", it) }

        Log.i(
            TAG,
            "effects disabled — aec=${echoCanceler != null} ns=${noiseSuppressor != null} agc=${gainControl != null}"
        )
    }

    private fun releaseVoiceEffects() {
        runCatching { echoCanceler?.release() }
        runCatching { noiseSuppressor?.release() }
        runCatching { gainControl?.release() }
        echoCanceler = null
        noiseSuppressor = null
        gainControl = null
    }

    // --- notification --------------------------------------------------------------

    private fun buildNotification(): Notification {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val channel = NotificationChannel(
                CHANNEL_ID,
                "Call screening",
                // LOW: no sound, no vibration. This fires during a live call and must not
                // interrupt it. The alert channel in M6 is the one that is allowed to shout.
                NotificationManager.IMPORTANCE_LOW
            ).apply { description = "Shown while SatyaCheck is screening a call" }
            manager.createNotificationChannel(channel)
        }

        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }

        return builder
            .setContentTitle("Screening this call")
            .setContentText("Listening for known scam patterns")
            .setSmallIcon(android.R.drawable.ic_lock_silent_mode_off)
            .setOngoing(true)
            .build()
    }
}
