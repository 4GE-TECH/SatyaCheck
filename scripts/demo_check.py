"""Pre-flight and demo driver for SatyaCheck.

Two jobs, both meant to be run minutes before a demo:

    python scripts/demo_check.py            # is everything ready?
    python scripts/demo_check.py --run      # stream real clips, show the verdicts

The check exists because the failure modes are quiet. A backend that booted without its
models still answers /api/health with 200; an unenrolled voiceprint store still returns a
valid `unknown` for every caller. Both look fine until the demo, so this asserts on the
things that actually matter and says plainly which are missing.

The run mode streams recorded clips through the same WebSocket the phone uses — same
framing, same 9-second windows — so it exercises the real path rather than a shortcut. It
is also the fallback if the handset misbehaves: the verdicts are genuine, just driven from
a file instead of a microphone.
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import sys
import wave
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CLIPS = REPO / "data" / "eval_set" / "clips"
BASE = "http://localhost:8000"

#: Clip -> what it should demonstrate. These are held-out recordings: never used to author
#: a corpus document, so the retrieval is a real measurement rather than a memory test.
DEMO_CLIPS = [
    ("held-sms-fraud-001", "parcel redelivery fee scam", "red"),
    ("held-telecom-002", "TRAI regulatory-notice scam", "red"),
    ("held-digital-arrest-004", "digital arrest, crime branch", "red"),
    ("held-family-emergency-001", "cloned family emergency (Hinglish)", "red"),
    ("friend_test", "genuine benign call", "green/grey"),
]

def _supports_colour() -> bool:
    """ANSI works in most terminals but not when piped, and not in older consoles."""
    if not sys.stdout.isatty():
        return False
    if sys.platform == "win32":
        # Windows 10+ understands ANSI only once virtual terminal processing is enabled.
        try:
            import ctypes

            kernel32 = ctypes.windll.kernel32
            return bool(kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7))
        except Exception:
            return False
    return True


if _supports_colour():
    GREEN, RED, YELLOW, GREY, RESET = (
        "\033[92m", "\033[91m", "\033[93m", "\033[90m", "\033[0m")
else:
    GREEN = RED = YELLOW = GREY = RESET = ""


def _colour(band: str) -> str:
    if band in ("high_risk", "suspicious"):
        return RED
    if band == "caution":
        return YELLOW
    if band == "verified":
        return GREEN
    return GREY


# --- pre-flight ---------------------------------------------------------------

def preflight() -> bool:
    import urllib.request

    ok = True

    def check(label: str, passed: bool, detail: str = "") -> None:
        """`detail` explains the *failure*, so it is only printed when one happened."""
        nonlocal ok
        mark = f"{GREEN}OK  {RESET}" if passed else f"{RED}FAIL{RESET}"
        print(f"  [{mark}] {label}" + (f"  — {detail}" if detail and not passed else ""))
        if not passed:
            ok = False

    print("\nBackend")
    try:
        with urllib.request.urlopen(f"{BASE}/api/health", timeout=5) as r:
            health = json.loads(r.read())
        check("reachable on :8000", True)
        # The intent branch is the one carrying the demo. Speaker is nice to have; spoof
        # has no checkpoint and is deliberately off.
        check("intent branch live", health.get("use_real_nlp") is True,
              "USE_REAL_NLP is false — verdicts will be fixture text")
        check("speaker branch live", health.get("use_real_speaker") is True,
              "USE_REAL_SPEAKER is false — every caller reads as unknown")
        if health.get("use_real_spoof") is False:
            print(f"  [{GREY}note{RESET}] anti-spoof is off by design — no checkpoint exists. "
                  "The panel says so via RC_SPOOF_UNAVAILABLE.")
    except Exception as exc:
        check("reachable on :8000", False, f"{type(exc).__name__} — start uvicorn first")
        return False

    print("\nModels")
    for name, path in [
        ("whisper (ASR)", REPO / "models" / "faster-whisper-small"),
        ("BGE-m3 (retrieval)", REPO / "models" / "bge-m3"),
        ("ECAPA (speaker)", REPO / "models" / "ecapa"),
    ]:
        check(name, path.is_dir(), f"missing at {path}")

    print("\nDemo clips")
    for clip, _, _ in DEMO_CLIPS:
        check(clip, (CLIPS / f"{clip}.wav").is_file())

    print("\nEnrolled voices")
    prints = sorted((REPO / "data" / "enrollments").glob("*.npz"))
    if prints:
        check(f"{len(prints)} enrolled", True, ", ".join(p.stem for p in prints[:4]))
    else:
        # Not a failure. Grey for everyone is correct behaviour — but the green path
        # cannot be shown, and that is worth knowing before standing up.
        print(f"  [{YELLOW}warn{RESET}] nobody enrolled — every caller will be grey. "
              "The green path needs an enrolment; see satyacheck_mobile/RUN.md.")

    print("\nPhone")
    import shutil
    import subprocess
    adb = shutil.which("adb") or str(
        Path.home() / "AppData/Local/Android/Sdk/platform-tools/adb.exe")
    try:
        out = subprocess.run([adb, "devices"], capture_output=True, text=True, timeout=15).stdout
        devices = [l for l in out.splitlines()[1:] if l.strip() and "device" in l]
        if devices:
            check("connected", True, devices[0].split()[0])
            fwd = subprocess.run([adb, "reverse", "--list"], capture_output=True,
                                 text=True, timeout=15).stdout
            check("USB tunnel (adb reverse tcp:8000)", "8000" in fwd,
                  "run: adb reverse tcp:8000 tcp:8000")
        else:
            print(f"  [{YELLOW}warn{RESET}] no device — plug in the phone, "
                  "or demo from the laptop with --run")
    except Exception:
        print(f"  [{YELLOW}warn{RESET}] adb not usable")

    return ok


# --- streaming demo -----------------------------------------------------------

def _window(path: Path, start_s: float, dur_s: float) -> bytes | None:
    """One WAV window, exactly as the phone's RingBuffer would emit it."""
    with wave.open(str(path), "rb") as w:
        sr = w.getframerate()
        total = w.getnframes() / sr
        if start_s >= total:
            return None
        w.setpos(int(start_s * sr))
        frames = w.readframes(int(min(dur_s, total - start_s) * sr))
    out = io.BytesIO()
    with wave.open(out, "wb") as o:
        o.setnchannels(1)
        o.setsampwidth(2)
        o.setframerate(sr)
        o.writeframes(frames)
    return out.getvalue()


