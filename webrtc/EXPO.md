# Building the Expo app

Validated on 2026-10-10 by following these steps in a fresh directory, up to a built debug
APK. The versions below are the ones that worked together. Change them together, not one
at a time.

| Package | Version |
|---|---|
| Expo SDK | 57 (`expo` 57.0.27, React 19.2.3, React Native 0.86.3) |
| `@livekit/react-native` | 3.0.0 |
| `@livekit/react-native-webrtc` | 144.2.0 |
| `livekit-client` | 2.22.4 |
| `@livekit/react-native-expo-plugin` | 1.0.3 |
| `@config-plugins/react-native-webrtc` | 15.0.2 |
| `@supabase/supabase-js` | 2.117.3 |
| `react-native-url-polyfill` | 4.0.0 |
| `expo-dev-client`, `expo-build-properties` | SDK 57 (`npx expo install` picks them) |

**Not Expo Go.** LiveKit needs native code, so you need a *development build*, which is your
own APK with the dev client inside. You build it once and then iterate in JavaScript with
Metro, as you would in Expo Go.

## 1. Create the app (anywhere, outside this repo)

```bash
npx create-expo-app@5.0.0 satyacheck-call --template blank-typescript@sdk-57
cd satyacheck-call
npx expo install expo-dev-client expo-build-properties \
  @livekit/react-native@3.0.0 @livekit/react-native-webrtc@144.2.0 livekit-client@2.22.4 \
  @livekit/react-native-expo-plugin@1.0.3 @config-plugins/react-native-webrtc@15.0.2 \
  @supabase/supabase-js@2.117.3 react-native-url-polyfill@4.0.0
```

## 2. `app.json`

`npx expo install` adds the two LiveKit plugins itself. Add these to the `expo` object:

```json
"android": {
  "package": "com.satyacheck.call",
  "permissions": ["android.permission.RECORD_AUDIO", "android.permission.MODIFY_AUDIO_SETTINGS",
                  "android.permission.INTERNET"]
},
"plugins": [
  "@livekit/react-native-expo-plugin",
  "@config-plugins/react-native-webrtc",
  ["expo-build-properties", { "android": { "usesCleartextTraffic": true } }]
]
```

`usesCleartextTraffic` allows the `http://` and `ws://` LAN addresses you test with. Android
blocks them in non-debug builds otherwise, and the app just fails to connect. Remove it once
the backend and LiveKit are behind HTTPS/WSS ([NETWORK.md](NETWORK.md)).

## 3. Configuration (`.env` in the app folder)

Expo reads `EXPO_PUBLIC_*` variables at build time:

```
EXPO_PUBLIC_BACKEND_URL=http://192.168.1.20:8000
EXPO_PUBLIC_SUPABASE_URL=https://<ref>.supabase.co
EXPO_PUBLIC_SUPABASE_ANON_KEY=<the project's public anon key>
```

Use the backend machine's LAN IP, never `localhost`: on a phone, `localhost` is the phone.
The LiveKit URL isn't configured here, because the backend returns it with each call.

## 4. `App.tsx`

This is the minimal working app. It type-checks against the versions above.

- Sign in with an emailed code.
- Start a call (get a code to share) or join one with a code.
- Talk.
- See the verdict about the **other** person's voice, with every client rule from
  [BACKEND_API.md](BACKEND_API.md) applied.

Replace it with your real UI, but keep the logic in `onData` and the agent checks.

