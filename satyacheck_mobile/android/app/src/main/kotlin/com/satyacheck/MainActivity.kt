package com.satyacheck

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioManager
import android.media.MediaPlayer
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Base64
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.nio.ByteBuffer
import java.nio.ByteOrder

/**
 * The single bridge between Dart and the native call-screening pieces.
 *
 * `CLAUDE.md` for this folder: MethodChannel only. Dart never touches Android APIs and
 * Kotlin never makes HTTP calls — audio comes up to Dart, and Dart talks to the backend.
 *
 * Every callback into Dart is posted to the main thread. The audio capture callbacks arrive
 * on the recorder's own thread, and calling `invokeMethod` off the platform thread is a
 * crash on release builds and a silent no-op on some devices.
 */
class MainActivity : FlutterActivity(),
    CallStateReceiver.CallStateListener,
    CallAudioService.AudioChunkListener,
    VoiceRecorder.Listener {

    private val CHANNEL = "com.satyacheck/native"
    private val PERMISSION_REQUEST = 4200

    private var channel: MethodChannel? = null
    private val main = Handler(Looper.getMainLooper())

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)

        val methodChannel = MethodChannel(flutterEngine.dartExecutor.binaryMessenger, CHANNEL)
        channel = methodChannel

        CallStateReceiver.listener = this
        CallAudioService.listener = this
        VoiceRecorder.listener = this

        methodChannel.setMethodCallHandler { call, result ->
            when (call.method) {
                "getPlatformVersion" -> result.success(
                    "Android ${Build.VERSION.RELEASE} (API ${Build.VERSION.SDK_INT})"
                )

                // What is granted right now — Dart drives the setup screen from this.
                "getPermissionStatus" -> result.success(
                    mapOf(
                        "microphone" to hasPermission(Manifest.permission.RECORD_AUDIO),
                        "phoneState" to hasPermission(Manifest.permission.READ_PHONE_STATE),
                        "overlay" to OverlayManager.canShow(this),
                    )
                )

                // Microphone and phone state: the ordinary runtime dialog.
                "requestPermissions" -> {
                    requestRuntimePermissions()
                    result.success(true)
                }

                // The overlay is NOT grantable by dialog — it needs a trip to Settings.
                "requestOverlayPermission" -> result.success(
                    OverlayManager.requestPermission(this)
                )

                "isScreeningActive" -> result.success(CallAudioService.sessionId != null)

                // Manual start, for testing the capture path without waiting for a call.
                "startCapture" -> {
                    CallAudioService.start(this)
                    result.success(true)
                }

                "stopCapture" -> {
                    CallAudioService.stop(this)
                    result.success(true)
                }

                "updateOverlay" -> {
                    val text = call.argument<String>("text") ?: "Checking…"
                    val signal = call.argument<String>("signal") ?: "grey"
                    OverlayManager.show(this, text, signal)
                    result.success(true)
                }

                "hideOverlay" -> {
                    OverlayManager.hide(this)
                    result.success(true)
                }

                // --- enrollment recording ---------------------------------------
                "startRecording" -> {
                    val file = java.io.File(cacheDir, "enrollment.wav")
                    result.success(
                        if (VoiceRecorder.start(file)) file.absolutePath else null
                    )
                }

                "stopRecording" -> result.success(VoiceRecorder.stop()?.absolutePath)

                "isRecording" -> result.success(VoiceRecorder.isRecording)

                // Play a demo clip out loud, so the room hears the call being screened.
                //
                // A verdict card turning red is a claim; hearing a cloned voice ask for
                // money and *then* seeing it turn red is evidence. Routed to the speaker
                // explicitly — the media stream defaults to the earpiece on some handsets
                // once a call has put the device in communication mode, and a demo nobody
                // can hear is worse than no demo.
                "playClip" -> {
                    val path = call.argument<String>("path")
                    if (path.isNullOrBlank()) {
                        result.success(0)
                    } else {
                        result.success(playClip(path))
                    }
                }

                "stopClip" -> {
                    stopClip()
                    result.success(true)
                }

                // The verdict, as something that survives the call ending.
                "showVerdictNotification" -> {
                    NotificationHelper.show(
                        this,
                        call.argument<String>("signal") ?: "grey",
                        call.argument<String>("title") ?: "Call screened",
                        call.argument<String>("body") ?: "",
                    )
                    result.success(true)
                }

                "clearVerdictNotification" -> {
                    NotificationHelper.clear(this)
                    result.success(true)
                }

                else -> result.notImplemented()
            }
        }
    }

    override fun onDestroy() {
        // Leaving these set would keep a destroyed activity alive through the static
        // listener fields and post to a dead channel.
        if (CallStateReceiver.listener === this) CallStateReceiver.listener = null
        if (CallAudioService.listener === this) CallAudioService.listener = null
        if (VoiceRecorder.listener === this) VoiceRecorder.listener = null
        stopClip()
        channel = null
        super.onDestroy()
    }

    // --- call state (M1) ---------------------------------------------------------

    override fun onCallRinging(incomingNumber: String?) =
        send("onCallRinging", mapOf("number" to incomingNumber))

    override fun onCallAnswered() = send("onCallAnswered", null)

    override fun onCallEnded() = send("onCallEnded", null)

    // --- audio (M3) ---------------------------------------------------------------

    override fun onChunk(sessionId: String, index: Int, pcm16: ShortArray, sampleRate: Int) {
        // Base64 rather than a raw byte array: the standard codec handles it on every
        // Flutter version, and a 3-second 16 kHz window is ~128 KB encoded — small enough
        // that the copy is not worth optimising away before it is measured.
        send(
            "onAudioChunk",
            mapOf(
                "sessionId" to sessionId,
                "index" to index,
                "sampleRate" to sampleRate,
                "durationMs" to (pcm16.size * 1000L / sampleRate),
                "pcm16Base64" to Base64.encodeToString(toLittleEndianBytes(pcm16), Base64.NO_WRAP),
            )
        )
    }

    override fun onCaptureError(reason: String) =
        send("onCaptureError", mapOf("reason" to reason))

    // --- enrollment recording -----------------------------------------------------

    override fun onLevel(level: Double, seconds: Double) =
        send("onRecordLevel", mapOf("level" to level, "seconds" to seconds))

    override fun onRecorderError(reason: String) =
        send("onRecorderError", mapOf("reason" to reason))

    // --- demo playback ---------------------------------------------------------

    private var player: MediaPlayer? = null

    /** Start playback and return the clip's length in milliseconds (0 if it failed). */
    private fun playClip(path: String): Int {
        stopClip()
        return try {
            val audio = getSystemService(Context.AUDIO_SERVICE) as AudioManager
            audio.mode = AudioManager.MODE_NORMAL
            val mp = MediaPlayer().apply {
                setAudioAttributes(
                    AudioAttributes.Builder()
                        .setUsage(AudioAttributes.USAGE_MEDIA)
                        .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                        .build()
                )
                setDataSource(path)
                prepare()
                start()
            }
            mp.setOnCompletionListener {
                it.release()
                if (player === it) player = null
            }
            player = mp
            // The caller uses this to hold the verdict back until the voice has finished.
            // Revealing "likely scam" while the clone is still mid-sentence steps on the
            // one moment the whole walkthrough exists for.
            mp.duration.coerceAtLeast(0)
        } catch (t: Throwable) {
            android.util.Log.w("SatyaCheck/Demo", "could not play $path", t)
            0
        }
    }

    private fun stopClip() {
        player?.let { p ->
            runCatching { if (p.isPlaying) p.stop() }
            runCatching { p.release() }
        }
        player = null
    }

    // --- helpers -------------------------------------------------------------------

    private fun send(method: String, args: Map<String, Any?>?) {
        main.post { channel?.invokeMethod(method, args) }
    }

    /**
     * PCM16 little-endian, which is what WAV expects and what the backend's ffmpeg step
     * reads. Explicit byte order, because ByteBuffer defaults to big-endian and the
     * resulting audio is white noise — a mistake that looks like a broken microphone.
     */
    private fun toLittleEndianBytes(samples: ShortArray): ByteArray {
        val buffer = ByteBuffer.allocate(samples.size * 2).order(ByteOrder.LITTLE_ENDIAN)
        buffer.asShortBuffer().put(samples)
        return buffer.array()
    }

    private fun hasPermission(permission: String): Boolean =
        ContextCompat.checkSelfPermission(this, permission) == PackageManager.PERMISSION_GRANTED

    private fun requestRuntimePermissions() {
        val wanted = mutableListOf(Manifest.permission.RECORD_AUDIO, Manifest.permission.READ_PHONE_STATE)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
            wanted += Manifest.permission.POST_NOTIFICATIONS
        }
        val missing = wanted.filterNot { hasPermission(it) }
        if (missing.isNotEmpty()) {
            ActivityCompat.requestPermissions(this, missing.toTypedArray(), PERMISSION_REQUEST)
        }
    }

    override fun onRequestPermissionsResult(
        requestCode: Int,
        permissions: Array<out String>,
        grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode != PERMISSION_REQUEST) return
        send(
            "onPermissionsChanged",
            mapOf(
                "microphone" to hasPermission(Manifest.permission.RECORD_AUDIO),
                "phoneState" to hasPermission(Manifest.permission.READ_PHONE_STATE),
                "overlay" to OverlayManager.canShow(this),
            )
        )
    }
}
