"""Replay a recorded WAV through the live screening WebSocket, as if it came from
the phone.

Sends the same 3s, no-overlap chunks the app sends (config.STREAM_CONTEXT_S is the
backend's own trailing buffer, not the chunk size — see server/ws_router.py), at real
wall-clock pace, and prints every overlay_update the backend sends back. This is the
demo's fallback: if the live three-phone loop is not stable, this script streaming a
recorded clip drives the exact same backend path and the exact same overlay.

Usage:
    python scripts/replay_wav.py data/eval_set/clips/held-digital-arrest-004.wav
    python scripts/replay_wav.py some.wav --host 192.168.137.1 --port 8000 --chunk-s 3.0
    python scripts/replay_wav.py some.wav --no-realtime   # as fast as the server allows

CLI smoke test (no server needed): python -m scripts.replay_wav --selftest
"""

from __future__ import annotations

import argparse
import asyncio
import base64
import io
import json
import sys
import time
import uuid
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

RESET, RED, AMBER, GREEN, GREY = "\033[0m", "\033[91m", "\033[93m", "\033[92m", "\033[90m"
_COLOUR = {"red": RED, "amber": AMBER, "green": GREEN, "grey": GREY}


def split_into_wav_chunks(path: Path, chunk_s: float) -> list[bytes]:
    """Cut a WAV file into self-contained `chunk_s`-second WAV chunks — each one a
    complete RIFF file, the same shape `AudioChunk.toWav()` produces on the app side.
    ffmpeg cannot infer sample rate or bit depth from bare PCM bytes."""
    with wave.open(str(path), "rb") as src:
        params = src.getparams()
        chunk_frames = int(chunk_s * params.framerate)
        chunks = []
        while True:
            frames = src.readframes(chunk_frames)
            if not frames:
                break
            buf = io.BytesIO()
            with wave.open(buf, "wb") as out:
                out.setnchannels(params.nchannels)
                out.setsampwidth(params.sampwidth)
                out.setframerate(params.framerate)
                out.writeframes(frames)
            chunks.append(buf.getvalue())
    return chunks


def _print_overlay(overlay: dict, elapsed_s: float) -> None:
    colour = _COLOUR.get(overlay.get("state", "grey"), GREY)
    signals = overlay.get("signals", {})
    intent = signals.get("intent")
    intent_str = f"{intent:.2f}" if isinstance(intent, (int, float)) else str(intent)
    print(
        f"  t={elapsed_s:5.1f}s  {colour}{overlay.get('state', '?').upper():<6}{RESET}"
        f"  identity={signals.get('identity')}"
        f"  intent={intent_str}"
        f"  authenticity={signals.get('authenticity')}"
    )
    if overlay.get("evidence"):
        print(f'           evidence: "{overlay["evidence"]}"')
    print(f"           latency: {overlay.get('latency_ms', '?')} ms")


async def replay(
    wav_path: Path, *, host: str, port: int, chunk_s: float, realtime: bool, scheme: str = "ws",
) -> list[dict]:
    import websockets

    chunks = split_into_wav_chunks(wav_path, chunk_s)
    if not chunks:
        print(f"  {RED}no audio in {wav_path}{RESET}")
        return []

    session_id = f"replay-{wav_path.stem}-{uuid.uuid4().hex[:8]}"
    url = f"{scheme}://{host}:{port}/api/ws/screen/{session_id}"
    print(f"Replaying {wav_path.name} ({len(chunks)} x {chunk_s:.1f}s chunks) -> {url}")

    overlays = []
    started = time.perf_counter()
    async with websockets.connect(url) as ws:
        for i, chunk in enumerate(chunks):
            send_at = i * chunk_s
            if realtime:
                wait = send_at - (time.perf_counter() - started)
                if wait > 0:
                    await asyncio.sleep(wait)

            await ws.send(json.dumps({
                "type": "audio_chunk",
                "session_id": session_id,
                "chunk_index": i,
                "audio_base64": base64.b64encode(chunk).decode(),
                "is_final": i == len(chunks) - 1,
            }))

            # Two messages per chunk: screening_update (full contract, ignored here),
            # then overlay_update (what this tool prints).
            await asyncio.wait_for(ws.recv(), timeout=180)
            overlay = json.loads(await asyncio.wait_for(ws.recv(), timeout=180))
            _print_overlay(overlay, time.perf_counter() - started)
            overlays.append(overlay)

    return overlays


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wav", nargs="?", type=Path, help="WAV file to replay")
    parser.add_argument("--host", default="localhost")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--chunk-s", type=float, default=3.0, help="chunk size in seconds")
    parser.add_argument("--no-realtime", action="store_true", help="send as fast as the server allows")
    parser.add_argument("--selftest", action="store_true", help="CLI smoke test, no server needed")
    args = parser.parse_args(argv)

    if args.selftest:
        return _selftest()

    if args.wav is None:
        parser.error("wav is required unless --selftest")
    if not args.wav.is_file():
        print(f"{RED}not found:{RESET} {args.wav}")
        return 1

    overlays = asyncio.run(replay(
        args.wav, host=args.host, port=args.port, chunk_s=args.chunk_s, realtime=not args.no_realtime,
    ))
    return 0 if overlays else 1


def _selftest() -> int:
    """No server, no models: proves the chunker produces valid, complete WAV files."""
    print("=" * 60)
    print("scripts.replay_wav smoke test")
    print("=" * 60)

    src = REPO_ROOT / "data" / "eval_set" / "clips" / "friend_test.wav"
    if not src.is_file():
        print(f"  skip: {src} not present")
        return 0

    chunks = split_into_wav_chunks(src, chunk_s=3.0)
    assert chunks, "expected at least one chunk"
    for chunk in chunks:
        with wave.open(io.BytesIO(chunk), "rb") as w:
            assert w.getnchannels() == 1
            assert w.getsampwidth() == 2
            assert w.getnframes() > 0
    print(f"  ✓ {len(chunks)} chunk(s), each a valid mono 16-bit WAV")
    print("=" * 60)
    print("All self-tests passed!")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
