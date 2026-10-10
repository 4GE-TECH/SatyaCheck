# Live feed and remote backend — frontend guide

For whoever builds the dashboard (`web/`) and the mobile app (`satyacheck_mobile/`) against a
SatyaCheck backend running on **another machine**, reached through a Cloudflare tunnel.

You need two things from the person running the backend:

| | Example | Used for |
|---|---|---|
| **Backend URL** | `https://quiet-river-1234.trycloudflare.com` | every REST call and WebSocket |
| **Live-feed token** | `k3v9…` | the `?token=` on `/api/ws/live` (only if they set one) |

The Exotel phone call itself goes from Exotel straight to the backend. You never handle call
audio; you watch verdicts arrive on the live feed.

---

## 1. Point the frontends at the backend

**Dashboard (`web/`, Vite).** The dev server proxies `/api` to `localhost:8000`
(`web/vite.config.ts`). Point it at the tunnel instead — `ws: true` is needed for the
WebSockets, `changeOrigin: true` for Cloudflare:

```ts
server: {
  proxy: {
    '/api': {
      target: process.env.SATYACHECK_BACKEND ?? 'http://localhost:8000',
      changeOrigin: true,
      ws: true,
    },
  },
},
```

```bash
SATYACHECK_BACKEND=https://quiet-river-1234.trycloudflare.com npm run dev
```

With the proxy, the browser only ever talks to `localhost:5173`, so CORS does not apply. If you
instead call the tunnel URL directly from the browser, the backend must allow your origin: the
backend owner starts it with `SATYACHECK_CORS_ORIGINS=http://localhost:5173` (comma-separated
for several).

**Mobile app (`satyacheck_mobile/`).** The backend URL is a build-time define (see
`lib/api_client.dart`); `https://` becomes `wss://` for its WebSocket automatically:

```bash
flutter run --dart-define=SATYACHECK_BACKEND=https://quiet-river-1234.trycloudflare.com
```

No `adb reverse` is needed when going through the tunnel.

Check the link first: `GET <backend>/api/health` returns `{"status": "ok", ...}`.

---

## 2. The live feed: `/api/ws/live`

```
wss://<backend host>/api/ws/live?token=<token>
```

(Through the Vite proxy: `ws://localhost:5173/api/ws/live?token=<token>`.)

