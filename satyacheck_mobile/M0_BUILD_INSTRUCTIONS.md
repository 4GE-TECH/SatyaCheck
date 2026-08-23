# M0: MethodChannel Round-Trip Test

## What this does
Flutter app calls Kotlin, Kotlin returns the Android version, Flutter displays it.
Tests that the MethodChannel bridge between Flutter and Kotlin is working.

## Setup Prerequisites

1. **Flutter SDK** installed and in PATH
2. **Android SDK** installed (API 34+)
3. **Connected Samsung device** running Android 13+, with developer mode enabled
4. **adb** in PATH

## Build & Install

### Step 1: Set up local.properties
```bash
cd satyacheck_mobile/android
```

Edit `local.properties` and set:
```properties
sdk.dir=/path/to/android-sdk
flutter.sdk=/path/to/flutter
```

On Windows:
```properties
sdk.dir=C:\\Android\\sdk
flutter.sdk=C:\\flutter
```

### Step 2: Build the APK
```bash
cd satyacheck_mobile
flutter pub get
flutter build apk --debug
```

### Step 3: Install on connected device
```bash
adb install -r build/app/outputs/apk/debug/app-debug.apk
```

Or use:
```bash
flutter install
```

### Step 4: Run the app
```bash
flutter run
```

## What to see

1. App launches with title "SatyaCheck M0 - MethodChannel Test"
2. Screen displays: "Kotlin says: Android 13 (API 33)" (or your device version)
3. Tap "Call Kotlin Again" button — response updates immediately

## Manual Permissions (None for M0)

M0 requires NO permissions. The app only tests the MethodChannel bridge.

Permissions will be added as we implement M1-M7.

## Troubleshooting

### APK fails to build
```
Error: "android.usesCleartextTraffic not found"
```
→ Verify AndroidManifest.xml has the cleartext attribute set.

### App crashes on launch
```
MissingPluginException
```
→ Ensure MainActivity.kt extends FlutterActivity and configureFlutterEngine is called.
→ Rebuild and reinstall fresh.

### adb not found
→ Add Android SDK tools to PATH:
```bash
export PATH=$PATH:/path/to/android-sdk/platform-tools
```

### Device not detected
```bash
adb devices
```
Should show your device. If blank, enable USB debugging in Settings > Developer Options.

## Next: M1 (CallStateReceiver)

Once this passes review, we implement call state detection.
