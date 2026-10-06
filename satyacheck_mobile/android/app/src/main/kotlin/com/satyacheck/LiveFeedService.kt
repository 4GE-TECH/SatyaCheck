package com.satyacheck

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.content.ContextCompat

/**
 * Keeps the app allowed on the network while the backend's live feed screens calls.
 *
 * During a call the dialer is in front and this app is in the background, and Android 15+
 * blocks network access for background apps. Measured on the OnePlus test phone:
 * `dumpsys netpolicy` reports `blocked=APP_BACKGROUND` for the app, the live-feed socket
 * broke a few seconds into every Exotel call (Dart reports it as close code 1002), and
 * every reconnect failed until the call ended — so the overlay froze and the call's final
 * verdict was lost. A foreground service puts the process outside that policy.
 *
 * It does nothing else: no microphone, no audio, no network of its own. MainActivity
 * starts it while the app is on screen, which Android always allows, and stops it when the
 * live feed is turned off.
 */
class LiveFeedService : Service() {

    companion object {
        private const val TAG = "SatyaCheck/LiveFeedSvc"
        private const val CHANNEL_ID = "com.satyacheck.watching"
        private const val NOTIFICATION_ID = 4202

        fun start(context: Context) {
            try {
                ContextCompat.startForegroundService(
                    context, Intent(context, LiveFeedService::class.java)
                )
            } catch (e: Exception) {
                // ForegroundServiceStartNotAllowedException if this ever runs while the app
                // is not on screen. Without the service the feed still works whenever the
                // app is in front; say so instead of failing the caller.
                Log.w(TAG, "could not start; the live feed may drop during calls: $e")
            }
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, LiveFeedService::class.java))
        }
    }

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        val notification = buildNotification()
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.UPSIDE_DOWN_CAKE) {
            startForeground(
                NOTIFICATION_ID, notification, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE
            )
        } else {
            startForeground(NOTIFICATION_ID, notification)
        }
        Log.i(TAG, "running: network stays open for the live feed during calls")
        return START_NOT_STICKY
    }

    override fun onDestroy() {
        Log.i(TAG, "stopped")
        super.onDestroy()
    }

    private fun buildNotification(): Notification {
        val manager = getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    "Watching for calls",
                    // LOW: silent. It is on screen for as long as the feed is on.
                    NotificationManager.IMPORTANCE_LOW
                ).apply { description = "Shown while SatyaCheck follows the screening server" }
            )
        }
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(this, CHANNEL_ID)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(this)
        }
        return builder
            .setContentTitle("Watching for calls")
            .setContentText("Live verdicts from the screening server")
            .setSmallIcon(android.R.drawable.ic_lock_silent_mode_off)
            .setOngoing(true)
            .build()
    }
}
