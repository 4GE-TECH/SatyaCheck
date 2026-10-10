"""End-to-end check of app-to-app calls without phones (webrtc/README.md, step 4).

Starts the real backend in this process (uvicorn on a free port, real models, a throwaway
SQLite file), then plays both phones with the LiveKit Python SDK against a running LiveKit
server. For each clip:

  1. "alice" creates a call over HTTP and joins the room; "bob" joins with the code;
  2. alice publishes the clip as her microphone, in real time;
  3. bob must receive verdict packets on `satyacheck.verdict` from the agent identity only;
  4. alice tries to publish a fake verdict: LiveKit must refuse it (no data grant);
  5. bob leaves and rejoins mid-call: he must get the full current state again;
  6. checks: the clone clip never shows the verified band; the genuine clip never shows high
     risk; every packet fits LiveKit's reliable-data limit.

Accounts: two signed-in users are simulated with a local signing key standing in for
Supabase (the same stand-in the test suite uses). Phones use real Supabase sign-in.

Needs: LiveKit running (webrtc/docker-compose.livekit.yml) and LIVEKIT_API_KEY /
LIVEKIT_API_SECRET in the environment, the same values LiveKit was started with.

    python -m scripts.webrtc_smoke                      # exits 1 on any failed check
"""

from __future__ import annotations

import asyncio
import json
import os
import socket
import sys
import tempfile
import threading
import time
import wave
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CLIPS = ROOT / "data" / "eval_set" / "clips"
CASES = [("cloned_scam", "clone"), ("friend_test", "genuine")]


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _configure(db: Path) -> None:
    os.environ.update({"DATABASE_URL": f"sqlite:///{db}", "AUTH_MODE": "jwt", "ENABLE_WEBRTC": "true",
                       "SATYACHECK_ENV": "dev",
                       # the test suite's stand-in issuer (server/tests/auth_helpers.py)
                       "AUTH_ISSUER": "https://test-ref.supabase.co/auth/v1",
                       "AUTH_JWKS_URL": "https://test-ref.supabase.co/auth/v1/.well-known/jwks.json",
                       "AUTH_AUDIENCE": "authenticated",
                       "LIVEKIT_URL": os.getenv("LIVEKIT_URL", "ws://127.0.0.1:7880"),
                       "WEBRTC_HEARTBEAT_S": "2", "LOG_LEVEL": "WARNING"})
    if not (os.getenv("LIVEKIT_API_KEY") and os.getenv("LIVEKIT_API_SECRET")):
        sys.exit("set LIVEKIT_API_KEY and LIVEKIT_API_SECRET (the values LiveKit was started with)")


def _start_backend(port: int):
    import uvicorn

    from server import auth
    from server.tests.auth_helpers import _KEY, make_token

    auth._signing_key = lambda token: _KEY.public_key()     # stand-in for Supabase's JWKS
    from server.capacity import warm_models
    from server.main import app

    warm_models()
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    threading.Thread(target=server.run, daemon=True).start()
    deadline = time.time() + 30
    while not server.started and time.time() < deadline:
        time.sleep(0.1)
    if not server.started:
        sys.exit("backend did not start")
    return server, make_token


