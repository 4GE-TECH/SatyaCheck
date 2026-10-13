# Backend API for app-to-app calls

All endpoints need a **signed-in** user: `Authorization: Bearer <Supabase access token>`.
The token comes from the email-code sign-in, the same as the other apps. Dev-mode shortcuts
don't work here. A call needs two real, different accounts that are connected.

Base URL: the backend, for example `http://192.168.1.20:8000`.

## The flow

1. Each person chooses a **username** (once).
2. A searches for B's username and taps **Connect**. B sees the request and **accepts** it.
   Until then neither can call the other: knowing someone's username is not enough to ring
   their phone.
3. Either one **calls** the other. The callee's app shows the incoming call while it is open,
   and they accept or decline. Unanswered calls are **missed** after 45 s
   (`WEBRTC_RING_TIMEOUT_S`).

## People endpoints

Mounted with the call endpoints (same conditions). Profiles carry a username and display name,
never an email address.

| Endpoint | What |
|---|---|
| `GET /api/profile` | Your profile, or `404` before you have chosen a username |
| `PUT /api/profile` `{"username", "display_name"}` | Choose or change it. `409` taken, `422` invalid or reserved (3–20 of `a-z 0-9 . _`; names that look official, like `satyacheck…` or `support…`, are refused) |
| `GET /api/users/search?q=` | Up to 20 usernames starting with `q` (2+ characters; a leading `@` is fine), each with your `relation`: `none`, `outgoing`, `incoming` or `connected`. Rate-limited: `429` |
| `GET /api/connections` | `{ "connected": [...], "incoming": [...], "outgoing": [...] }` |
| `POST /api/connections` `{"user_id"}` | Send a connect request (`201`). If they already asked you, this connects you. `409` until you have a username; `429` when rate-limited |
| `POST /api/connections/{user_id}/accept` | Accept their request. Only the person asked can accept |
| `DELETE /api/connections/{user_id}` | Decline, cancel, or disconnect (`204`) |

A person is `{ "user_id", "username", "display_name", "relation" }`.

## Call endpoints

### `POST /api/webrtc/calls` `{"callee_id"}` — ring a connection (the caller)

`201` response:

```json
{
  "call_id": "e7919c122f171720",
  "livekit_url": "ws://192.168.1.20:7880",
  "token": "<LiveKit token for this phone>",
  "agent_identity": "satyacheck-agent-e7919c122f171720",
  "other": {"user_id": "…", "username": "bob", "display_name": "Bob"},
  "ring_timeout_s": 45
}
```

- Connect to `livekit_url` with `token` straight away and wait in the room: the callee joins
  when they answer.
- `403` they are not a connection; `409` you or they are already in a call; `503` the server is
  at capacity (two calls by default).

### `GET /api/webrtc/incoming` — calls ringing for you (the callee)

`{ "calls": [ { "call_id", "caller": {person}, "rings_for_s" } ] }`

Poll it every couple of seconds while the app is open. There is no push yet, so a closed app
does not ring.

### `POST /api/webrtc/calls/{call_id}/accept` — answer (the callee)

`200` response: `{ "call_id", "livekit_url", "token", "agent_identity", "other" }`. Your token
is minted only now. `404` if it is no longer ringing (cancelled, missed, or not yours).

### `POST /api/webrtc/calls/{call_id}/decline` — decline (the callee)

Returns `204`.

### `GET /api/webrtc/calls/{call_id}` — state, for either party

`{ "call_id", "role": "caller" | "callee", "status": "ringing" | "active" | "ended",
"ended_reason": "declined" | "missed" | "cancelled" | "hung_up" | "dropped" | "timed_out" | null,
"other_joined", "ended", "screening" }`

Poll it during the call: it is how each side learns the other declined, missed or hung up.
Anyone not in the call gets `404`.

Two endings come from the service, not from a person, so never word them as someone
hanging up:

| Reason | Meaning |
|---|---|
| `dropped` | One phone left the room and didn't come back within 60 s (`WEBRTC_ABANDON_AFTER_S`). |
| `timed_out` | The call reached its limit of 2 hours (`WEBRTC_MAX_CALL_S`). |

### `POST /api/webrtc/calls/{call_id}/rejoin` — re-enter a live call, for either party

Returns a fresh ticket (`{ "call_id", "livekit_url", "token", "agent_identity", "other" }`). It
is for re-entering the same call after the connection dropped for good. Room tokens are
short-lived, so on a long call the original one may no longer let a phone back in.

Who may rejoin:

- the caller, while the call rings;
- either party, once it is answered;
- nobody else. The callee of a ringing call must answer instead; anyone else, and anyone
  after the call has ended, gets `404`.

Rejoin within 60 s. After that the service ends the call as `dropped`. The Flutter app does
this automatically: it keeps the last verdict on screen while rejoining, and the agent
resends the full state when the phone arrives.

### `DELETE /api/webrtc/calls/{call_id}` — cancel or hang up, for either party

Returns `204`. Then disconnect from the room.

## What the tokens allow

| | Phone | Screening agent |
|---|---|---|
| Identity | the user's account id | `satyacheck-agent-<call_id>` (= `agent_identity`) |
| Publish | **microphone audio only** | nothing (no media) |
| Publish data | **no** | yes (the verdicts) |
| Subscribe | yes | yes |

Tokens last 10 minutes and allow one room. They are for joining: an established call keeps
running after the token expires, and LiveKit's own quick reconnects keep working. A phone
whose connection dropped for good asks `/rejoin` for a fresh token.

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

- **The agent listens only once the callee answers.** A caller talking while it rings is heard
  by nobody, so that audio isn't screened.
- **Each voice is a backend session:**
  - `rtc_<call_id>_caller` and `rtc_<call_id>_callee`;
  - owned by the account that *listens* to it;
  - shown in that account's reports.
- **Capacity:** each call uses two of the server's live-session slots (four on the GPU
  machine), so two calls at once by default.
