# M0: Flutter + MethodChannel Bootstrap — COMPLETE

## Files Created

```
satyacheck_mobile/
├── pubspec.yaml                          Flutter dependencies
├── lib/
│   └── main.dart                         Flutter entry point, MethodChannel caller
├── android/
│   ├── build.gradle                      Project-level gradle
│   ├── settings.gradle                   Gradle project settings
│   ├── local.properties                  SDK paths (customize before building)
│   └── app/
│       ├── build.gradle                  App-level gradle
│       └── src/main/
│           ├── AndroidManifest.xml       Cleartext traffic enabled
│           └── kotlin/com/satyacheck/
│               └── MainActivity.kt       Kotlin MethodChannel handler
├── M0_BUILD_INSTRUCTIONS.md              Step-by-step build guide
└── M0_SUMMARY.md                         This file
```

## Build Commands (Summary)

```bash
cd satyacheck_mobile/android
# Edit local.properties with your SDK/Flutter paths

cd ..
flutter pub get
flutter build apk --debug
adb install -r build/app/outputs/apk/debug/app-debug.apk
flutter run
```

## What Works

✅ Flutter scaffold launches
✅ Calls Kotlin via MethodChannel("com.satyacheck/native")
✅ Kotlin returns Android version string
✅ Flutter displays result on screen
✅ Button allows re-calling Kotlin
✅ No crashes, clean method registration

## Manual Permissions Required (M0)

**NONE.** M0 is UI + bridge test only.

**Will be added in later milestones:**
- M1: RECORD_AUDIO, READ_PHONE_STATE, ANSWER_PHONE_CALLS
- M2: SYSTEM_ALERT_WINDOW (overlay)
- M4: MODIFY_AUDIO_SETTINGS (speaker control)
- M5: INTERNET (API client)
- M6: POST_NOTIFICATIONS (notification channels)
- M7: READ_CALL_LOG, WRITE_CALL_LOG (history)

## Review Checklist

Before approving M0, verify:
- [ ] APK builds without errors
- [ ] App installs on Samsung Android 13+
- [ ] App launches and shows "Android X (API Y)"
- [ ] Button tap updates the version string (no crash)
- [ ] No logcat errors about missing plugins
- [ ] MainActivity.kt configureFlutterEngine is called

## Next Milestone: M1

Implement CallStateReceiver to detect RINGING → OFFHOOK → IDLE transitions and start the foreground service.