async def _stream(clip: str, label: str, expected: str) -> None:
    import websockets

    path = CLIPS / f"{clip}.wav"
    if not path.is_file():
        print(f"  {RED}missing{RESET} {path}")
        return

    # A fresh session id every run. Reusing one collides with the row the backend already
    # wrote for it and the socket closes immediately — which made every clip after the
    # first run of the demo fail with ConnectionClosedOK.
    import uuid

    session = f"demo-{clip}-{uuid.uuid4().hex[:8]}"
    print(f"\n{'=' * 74}\n{label}\n  {clip}.wav   (expect {expected})\n{'=' * 74}")

    try:
        async with websockets.connect(f"ws://localhost:8000/api/ws/screen/{session}") as ws:
            # 9-second windows with 3s overlap — the same cadence CallAudioService uses,
            # and for the same reason: Whisper invents sentences on shorter slices.
            start, index = 0.0, 0
            while (payload := _window(path, start, 9.0)) is not None:
                await ws.send(json.dumps({
                    "type": "audio_chunk", "session_id": session, "chunk_index": index,
                    "audio_base64": base64.b64encode(payload).decode(), "is_final": False,
                }))
                raw = await asyncio.wait_for(ws.recv(), timeout=180)
                msg = json.loads(raw)
                if msg.get("type") == "screening_update":
                    _show(msg["response"])
                start += 6.0
                index += 1
                if index >= 3:
                    break
    except Exception as exc:
        print(f"  {RED}stream failed{RESET}: {type(exc).__name__}: {exc}")


def _show(response: dict) -> None:
    fusion = response.get("fusion", {})
    band = fusion.get("band", "?")
    colour = _colour(band)
    print(f"\n  {colour}{band.upper():<11}{RESET} trust {fusion.get('trust_score')}"
          f"   mode {fusion.get('mode')}")

    text = (response.get("transcript") or {}).get("text", "")
    if text:
        print(f'  heard: "{text[:66]}{"…" if len(text) > 66 else ""}"')

    warning = fusion.get("vernacular_warning")
    if warning:
        print(f"  {colour}warning:{RESET} {warning}")

    for code in fusion.get("reason_codes", []):
        cite = code.get("citation_url")
        print(f"    [{code.get('signal','?'):<12}] {code.get('code')}")
        if cite:
            print(f"                    {cite}")


async def run_demo() -> None:
    for clip, label, expected in DEMO_CLIPS:
        await _stream(clip, label, expected)
    print(f"\n{'=' * 74}\nDone. Same WebSocket, same 9s windows the phone uses.\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="store_true",
                        help="stream the demo clips and print verdicts")
    args = parser.parse_args()

    if args.run:
        asyncio.run(run_demo())
        return 0

    print("\nSatyaCheck pre-flight")
    ready = preflight()
    print(f"\n{GREEN}Ready.{RESET}\n" if ready
          else f"\n{RED}Not ready — fix the FAIL lines above.{RESET}\n")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