```tsx
// SatyaCheck call app: minimal starting point (webrtc/EXPO.md).
// Sign in with an emailed code, start or join a call, talk, and see the verdict about the
// OTHER person's voice. Every rule from webrtc/BACKEND_API.md is applied in onData below.
import 'react-native-url-polyfill/auto';
import { registerGlobals, AudioSession } from '@livekit/react-native';
import { Room, RoomEvent, type RemoteParticipant } from 'livekit-client';
import { createClient } from '@supabase/supabase-js';
import { useEffect, useRef, useState } from 'react';
import { Button, PermissionsAndroid, Platform, SafeAreaView, StyleSheet, Text, TextInput, View } from 'react-native';

registerGlobals();   // once, at module level, before any LiveKit use

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL!;            // e.g. http://192.168.1.20:8000
const supabase = createClient(process.env.EXPO_PUBLIC_SUPABASE_URL!, process.env.EXPO_PUBLIC_SUPABASE_ANON_KEY!,
  { auth: { persistSession: false } });                           // memory only, like the web app

type Verdict = {
  rev: number; display_band: string; trust_score: number | null; screening_available: boolean;
  reason: string | null; alerts: { alert_id: string; band: string; resolved: boolean; evidence: string | null }[];
  coverage: { unscreened_s: number; degraded: boolean } | null;
};
type Joined = { call_id: string; livekit_url: string; token: string; agent_identity: string; code?: string };

const BAND_COPY: Record<string, { label: string; color: string }> = {
  insufficient: { label: 'Listening…', color: '#6b7280' },
  unverified: { label: 'Not a saved voice', color: '#6b7280' },          // neutral, never green
  verified: { label: 'Matches a saved voice', color: '#15803d' },
  caution: { label: 'Take a moment to verify', color: '#b45309' },
  suspicious: { label: 'Be careful', color: '#c2410c' },
  high_risk: { label: 'Stop. Call them back on a number you trust.', color: '#b91c1c' },
};

async function api(path: string, method = 'POST'): Promise<any> {
  const { data } = await supabase.auth.getSession();
  const res = await fetch(`${BACKEND}${path}`, {
    method, headers: { Authorization: `Bearer ${data.session?.access_token ?? ''}` },
  });
  if (!res.ok) throw new Error((await res.json().catch(() => null))?.detail ?? `HTTP ${res.status}`);
  return res.status === 204 ? null : res.json();
}

export default function App() {
  const [signedIn, setSignedIn] = useState(false);
  const [email, setEmail] = useState('');
  const [otp, setOtp] = useState('');
  const [codeSent, setCodeSent] = useState(false);
  const [joinCode, setJoinCode] = useState('');
  const [call, setCall] = useState<Joined | null>(null);
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [screeningLost, setScreeningLost] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const room = useRef<Room | null>(null);

  async function signIn() {
    setError(null);
    const r = codeSent
      ? await supabase.auth.verifyOtp({ email, token: otp, type: 'email' })
      : await supabase.auth.signInWithOtp({ email });
    if (r.error) setError(r.error.message);
    else if (codeSent) setSignedIn(true);
    else setCodeSent(true);
  }

  async function connect(joined: Joined) {
    if (Platform.OS === 'android') {
      await PermissionsAndroid.request(PermissionsAndroid.PERMISSIONS.RECORD_AUDIO);
    }
    await AudioSession.startAudioSession();
    const r = new Room();
    r.on(RoomEvent.DataReceived, (payload: Uint8Array, participant?: RemoteParticipant, _kind?: unknown, topic?: string) => {
      // Rule 1: only the agent, only this topic. Rule 2: keep the highest rev.
      if (topic !== 'satyacheck.verdict' || participant?.identity !== joined.agent_identity) return;
      const msg: Verdict = JSON.parse(new TextDecoder().decode(payload));
      setVerdict(prev => (prev && prev.rev > msg.rev ? prev : msg));
    });
    r.on(RoomEvent.ParticipantConnected, (p: RemoteParticipant) => {
      if (p.identity === joined.agent_identity) setScreeningLost(false);
    });
    r.on(RoomEvent.ParticipantDisconnected, (p: RemoteParticipant) => {
      if (p.identity === joined.agent_identity) setScreeningLost(true);   // Rule 4
    });
    await r.connect(joined.livekit_url, joined.token);
    await r.localParticipant.setMicrophoneEnabled(true);
    room.current = r;
    setCall(joined);
  }

  async function startCall() {
    try { await connect(await api('/api/webrtc/calls')); } catch (e) { setError(String(e)); }
  }

  async function joinCall() {
    try { await connect(await api(`/api/webrtc/calls/${encodeURIComponent(joinCode.trim())}/join`)); }
    catch (e) { setError(String(e)); }
  }

  async function hangUp() {
    if (call) await api(`/api/webrtc/calls/${call.call_id}`, 'DELETE').catch(() => {});
    await room.current?.disconnect();
    await AudioSession.stopAudioSession();
    room.current = null;
    setCall(null);
    setVerdict(null);
    setScreeningLost(false);
  }

  useEffect(() => () => { room.current?.disconnect(); }, []);

  if (!signedIn) {
    return (
      <SafeAreaView style={styles.page}>
        <Text style={styles.title}>Sign in to SatyaCheck</Text>
        <TextInput style={styles.input} placeholder="Email" autoCapitalize="none" value={email} onChangeText={setEmail} />
        {codeSent && <TextInput style={styles.input} placeholder="6-digit code" keyboardType="number-pad" value={otp} onChangeText={setOtp} />}
        <Button title={codeSent ? 'Sign in' : 'Email me a code'} onPress={signIn} />
        {error && <Text style={styles.error}>{error}</Text>}
      </SafeAreaView>
    );
  }

  if (!call) {
    return (
      <SafeAreaView style={styles.page}>
        <Button title="Start a call" onPress={startCall} />
        <TextInput style={styles.input} placeholder="Call code" autoCapitalize="characters" value={joinCode} onChangeText={setJoinCode} />
        <Button title="Join a call" onPress={joinCall} />
        {error && <Text style={styles.error}>{error}</Text>}
      </SafeAreaView>
    );
  }

  const copy = BAND_COPY[verdict?.display_band ?? 'insufficient'] ?? BAND_COPY.insufficient;
  const openAlerts = verdict?.alerts.filter(a => !a.resolved) ?? [];          // Rule 6
  return (
    <SafeAreaView style={styles.page}>
      {call.code && <Text style={styles.title}>Share this code: {call.code}</Text>}
      <View style={[styles.banner, { backgroundColor: copy.color }]}>
        <Text style={styles.bannerText}>{copy.label}</Text>
        {verdict?.trust_score != null && <Text style={styles.bannerText}>{Math.round(verdict.trust_score)}/100</Text>}
      </View>
      {screeningLost && <Text style={styles.error}>Screening unavailable. Call them back on a number you trust.</Text>}
      {verdict && !verdict.screening_available && <Text style={styles.error}>Screening paused: {verdict.reason}</Text>}
      {verdict?.coverage && (verdict.coverage.unscreened_s > 0 || verdict.coverage.degraded) &&
        <Text>Part of this call couldn't be checked.</Text>}
      {openAlerts.map(a => <Text key={a.alert_id}>• {a.evidence ?? a.band}</Text>)}
      <Button title="Hang up" color="#b91c1c" onPress={hangUp} />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  page: { flex: 1, padding: 20, gap: 12, justifyContent: 'center' },
  title: { fontSize: 22, fontWeight: '600' },
  input: { borderWidth: 1, borderColor: '#d1d5db', borderRadius: 8, padding: 12, fontSize: 18 },
  error: { color: '#b91c1c' },
  banner: { padding: 20, borderRadius: 12 },
  bannerText: { color: 'white', fontSize: 22, fontWeight: '700' },
});
```

