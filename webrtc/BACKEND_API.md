# Backend API for app-to-app calls

All endpoints need a **signed-in** user: `Authorization: Bearer <Supabase access token>`.
The token comes from the email-code sign-in, the same as the other apps. Dev-mode shortcuts
don't work here. A call needs two real, different accounts.

Base URL: the backend, for example `http://192.168.1.20:8000`.

## Endpoints

### `POST /api/webrtc/calls` — start a call (the caller)

`201` response:

```json
{
  "call_id": "e7919c122f171720",
  "code": "RS8FD7WT",
  "livekit_url": "ws://192.168.1.20:7880",
  "token": "<LiveKit token for this phone>",
  "agent_identity": "satyacheck-agent-e7919c122f171720",
  "code_expires_in_s": 900
}
```

- Show `code` to the caller to share (read aloud, or send on WhatsApp). It works **once**.
- Connect to `livekit_url` with `token`.
- `503` means the server is at capacity, two calls by default. Try again later.

### `POST /api/webrtc/calls/{code}/join` — join with a code (the callee)

`200` response: `{ "call_id", "livekit_url", "token", "agent_identity" }`

| Status | Meaning |
|---|---|
| `404` | Unknown, expired or already-used code |
| `400` | You tried to join your own call |
| `429` | Too many attempts. Wait a minute. |

Codes are case-insensitive.

### `GET /api/webrtc/calls/{call_id}` — state, for either party

`{ "call_id", "role": "caller" | "callee", "other_joined", "ended", "screening" }`

Poll this on the caller's side to show "waiting for the other person". Anyone not in the call
gets `404`.

### `DELETE /api/webrtc/calls/{call_id}` — end the call, for either party

Returns `204`. Then disconnect from the room.

## What the tokens allow

| | Phone | Screening agent |
|---|---|---|
| Identity | the user's account id | `satyacheck-agent-<call_id>` (= `agent_identity`) |
| Publish | **microphone audio only** | nothing (no media) |
| Publish data | **no** | yes (the verdicts) |
| Subscribe | yes | yes |

Tokens last 10 minutes and allow one room. They are for joining: an established call keeps
running after the token expires.

## The verdict message

The agent sends it to the listener only. It's a LiveKit **data message**, reliable, topic
`satyacheck.verdict`, payload UTF-8 JSON, always under 12 KiB.

```json
{
  "type": "satyacheck.verdict",
  "schema_version": 1,
  "rev": 7,
  "session_id": "rtc_e7919c122f171720_caller",
  "screening_available": true,
  "reason": null,
  "display_band": "suspicious",
  "trust_score": 41.0,
  "mode": "authority_check",
  "reasons": [
    {"code": "RC_RISK_MARKERS_PRESENT", "explanation": "Asks for money to be sent immediately..."}
  ],
  "alerts": [
    {"alert_id": "a1", "band": "high_risk", "at_s": 22.5, "resolved": false,
     "evidence": "Asks you not to tell anyone and to stay on the line."}
  ],
  "coverage": {"screened_s": 48.0, "unscreened_s": 0.0, "degraded": false},
  "transcript_tail": "...main abhi police station mein hoon, Papa ko mat batana...",
  "transcript_rev": 5,
  "is_final": false
}
```

### `display_band`

| Value | Meaning | Show it as |
|---|---|---|
| `insufficient` | Not enough speech yet. No score. | "Listening…" (grey). **Do not show a number.** |
| `unverified` | A stranger: nobody saved matches. **Neutral, not bad.** | Grey. Never green. |
| `verified` | Matches a voice the listener saved | Green |
| `caution` / `suspicious` / `high_risk` | Increasing concern | Amber / orange / red |

- `trust_score` is `null` when the band is `insufficient`.
- `mode`:
  - `identity_check`: the voice is compared with someone saved;
  - `authority_check`: a stranger, judged on the voice and what is said.

## Rules a client must follow

These aren't style preferences. Each one prevents a real failure.

1. **Verify the sender.** Act on a data message only if:

   ```
   topic === "satyacheck.verdict" && participant?.identity === agent_identity
   ```

   Phones can't publish data. This check is the second lock in case a server is ever
   misconfigured.
2. **Keep the highest `rev`.** Ignore a message with a lower `rev` than one you already
   showed. Reliable messages can arrive after a newer heartbeat.
3. **The agent resends the full state** every few seconds and whenever you (re)join. After a
   reconnect, just wait for the next message. Don't reset the banner to green or empty.
4. **Screening unavailable:**
   - If `screening_available` is `false`, show "Screening paused" with `reason`, and keep
     the last band visible.
   - If the agent participant (`agent_identity`) **leaves the room**, show "Screening
     unavailable". You're on your own, so call back on a number you trust.
5. **Don't show the agent as a person** in the call UI. Filter it out by `agent_identity`.
6. **Alerts never silently disappear.** Show every alert with `resolved: false`. An alert is
   withdrawn only with `resolved: true`, when the claim it rested on changed.
7. **Unscreened time is real.** If `coverage.unscreened_s > 0` or `coverage.degraded`, say
   "Part of this call couldn't be checked."
8. **Wording:**
   - Never say "scammer" or "fraud". Say what was found, and what to do: "Call them back on a
     number you already have."
   - A matching phone number is a hint, never proof.
   - `unverified` is not an accusation.

## Receiving messages (React Native, `livekit-client`)

```ts
import { RoomEvent } from 'livekit-client';

room.on(RoomEvent.DataReceived, (payload, participant, kind, topic) => {
  if (topic !== 'satyacheck.verdict' || participant?.identity !== agentIdentity) return;
  const msg = JSON.parse(new TextDecoder().decode(payload));
  setVerdict(prev => (prev && prev.rev > msg.rev ? prev : msg));
});

room.on(RoomEvent.ParticipantDisconnected, p => {
  if (p.identity === agentIdentity) setScreeningLost(true);
});
```

## Under the hood (for reference)

- **The agent listens only once both people are in.** A caller talking before the callee joins
  is heard by nobody, so that audio isn't screened.
- **Each voice is a backend session:**
  - `rtc_<call_id>_caller` and `rtc_<call_id>_callee`;
  - owned by the account that *listens* to it;
  - shown in that account's reports.
- **Capacity:** each call uses two of the server's live-session slots (four on the GPU
  machine), so two calls at once by default.