def _http(port, method, path, owner, make_token):
    import urllib.request

    req = urllib.request.Request(f"http://127.0.0.1:{port}{path}", method=method,
                                 headers={"Authorization": f"Bearer {make_token(owner)}"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read() or b"{}")


def _pcm(clip: str) -> bytes:
    with wave.open(str(CLIPS / f"{clip}.wav"), "rb") as w:
        assert w.getframerate() == 16000 and w.getnchannels() == 1, "clips are 16 kHz mono"
        return w.readframes(w.getnframes())


async def _call(port, make_token, clip: str, kind: str) -> list[str]:
    from livekit import rtc

    failures: list[str] = []
    created = _http(port, "POST", "/api/webrtc/calls", "alice", make_token)
    joined = _http(port, "POST", f"/api/webrtc/calls/{created['code']}/join", "bob", make_token)
    agent = created["agent_identity"]
    url = created["livekit_url"]
    packets, foreign = [], []
    t0 = [0.0]

    def listen(room):
        def on_data(packet):
            sender = packet.participant.identity if packet.participant else None
            if packet.topic != "satyacheck.verdict":
                return
            if sender != agent:
                foreign.append(sender)
                return
            packets.append((time.monotonic() - t0[0], len(packet.data), json.loads(packet.data)))
        room.on("data_received", on_data)

    alice, bob = rtc.Room(), rtc.Room()
    listen(bob)
    await bob.connect(url, joined["token"])
    await alice.connect(url, created["token"])
    source = rtc.AudioSource(16000, 1)
    track = rtc.LocalAudioTrack.create_audio_track("microphone", source)
    opts = rtc.TrackPublishOptions()
    opts.source = rtc.TrackSource.SOURCE_MICROPHONE
    await alice.local_participant.publish_track(track, opts)

    # A forged verdict from the caller. Phones have no data grant, so LiveKit must drop it:
    # bob must never receive a verdict-topic packet from alice. (publish_data itself does
    # not necessarily raise; the server drops the packet.)
    try:
        await alice.local_participant.publish_data(json.dumps({"type": "satyacheck.verdict",
                                                               "display_band": "verified"}).encode(),
                                                   topic="satyacheck.verdict")
    except Exception:  # noqa: BLE001 — refusing locally is fine too
        pass

    pcm = _pcm(clip) * 3                                     # ~a call's worth of speech
    step = 160 * 2                                           # 10 ms
    t0[0] = time.monotonic()
    rejoined_at = None
    for i in range(0, len(pcm) - step, step):
        frame = rtc.AudioFrame(pcm[i:i + step], 16000, 1, 160)
        await source.capture_frame(frame)
        elapsed = time.monotonic() - t0[0]
        if rejoined_at is None and elapsed > len(pcm) / 32000 / 2:      # halfway: bob drops and rejoins
            before = len(packets)
            await bob.disconnect()
            bob = rtc.Room()
            listen(bob)
            await bob.connect(url, joined["token"])
            rejoined_at = (time.monotonic() - t0[0], before)
        await asyncio.sleep(max(0.0, t0[0] + (i + step) / 32000 - time.monotonic()))
    await asyncio.sleep(6)                                   # let the last windows land
    _http(port, "DELETE", f"/api/webrtc/calls/{created['call_id']}", "alice", make_token)
    await alice.disconnect()
    await bob.disconnect()

    bands = [p["display_band"] for _, _, p in packets]
    first = next((t for t, _, p in packets if p["display_band"] != "insufficient"), None)
    print(f"  {clip} ({kind}): {len(packets)} packets, bands {sorted(set(bands))}, "
          f"first scored verdict after {first if first is None else round(first, 2)} s of audio, "
          f"largest packet {max((n for _, n, _ in packets), default=0)} bytes")
    if not packets:
        failures.append(f"{clip}: no verdict reached the listener")
    if foreign:
        failures.append(f"{clip}: verdict-topic packets from non-agent senders {sorted(set(map(str, foreign)))} "
                        f"(a forged verdict got through, or the agent's identity is not visible)")
    if any(n > 15 * 1024 for _, n, _ in packets):
        failures.append(f"{clip}: a packet exceeded 15 KiB")
    if kind == "clone" and "verified" in bands:
        failures.append(f"{clip}: a cloned voice was shown as verified")
    if kind == "genuine" and "high_risk" in bands:
        failures.append(f"{clip}: a genuine voice was shown as high risk")
    if rejoined_at is not None:
        t_rejoin, _ = rejoined_at
        after = [p for t, _, p in packets if t >= t_rejoin]
        if not after:
            failures.append(f"{clip}: no state reached the listener after rejoining")
        else:
            revs = [p["rev"] for _, _, p in packets if p.get("rev") is not None]
            print(f"    rejoined at {t_rejoin:.1f} s; first packet after it has rev {after[0]['rev']} "
                  f"(max before {max(revs[:len(revs) - len(after)] or [0])})")
    return failures


def main() -> int:
    tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)   # Windows: SQLite may still hold the file
    _configure(Path(tmp.name) / "smoke.db")
    sys.path.insert(0, str(ROOT))
    port = _free_port()
    server, make_token = _start_backend(port)
    failures: list[str] = []
    try:
        for clip, kind in CASES:
            failures += asyncio.run(_call(port, make_token, clip, kind))
    finally:
        server.should_exit = True
        time.sleep(1)
    if failures:
        print("WEBRTC SMOKE FAILED:")
        for f in failures:
            print("  " + f)
        return 1
    print("WEBRTC SMOKE OK: verdicts reached the listener only, forged verdicts were refused, "
          "rejoining resynced, packets fit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
