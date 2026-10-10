# App-to-app calls over WebRTC

Android gives a third-party app **silence** during a normal phone call (see the root
`CLAUDE.md`), so SatyaCheck can't hear a regular call on the phone that's in it. For real-time
testing, the app *becomes* the phone: two people who both have the app call each other through
it, and the backend hears each voice live.

This is a **test path**. A real scammer won't install our app. It lets us exercise the live
pipeline on real phones, with real networks and real voices.

This folder holds docs and config only. The Expo app is yours to build. The backend side is
complete and tested.

## How it fits together

```
 phone A (Expo app) ──mic──►┐                      ┌──► phone B hears A
                            │   LiveKit server      │
 phone B (Expo app) ──mic──►┤  (same machine as     ├──► phone A hears B
                            │   the backend)        │
                            └──► screening agent ───┘   (hears both, over localhost)
                                   │
                                   ├─ A's voice → identity, synthetic-voice, intent checks → verdicts → B only
                                   └─ B's voice → the same checks                         → verdicts → A only
```

- **The call is a LiveKit room.** The two phones and one screening agent are its participants.
- **Each voice is screened for the other person.** The person *listening* gets the verdict
  about the voice they hear. Their own saved voices ("Papa", "Asha") are what the voice is
  compared against.
- **Verdicts travel as LiveKit data messages** on topic `satyacheck.verdict`. They come only
  from the agent (phones are not allowed to send data). See [BACKEND_API.md](BACKEND_API.md).
- **Latency:**
  - The backend runs on a GPU. A verdict update lands about **0.2 s** after the audio it
    covers (measured, one call).
  - The first scored verdict needs a few seconds of speech: about **6.6 s** in the smoke test.
  - LiveKit adds tens of milliseconds on a good network. See [NETWORK.md](NETWORK.md).

## Order of work

### 1. Two accounts

Sign-in is a Supabase email code, the same as the web and Flutter apps. Make two accounts
(two email addresses). A call needs two *different* accounts: you can't call yourself.

### 2. LiveKit

On the machine that runs the backend:

```bash
export LIVEKIT_API_KEY=satyacheck
export LIVEKIT_API_SECRET=$(python -c "import secrets; print(secrets.token_urlsafe(32))")   # 32+ chars
export LIVEKIT_NODE_IP=<this machine's LAN IP, e.g. 192.168.1.20>
docker compose -f webrtc/docker-compose.livekit.yml up -d
```

Keep the secret out of git. Put it in your shell or in the git-ignored `.env`.

### 3. The backend

Add these to `.env`. These are WebRTC's settings; the rest of `.env` is as in `.env.example`.

```
AUTH_MODE=jwt
SUPABASE_URL=https://<ref>.supabase.co
ENABLE_WEBRTC=true
LIVEKIT_URL=ws://<LAN IP>:7880          # what the PHONES connect to
LIVEKIT_AGENT_URL=ws://127.0.0.1:7880   # what the backend's agent connects to
LIVEKIT_API_KEY=satyacheck
LIVEKIT_API_SECRET=<same secret as above>
```

Then:

```bash
uvicorn server.main:app --host 0.0.0.0 --port 8000
```

The startup log must say:

```
WebRTC calls mounted at /api/webrtc
```

If it says **NOT mounted**, the line explains why: dev auth mode, or missing keys.
`GET /api/ready` shows where every model runs. You want `"device": "cuda"` and no `fallbacks`.

### 4. Smoke test, before touching a phone

```bash
python -m scripts.webrtc_smoke
```

This plays both phones in Python against your LiveKit server. It checks four things:

- verdicts reach the listener only;
- a phone can't forge a verdict;
- rejoining resyncs the state;
- packets fit LiveKit's size limit.

It must print `WEBRTC SMOKE OK`.

### 5. The Expo app

Follow [EXPO.md](EXPO.md): a development build (not Expo Go) with sign-in, create/join a call,
and the verdict banner.

### 6. Acceptance

The hand-off is done when every box in [ACCEPTANCE.md](ACCEPTANCE.md) is ticked, including a
call between two phones on **mobile data**.

## Files

| File | What |
|---|---|
| [BACKEND_API.md](BACKEND_API.md) | Endpoints, tokens, the verdict message, the rules a client must follow |
| [EXPO.md](EXPO.md) | Building the Expo app and the APK |
| [NETWORK.md](NETWORK.md) | Making the server reachable from phones, TURN, LiveKit Cloud |
| [ACCEPTANCE.md](ACCEPTANCE.md) | The checklist that says it works |
| `livekit.yaml`, `docker-compose.livekit.yml` | The LiveKit server |

**Backend code:**

- `server/webrtc_router.py` — the endpoints;
- `server/webrtc_calls.py` — calls and codes;
- `server/webrtc_screening.py` — tokens, the agent manager, what a listener is sent;
- `acquisition/webrtc/` — the agent and audio framing;
- `server/live_presenter.py` — alert and band rules shared with the web app's live stream.
