package com.satyacheck

import android.content.Context
import android.content.Intent
import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.net.Uri
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.util.TypedValue
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.widget.LinearLayout
import android.widget.TextView

/**
 * M2 — a small always-on-top banner shown during a screened call.
 *
 * Deliberately **non-interactive**. It reports; it does not ask. During a call the user is
 * already talking to someone and possibly being pressured — a dialog demanding a decision is
 * the worst possible interruption, and a tappable overlay covering the dialer risks the user
 * hanging up on a real call by accident. FLAG_NOT_FOCUSABLE and FLAG_NOT_TOUCH_MODAL let
 * every touch pass straight through to the dialer underneath.
 *
 * PERMISSION, WHICH IS NOT LIKE THE OTHERS
 *
 * `SYSTEM_ALERT_WINDOW` cannot be granted by `requestPermissions()`. The user has to approve
 * it on a dedicated Settings screen, reached with ACTION_MANAGE_OVERLAY_PERMISSION. Calling
 * `addView` without it throws `BadTokenException` and takes the process down, so every entry
 * point checks `canDrawOverlays` first and degrades to a log line.
 *
 * All window operations must run on the main thread; the call-state receiver already does,
 * but the audio service does not, so everything here is posted to the main looper.
 */
object OverlayManager {

    private const val TAG = "SatyaCheck/Overlay"

    private val main = Handler(Looper.getMainLooper())

    private var view: View? = null
    private var label: TextView? = null

    /** True when the user has granted the overlay permission. */
    fun canShow(context: Context): Boolean =
        Build.VERSION.SDK_INT < Build.VERSION_CODES.M || Settings.canDrawOverlays(context)

    /**
     * Send the user to the system screen where the overlay permission is granted.
     *
     * Returns false when the permission is already held, so the caller can skip the trip.
     */
    fun requestPermission(context: Context): Boolean {
        if (canShow(context)) return false
        val intent = Intent(
            Settings.ACTION_MANAGE_OVERLAY_PERMISSION,
            Uri.parse("package:${context.packageName}")
        ).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        runCatching { context.startActivity(intent) }
            .onFailure { Log.e(TAG, "could not open overlay settings", it) }
        return true
    }

    /**
     * Show the banner, or update it if already up. Safe to call repeatedly.
     *
     * `signal` tints the background: green / amber / red / grey. Grey is the default and
     * the resting state — a screening in progress has verified nobody, and an unknown
     * caller is not an accusation.
     */
    fun show(context: Context, text: String, signal: String = "grey") {
        val app = context.applicationContext
        main.post {
            if (!canShow(app)) {
                Log.w(TAG, "overlay permission not granted; not showing \"$text\"")
                return@post
            }
            try {
                if (view == null) attach(app)
                label?.text = text
                (view?.background as? GradientDrawable)?.setColor(backgroundFor(signal))
            } catch (t: Throwable) {
                // An overlay that fails must never take the call down with it.
                Log.e(TAG, "failed to show overlay", t)
                view = null
                label = null
            }
        }
    }

    /** Opaque enough to read over a dialer, tinted by verdict. */
    private fun backgroundFor(signal: String): Int = when (signal) {
        "red" -> Color.parseColor("#EEDC2626")
        "amber" -> Color.parseColor("#EED97706")
        "green" -> Color.parseColor("#EE16A34A")
        else -> Color.parseColor("#DD1F2937")
    }

    /** Remove the banner. Safe when nothing is showing. */
    fun hide(context: Context) {
        val app = context.applicationContext
        main.post {
            val current = view ?: return@post
            runCatching { windowManager(app).removeView(current) }
                .onFailure { Log.w(TAG, "removeView failed; view was likely already gone", it) }
            view = null
            label = null
        }
    }

    // --- internals -------------------------------------------------------------

    private fun attach(context: Context) {
        val text = TextView(context).apply {
            setTextColor(Color.WHITE)
            setTextSize(TypedValue.COMPLEX_UNIT_SP, 16f)
            // CLAUDE.md: "Large type — a judge reads this from three metres away."
            val pad = dp(context, 14)
            setPadding(pad, dp(context, 10), pad, dp(context, 10))
        }

        val container = LinearLayout(context).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            background = GradientDrawable().apply {
                cornerRadius = dp(context, 12).toFloat()
                // Neutral grey while unresolved. Never green: a screening in progress has
                // verified nobody, and green means "we verified this person".
                setColor(Color.parseColor("#DD1F2937"))
            }
            addView(text)
        }

        val params = WindowManager.LayoutParams(
            WindowManager.LayoutParams.WRAP_CONTENT,
            WindowManager.LayoutParams.WRAP_CONTENT,
            overlayType(),
            // NOT_FOCUSABLE keeps the dialer's keypad working; NOT_TOUCH_MODAL passes
            // touches through. Together they make this a heads-up display, not a dialog.
            WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                WindowManager.LayoutParams.FLAG_NOT_TOUCH_MODAL,
            android.graphics.PixelFormat.TRANSLUCENT
        ).apply {
            gravity = Gravity.TOP or Gravity.CENTER_HORIZONTAL
            y = dp(context, 48)
        }

        windowManager(context).addView(container, params)
        view = container
        label = text
    }

    private fun windowManager(context: Context): WindowManager =
        context.getSystemService(Context.WINDOW_SERVICE) as WindowManager

    /**
     * TYPE_APPLICATION_OVERLAY from API 26. The older TYPE_PHONE still compiles but is
     * ignored on modern Android, so a single constant would silently fail on one side.
     */
    @Suppress("DEPRECATION")
    private fun overlayType(): Int =
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O)
            WindowManager.LayoutParams.TYPE_APPLICATION_OVERLAY
        else
            WindowManager.LayoutParams.TYPE_PHONE

    private fun dp(context: Context, value: Int): Int =
        (value * context.resources.displayMetrics.density).toInt()
}
