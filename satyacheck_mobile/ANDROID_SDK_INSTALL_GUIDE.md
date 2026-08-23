# Android SDK Installation Guide

## Quick Summary

You need **Android SDK API 34** to build M0. Flutter is already installed at `/c/flutter`.

## Step 1: Install Android Studio (Easiest)

**Download:**
- Go to https://developer.android.com/studio
- Download for your OS (Windows/Mac/Linux)
- Run the installer

**During Installation:**
1. Accept the license agreement
2. Select "Standard installation" (recommended)
3. Choose installation location:
   - Windows: `C:\Users\<YourName>\AppData\Local\Android\sdk`
   - Mac: `~/Library/Android/sdk`
   - Linux: `~/Android/sdk`

**After Installation:**
1. Open Android Studio
2. Go to **Settings > Languages & Frameworks > Android SDK**
3. Verify **API Level 34** is installed (checked box)
4. Click **Apply** and wait for download to complete

---

## Step 2: Auto-Configure local.properties

Run the setup script:

**Windows (PowerShell):**
```powershell
cd satyacheck_mobile
.\SETUP_ANDROID_SDK.bat
```

**Linux/Mac (Bash):**
```bash
cd satyacheck_mobile
chmod +x SETUP_ANDROID_SDK.sh
./SETUP_ANDROID_SDK.sh
```

This will:
- ✓ Find your Flutter path
- ✓ Find your Android SDK path
- ✓ Auto-generate `android/local.properties`

---

## Step 3: Build & Run

```bash
cd satyacheck_mobile
flutter pub get
flutter build apk --debug
adb install -r build/app/outputs/apk/debug/app-debug.apk
flutter run
```

---

## Troubleshooting

### "Android SDK not found"
- Verify Android Studio installed completely
- Check that API 34 is present in Android Studio > Settings > SDK
- Run the setup script again

### "adb: command not found"
Add Android platform-tools to PATH:

**Windows:**
```powershell
$env:PATH += ";C:\Users\<YourName>\AppData\Local\Android\sdk\platform-tools"
```

**Mac/Linux:**
```bash
export PATH=$PATH:~/Android/sdk/platform-tools
```

### "Device not detected"
```bash
adb devices
```

If empty:
1. Enable **Developer Mode** on your Samsung (Settings > About > tap Build Number 7 times)
2. Enable **USB Debugging** (Settings > Developer Options > USB Debugging)
3. Plug in phone and run `adb devices` again

---

## Manual Permissions (None for M0)

M0 requires **zero manual permissions**. Just build and run.

---

**Once Android SDK is installed and `local.properties` is generated, post that you're ready and I'll verify the build.**
