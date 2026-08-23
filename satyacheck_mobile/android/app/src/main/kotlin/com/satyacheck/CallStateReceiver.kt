package com.satyacheck

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.telephony.TelephonyManager
import android.util.Log

/**
 * M1 — listens for phone call state transitions and drives the rest of the app.
 *
 * The system broadcasts ACTION_PHONE_STATE on every change. The transitions that matter:
 *
 *     RINGING  -> an incoming call is arriving. Show the overlay.
 *     OFFHOOK  -> the call was answered (or an outgoing call started). Start capturing.
 *     IDLE     -> the call ended. Stop everything.
 *
 * TWO THINGS THAT ARE EASY TO GET WRONG HERE
 *
 * **The broadcast repeats.** Android delivers the same state more than once — on a dual-SIM
 * device it fires per subscription, and OEM dialers re-broadcast. Acting on every delivery
 * starts two recorders for one call. `lastState` de-duplicates.
 *
 * **IDLE arrives before RINGING has been seen** when the app starts mid-call, and after an
 * app restart the receiver has no memory. Treating a bare IDLE as "a call just ended" would
 * fire a stop for a call that never began, so IDLE only acts if a call was actually active.
 *
 * The receiver deliberately does no work itself. `onReceive` runs on the main thread with a
 * ~10 second budget before the system kills the process, so anything slower than a state
 * check belongs in the foreground service.
 */
class CallStateReceiver : BroadcastReceiver() {

    companion object {
        private const val TAG = "SatyaCheck/CallState"

        /**
         * The last state acted upon, shared across instances.
         *
         * The system constructs a *new* receiver for every broadcast, so per-instance state
         * would be lost between them and de-duplication would never work.
         */
        @Volatile
        private var lastState: String? = null

        /** Set by MainActivity so native call events can reach Dart. */
        @Volatile
        var listener: CallStateListener? = null

        /** Reset when a session ends, so a later call starts clean. */
        fun reset() {
            lastState = null
        }
    }

    /** What the Flutter side implements to hear about calls. */
    interface CallStateListener {
        fun onCallRinging(incomingNumber: String?)
        fun onCallAnswered()
        fun onCallEnded()
    }

    override fun onReceive(context: Context, intent: Intent) {
        if (intent.action != TelephonyManager.ACTION_PHONE_STATE_CHANGED) return

        val state = intent.getStringExtra(TelephonyManager.EXTRA_STATE) ?: return

        // Same state twice in a row is a duplicate broadcast, not a real transition.
        if (state == lastState) {
            Log.d(TAG, "ignoring duplicate broadcast: $state")
            return
        }
        val previous = lastState
        lastState = state

        // EXTRA_INCOMING_NUMBER needs READ_CALL_LOG on API 29+, which this app does not
        // request — the number is a nice-to-have for the overlay, never a signal. Absent
        // permission it is simply null, which every caller below tolerates.
        val incomingNumber = runCatching {
            @Suppress("DEPRECATION")
            intent.getStringExtra(TelephonyManager.EXTRA_INCOMING_NUMBER)
        }.getOrNull()

        Log.i(TAG, "call state ${previous ?: "-"} -> $state")

        when (state) {
            TelephonyManager.EXTRA_STATE_RINGING -> {
                listener?.onCallRinging(incomingNumber)
                OverlayManager.show(context, "Checking…")
            }

            TelephonyManager.EXTRA_STATE_OFFHOOK -> {
                // Answered, or an outgoing call began. Either way there is now live audio.
                listener?.onCallAnswered()
                OverlayManager.show(context, "Checking…")
                CallAudioService.start(context)
            }

            TelephonyManager.EXTRA_STATE_IDLE -> {
                // Only meaningful if a call was actually in progress. A bare IDLE on app
                // start is the normal resting state, not the end of anything.
                if (previous == null) {
                    Log.d(TAG, "IDLE with no prior call; nothing to tear down")
                    return
                }
                listener?.onCallEnded()
                CallAudioService.stop(context)
                OverlayManager.hide(context)
            }
        }
    }
}