Notes:

- **Remote audio plays by itself** once you're subscribed (React Native WebRTC). Speaker
  versus earpiece routing is `AudioSession` configuration; see the `@livekit/react-native`
  README.
- **The caller polls** `GET /api/webrtc/calls/{call_id}` to show "waiting for the other
  person" until `other_joined` is true. The minimal app skips this.
- **Before the callee joins, nothing is screened.** That's by design: nobody is listening yet.

## 5. Build the development APK

Choose **one** of these.

### A. EAS (cloud build; no Android SDK needed on your laptop)

```bash
npm install -g eas-cli@24.12.1
eas login
eas build:configure            # creates eas.json
```

In `eas.json`, make the development profile produce an installable APK:

```json
{
  "build": {
    "development": {
      "developmentClient": true,
      "distribution": "internal",
      "android": { "buildType": "apk" }
    },
    "preview": {
      "distribution": "internal",
      "android": { "buildType": "apk" }
    }
  }
}
```

Then:

```bash
eas build -p android --profile development
```

EAS prints a link and a QR code to download the APK. Send it to the second tester the same way.

**`EXPO_PUBLIC_*` on EAS:** a local `.env` is not uploaded with the build. Set the three
variables as EAS environment variables (`eas env:create`) or in the profile's `env` block.

### B. Local (Android SDK and **JDK 17**)

```bash
npx expo prebuild --platform android
cd android && ./gradlew assembleDebug        # Windows: gradlew.bat assembleDebug
# -> android/app/build/outputs/apk/debug/app-debug.apk
```

Set `ANDROID_HOME` to your Android SDK and `JAVA_HOME` to a **JDK 17**. Both of these were
learned the hard way on the validation machine:

- **JDK 24 fails** at `configureCMakeDebug` with "A restricted method in java.lang.System has
  been called". JDK 17 is React Native's recommended JDK.
- **Windows: keep the project at a short path**, for example `C:\dev\satyacheck-call`. A deep
  folder fails at `buildCMakeDebug` with "The maximum full path to an object file is 250".
  Drive-letter or junction tricks don't help, because the build resolves them back to the
  long path.

If Gradle fails with `PKIX path validation failed`, something on your network intercepts TLS,
and Java doesn't trust it while your browser does. On Windows, make Java use the Windows
certificate store for that shell. Verification stays on: Java checks against the same roots
your browser trusts.

```bash
export JAVA_TOOL_OPTIONS="-Djavax.net.ssl.trustStoreType=Windows-ROOT"
```

This was needed on the validation machine. **Never turn certificate checks off.**

## 6. Run it

```bash
npx expo start --dev-client
```

1. Install the APK on both phones.
2. Open it. It finds Metro on the same Wi-Fi; or scan the QR code that `expo start` prints.
3. Edits to `App.tsx` reload live. Rebuild the APK only when you add or upgrade a *native*
   package.

To hand someone a self-contained APK with no Metro, build the `preview` profile
(`eas build -p android --profile preview`). The JavaScript is bundled inside it.

## 7. Then

Go through [ACCEPTANCE.md](ACCEPTANCE.md). Do the mobile-data call last, after the same-Wi-Fi
call works ([NETWORK.md](NETWORK.md)).
