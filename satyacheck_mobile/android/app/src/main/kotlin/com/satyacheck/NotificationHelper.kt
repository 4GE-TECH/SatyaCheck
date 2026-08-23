package com.satyacheck

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.os.Build
import android.util.Log

/**
 * M6 — the verdict, as a notification.
 *
 * The overlay is the in-call surface; this is what survives the call. Someone who was
 * pressured into hanging up and calling a number back needs to still see the warning after
 * the screen returns to the launcher.
 *
 * TWO CHANNELS, ON PURPOSE
 *
 * A red verdict earns sound and vibration. A green one does not — a screening app that
 * buzzes on every legitimate call gets muted within a day, and then it is not there for the
 * one call that mattered. Android channel importance cannot be changed after creation, so
 * the split has to be by channel rather than per-notification priority.
 *
 * Grey (unverified / insufficient) posts nothing at all. "We could not tell" is not news,
 * and pushing it as a notification would train the exact indifference this is trying to
 * avoid.
 */
object NotificationHelper {

    private const val TAG = "SatyaCheck/Notify"

    private const val CHANNEL_ALERT = "com.satyacheck.alerts"
    private const val CHANNEL_INFO = "com.satyacheck.results"

    /** Stable id, so a later verdict for the same call replaces the earlier one. */
    private const val VERDICT_ID = 4301

    /** Signals mirroring `models.dart` — the values Dart sends across the channel. */
    const val GREEN = "green"
    const val AMBER = "amber"
    const val RED = "red"
    const val GREY = "grey"

    fun show(context: Context, signal: String, title: String, body: String) {
        if (signal == GREY) {
            // Nothing useful to say. See the class docstring.
            return
        }

        val manager =
            context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        ensureChannels(manager)

        val channel = if (signal == RED) CHANNEL_ALERT else CHANNEL_INFO

        val open = PendingIntent.getActivity(
            context,
            0,
            Intent(context, MainActivity::class.java)
                .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP),
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )

        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(context, channel)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(context).setPriority(
                if (signal == RED) Notification.PRIORITY_HIGH else Notification.PRIORITY_DEFAULT
            )
        }

        val notification = builder
            .setContentTitle(title)
            .setContentText(body)
            // The body carries the reason and can run long; without BigTextStyle it is
            // silently truncated to one line, which is where the evidence lives.
            .setStyle(Notification.BigTextStyle().bigText(body))
            .setSmallIcon(
                if (signal == RED) android.R.drawable.stat_notify_error
                else android.R.drawable.stat_notify_chat
            )
            .setColor(colorFor(signal))
            .setContentIntent(open)
            .setAutoCancel(true)
            .build()

        try {
            manager.notify(VERDICT_ID, notification)
        } catch (t: Throwable) {
            // POST_NOTIFICATIONS may be denied on API 33+. Not being able to notify must
            // not take down a call in progress.
            Log.w(TAG, "could not post verdict notification", t)
        }
    }

    fun clear(context: Context) {
        val manager =
            context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        runCatching { manager.cancel(VERDICT_ID) }
    }

    private fun ensureChannels(manager: NotificationManager) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return

        if (manager.getNotificationChannel(CHANNEL_ALERT) == null) {
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ALERT,
                    "Scam alerts",
                    NotificationManager.IMPORTANCE_HIGH
                ).apply {
                    description = "Shown when a call matches a known scam pattern"
                    enableVibration(true)
                    enableLights(true)
                    lightColor = Color.RED
                }
            )
        }

        if (manager.getNotificationChannel(CHANNEL_INFO) == null) {
            manager.createNotificationChannel(
                NotificationChannel(
                    CHANNEL_INFO,
                    "Call results",
                    // DEFAULT, not HIGH: silent. A verified or merely-cautious call is
                    // information, not an emergency.
                    NotificationManager.IMPORTANCE_DEFAULT
                ).apply {
                    description = "The result of screening a call"
                    enableVibration(false)
                }
            )
        }
    }

    private fun colorFor(signal: String): Int = when (signal) {
        RED -> Color.parseColor("#DC2626")
        AMBER -> Color.parseColor("#D97706")
        GREEN -> Color.parseColor("#16A34A")
        else -> Color.parseColor("#6B7280")
    }
}
