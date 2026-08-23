# SatyaCheck mobile

Flutter + Kotlin call-screening client. Dart never touches Android APIs and Kotlin never
makes HTTP calls — audio comes up through one MethodChannel, and Dart talks to the backend.

---

## Build prerequisites

| | version | note |
|---|---|---|
| Flutter | 3.47+ | Gradle files must be `.gradle.kts`; Groovy files fail with a misleading `Could not determine run package name` |
| Android Studio | with SDK + JDK 17 | Gradle needs a JDK, not a JRE |
| Android SDK | `compileSdk` / `ndkVersion` from Flutter | never pin literals — pinned versions get unpublished and break the build |

`android/local.properties` must contain both:

```properties
sdk.dir=C\:\\Users\\<you>\\AppData\\Local\\Android\\Sdk
flutter.sdk=C\:\\flutter
```

### If Gradle cannot resolve dependencies behind TLS interception

Antivirus products that scan HTTPS (AVG, Kaspersky, ESET) re-sign every certificate, and
Gradle's JVM rejects the substituted root. **Do not disable certificate verification.** Add
the interceptor's root to a private truststore instead:

```bash
keytool -importcert -alias av-root -file av-root.cer \
        -keystore ~/.satyacheck/cacerts -storepass changeit -noprompt
```

then reference it from `android/gradle.properties` **and** `JAVA_TOOL_OPTIONS` — Gradle's
daemon and its workers read different ones.

---

## Running against the backend

```bash
# 1. backend on the laptop
python -m uvicorn server.main:app --host 0.0.0.0 --port 8000

# 2. USB tunnel — the phone's localhost:8000 becomes the laptop's
adb reverse tcp:8000 tcp:8000

# 3. install and run
flutter run
```

**USB, not Wi-Fi.** `adb reverse` needs no network, survives the laptop being on Ethernet,
and is unaffected by the Windows firewall — none of which is true of a LAN address. For
Wi-Fi anyway, pass the laptop's LAN IP (never `localhost`, which on a phone means the
phone):

```bash
flutter run --dart-define=SATYACHECK_BACKEND=http://192.168.1.42:8000
```

### `adb reverse` dies on every USB replug

This is the single most common failure and it presents as *"cannot reach the screening
server"*. The app also caches the reachable flag at startup, so restoring the tunnel is not
enough on its own:

```bash
adb reverse --remove-all
adb reverse tcp:8000 tcp:8000
adb shell am force-stop com.satyacheck
```

Then reopen the app.

---

## Permissions

Four, and one of them is not a dialog:

| permission | why | how |
|---|---|---|
| `RECORD_AUDIO` | capture | runtime dialog |
| `READ_PHONE_STATE` | detect ringing / answered | runtime dialog |
| `POST_NOTIFICATIONS` | foreground service notice | runtime dialog |
| `SYSTEM_ALERT_WINDOW` | the overlay during a call | **Settings screen**, not a dialog |

---

## Known platform limit — call audio cannot be recorded

**Android gives the microphone exclusively to the dialer during a telephony call and hands
every other app digital silence.** Not an error, not a short read — zeros.

Measured on a Galaxy S23 FE running Android 16: 576,000 consecutive samples captured during
a live call, every one of them zero. Android's own audio service logs it:

```
rec start ... src:VOICE_COMMUNICATION silenced pack:com.satyacheck
```

`AudioRecord` opens, reports `RECORDSTATE_RECORDING`, and `read()` returns full buffers, so
every layer reports success while nothing is heard. There is no workaround:
`AudioSource.VOICE_CALL` requires `CAPTURE_AUDIO_OUTPUT`, which is `signature|privileged`;
Google closed third-party call recording in Android 10 and the accessibility route in
Android 11.

`CallAudioService` now detects OS-substituted silence — it checks sample *amplitude*, not
sample count — and surfaces *"Android is blocking microphone access during this call"*
rather than silently producing `unverified` verdicts.

The paths that do work:

- **Demo callers** in the app — bundled clips screened through the real backend.
- **`scripts/live_screen.py`** on the laptop — a bystanding device is under no restriction.
- **Manual capture** on a phone that is *not* the one in the call.

Speakerphone routing is also owned by the dialer's `InCallService`. The app requests it via
`setCommunicationDevice()` and reads the route back, but on a cellular call the user may
still have to tap Speaker; the overlay says so when the request is refused.

---

## Architecture

```
CallStateReceiver   PHONE_STATE -> RINGING / OFFHOOK / IDLE, de-duplicated
CallAudioService    foreground service, holds the mic, 9s windows / 3s overlap
RingBuffer          pure arithmetic, unit-tested without a device
OverlayManager      SYSTEM_ALERT_WINDOW banner
VoiceRecorder       enrollment capture with live level metering
MainActivity        the only MethodChannel bridge

lib/native_bridge   Dart side of that channel
lib/call_session    orchestration; owns the WebSocket
lib/api_client      the only place that makes network calls
```

**9-second windows, not 3.** Whisper does not stay quiet on too-little audio — it invents
fluent sentences. Measured on the same recording: a 3s slice returned *"alert can product us
from with the minger next week"*; the 9s window returned the actual sentence. The ASR gate
checks `no_speech_prob` and repetition, and a fluent hallucination trips neither.

---

## Tests

```bash
flutter test                                    # Dart
./gradlew :app:testDebugUnitTest                # RingBuffer
```