- **Sign in with your first message** (since the upgrade plan's Phase 1):
  `{"type": "auth", "token": "<Supabase access token>"}`. You then receive only **your
  account's** calls. Never put the access token in the URL.
  - Backend in `AUTH_MODE=dev`: a client that stays silent for half a second is the dev
    account, so today's dashboard keeps working unchanged.
  - Backend in `AUTH_MODE=jwt` (always in production): no valid auth message within
    `WS_AUTH_TIMEOUT_S` (10 s), and the server closes with **1008**.
- **Receive-only** after that. Anything else you send is ignored. Keep the socket open.
- **Wrong or missing `?token=`** (only when the backend set `LIVE_FEED_TOKEN`, an older
  extra gate): the server closes with code **1008**.
- **Live only.** Connect before the call starts; there is no replay of earlier verdicts. If the
  socket drops, reconnect — verdicts sent in between are not resent.
- One feed carries **every call of your account**. Group messages by `session_id`; a new `session_id` is a new
  call.

### Messages

On connect, once:

```json
{"type": "hello", "schema_version": 1, "server_time": "2026-10-06T12:55:58.123456+00:00"}
```

Then one `verdict` per scoring window — about every **2 seconds of call audio** — plus exactly
one final verdict per call (`is_final: true`) when the call ends. Ignore any `type` you don't
recognise; check `schema_version` (currently `1`).

```json
{
  "type": "verdict",
  "schema_version": 1,
  "session_id": "MZ8f2c41e0a7",
  "window_index": 4,
  "is_final": false,
  "escalated": true,
  "timestamp": "2026-10-06T12:55:58.439517+00:00",
  "band": "high_risk",
  "overlay_state": "red",
  "trust_score": 12.0,
  "risk_score": 0.88,
  "mode": "identity_check",
  "signals": {"identity": "match", "authenticity": "synthetic", "intent_risk": 0.94},
  "reason_codes": [
    {
      "code": "RC_SYNTHETIC_VOICE_DETECTED",
      "signal": "authenticity",
      "value": "Peak Synth 98% (Run 6.5s)",
      "threshold": "> 40%",
      "explanation": "Deepfake speech synthesis signatures detected. Spectral artifacts match neural vocoder cloning.",
      "severity": "critical"
    }
  ],
  "transcript": "Papa emergency ho gaya hai, police ne pakad liya hai! Phone kisi ko mat dena, turant 50000 bhejo is UPI ID pe!",
  "language": "hi",
  "caller_context": {"claimed_number": "+919876543210", "claimed_name": null, "claimed_identity": null, "channel_type": "telephony"},
  "threat_label": null,
  "recommended_actions": ["DO NOT transfer money via UPI.", "Disconnect the call immediately."],
  "vernacular_warning": "सावधान! यह कॉल एक क्लोन की हुई नकली आवाज़ हो सकती है। कोई भी पैसा ट्रांसफर न करें।",
  "window_trust_score": 64.7,
  "window_band": "caution"
}
```

### Fields

| Field | Type | Meaning |
|---|---|---|
| `session_id` | string | One call. Plain name `[A-Za-z0-9_-]`. |
| `window_index` | int | 0, 1, 2… per call. The final verdict may repeat the last index. |
| `is_final` | bool | `true` exactly once per call, on its last verdict. |
| `escalated` | bool | `true` when this verdict raised the call's warning level (good moment for an alert sound). |
| `band` | string | `verified` · `caution` · `suspicious` · `high_risk` · `unverified` · `insufficient` |
| `overlay_state` | string | The colour to show: `green` · `amber` · `red` · `grey`. Use this rather than mapping `band` yourself. |
| `trust_score` | number | 0–100, higher = more trusted. The **session** score: never goes up during a call (a scam cannot climb back). |
| `window_trust_score` | number | 0–100, **this window's own** score before the session floor. It moves up and down — use it for a live gauge. |
| `window_band` | string | This window's own band, before the session latch. Same values as `band`. |
| `risk_score` | number | 0–1, the fused risk. |
| `mode` | string | `identity_check` (a known contact) or `authority_check` (a stranger). |
| `signals.identity` | string | `match` · `mismatch` · `unknown` (unknown is normal for a stranger, not suspicious). |
| `signals.authenticity` | string | `synthetic` · `bonafide` · `unavailable` (the voice check did not run — say "not measured", never "genuine"). |
| `signals.intent_risk` | number | 0–1, from what was said. |
| `reason_codes[]` | list | The evidence, in display order. `severity`: `info` · `low` · `medium` · `high` · `critical`. |
| `transcript` | string | What has been understood so far. **Empty for roughly the first 9–14 seconds** — speech recognition waits for enough audio, and verdicts never wait for it. |
| `language` | string | `en`, `hi`, … or `unknown`. |
| `caller_context` | object or null | The caller's number from Exotel (`channel_type: "telephony"`). Display only — it never affects the score. |
| `threat_label` | object or null | `{sector, threat, family}`, e.g. banking / KYC update fraud. Present only on warning bands. |
| `recommended_actions` | list of strings | What to tell the person on the call. |
| `vernacular_warning` | string or null | A spoken-style warning in Hindi for warning bands. |

### Rendering rules the backend relies on

- **Never show green for `authority_check`.** The backend already reports `unverified` (grey)
  there; don't override it.
- **Don't present a verdict as an accusation.** Show it as a level with evidence ("signs of a
  cloned voice"), never "this is a scammer".
- **`insufficient` is not a result.** It means the audio so far was too short or too noisy to
  score — show "listening…", not a colour judgement. Early windows of every call are often
  `insufficient`.
- The **final** verdict (`is_final: true`) is the one to keep for the call's summary.

---

## 3. Other endpoints you may want

| Endpoint | Use |
|---|---|
| `GET /api/health` | Liveness and which branches are on (`use_real_spoof`, etc.). |
| `GET /api/screen/{session_id}` | The stored final verdict of a call (full `ScreeningResponse`). |
| `GET /api/report/{session_id}` and `/pdf` | The incident report (JSON / PDF) for a finished call. |
| `wss://…/api/ws/guardian` | Existing guardian alerts — only when a call escalates to suspicious or high risk. |
| `POST /api/screen` | Upload a clip (the app's demo callers), unchanged. |

---

## 4. Troubleshooting

| Symptom | Likely cause |
|---|---|
| `/api/health` fails | Wrong URL, or the backend owner's tunnel restarted (quick tunnels get a **new URL** each start). |
| Live socket closes immediately with 1008 | Missing or wrong `?token=`. |
| Socket connects but nothing arrives | No call in progress — verdicts only flow during an Exotel call. Ask the backend owner to check their log for `exotel: stream started`. |
| Browser CORS error | You're calling the tunnel directly: use the Vite proxy, or have the backend add your origin to `SATYACHECK_CORS_ORIGINS`. |
