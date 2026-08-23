# M0: What You Need to Do Now

## Current Status

✅ **Flutter**: Found at `/c/flutter`  
✅ **M0 Code**: Complete (pubspec.yaml, main.dart, MainActivity.kt, etc.)  
❌ **Android SDK**: Not installed

---

## Action Items

### 1. Install Android Studio (15 min)

```
https://developer.android.com/studio
```

During setup, ensure **API 34** is selected for download.

### 2. Auto-Configure (1 min)

Once Android Studio is installed, run:

**Windows:**
```
cd satyacheck_mobile
SETUP_ANDROID_SDK.bat
```

**Mac/Linux:**
```
cd satyacheck_mobile
bash SETUP_ANDROID_SDK.sh
```

This auto-generates `android/local.properties` with your paths.

### 3. Build & Install (5 min)

```bash
cd satyacheck_mobile
flutter pub get
flutter build apk --debug
adb install -r build/app/outputs/apk/debug/app-debug.apk
flutter run
```

### 4. Grant Manual Permissions (0 min for M0)

M0 requires **no manual permissions**.

---

## What Should Happen

1. App launches with title "SatyaCheck M0 - MethodChannel Test"
2. Screen displays your Android version: **"Kotlin says: Android 13 (API 33)"** (or your version)
3. Tap "Call Kotlin Again" → updates immediately
4. No crashes

---

## Files Provided

- **M0_BUILD_INSTRUCTIONS.md** — Detailed build steps
- **ANDROID_SDK_INSTALL_GUIDE.md** — SDK installation walkthrough
- **SETUP_ANDROID_SDK.bat** — Auto-config (Windows)
- **SETUP_ANDROID_SDK.sh** — Auto-config (Mac/Linux)
- **M0_SUMMARY.md** — Quick reference

---

## Next Message

Once you've installed Android SDK and run the setup script, reply with:
```
Setup complete. Ready to build.
```

And I'll verify the build and help with any errors.

---

**DO NOT build yet.** Android SDK must be installed first.
