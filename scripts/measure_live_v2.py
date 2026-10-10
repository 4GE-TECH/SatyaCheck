"""Measure the v2 live path under load (upgrade plan, Phase 3, "measure before promising").

Starts a real server (uvicorn, real models, WARM_MODELS=true) on localhost against a
throwaway SQLite database — never the configured Supabase — then streams N simultaneous
calls through /api/ws/v2/screen at real-time pace (0.5 s binary frames), each a
`--call-s` second call made by looping eval clips.

Reported per concurrency level (p50 / p95 / p99, seconds):
  * update latency      speech -> the assessment covering it arrives
                        (arrival time - wall time its last sample was sent)
  * commit latency      speech -> the words are committed in the transcript
  * coverage            sessions that reported unscored gaps; catch-up backlog
and once: cold readiness (process start -> /api/ready 200).

Usage:  python -m scripts.measure_live_v2 --levels 1 2 4 8 --call-s 90

Exits 1 on errors, a model fallback, not-ready, or when even one voice misses ACCEPT.
Writes data/measurements/live_v2_latency.json (numbers and file names only, no audio).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

import numpy as np

import config

CLIPS = ["friend_test", "held-family-emergency-001", "held-digital-arrest-004", "me_test2"]
FRAME_S = 0.5
OUT = config.REPO_ROOT / "data" / "measurements" / "live_v2_latency.json"


def _pct(values, q):
    return round(float(np.percentile(values, q)), 3) if values else None


def _stats(values):
    return {"n": len(values), "p50": _pct(values, 50), "p95": _pct(values, 95), "p99": _pct(values, 99),
            "max": round(max(values), 3) if values else None}


def _call_audio(seconds: float, offset: int) -> bytes:
    import soundfile as sf

    parts, total = [], 0
    k = offset
    while total < seconds * 16000:
        audio, sr = sf.read(str(config.REPO_ROOT / "data" / "eval_set" / "clips" / f"{CLIPS[k % len(CLIPS)]}.wav"),
                            dtype="int16")
        assert sr == 16000
        parts.append(audio if audio.ndim == 1 else audio[:, 0])
        total += len(parts[-1])
        k += 1
    return np.concatenate(parts)[: int(seconds * 16000)].astype("<i2").tobytes()


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start_server(port: int, db: Path, log_path: Path) -> tuple[subprocess.Popen, float]:
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "AUTH_MODE": "dev", "SATYACHECK_ENV": "dev",
           "WARM_MODELS": "true", "MAX_LIVE_SESSIONS": "64", "LOG_LEVEL": "WARNING", "ENABLE_EXOTEL": "false"}
    started = time.monotonic()
    log_file = log_path.open("wb")
    proc = subprocess.Popen([sys.executable, "-m", "uvicorn", "server.main:app", "--host", "127.0.0.1",
                             "--port", str(port), "--log-level", "warning"], cwd=str(config.REPO_ROOT), env=env,
                            # A file, not a pipe: nobody reads a pipe while calls run, and once
                            # its buffer fills the server blocks on its next log line.
                            stdout=subprocess.DEVNULL, stderr=log_file)
    proc.log_file = log_file   # closed after the server exits (Windows keeps the dir otherwise)
    deadline = started + 600
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ready", timeout=2) as r:
                if r.status == 200:
                    return proc, time.monotonic() - started
        except Exception:
            pass
        if proc.poll() is not None:
            raise SystemExit(f"server exited: {log_path.read_text(errors='replace')[-2000:]}")
        time.sleep(1.0)
    proc.kill()
    raise SystemExit("server never became ready")


async def one_call(port: int, session_id: str, pcm: bytes) -> dict:
    import websockets

    from contracts import StreamV2Start

    updates, commits, degraded, finals = [], [], False, 0
    seen_segments: set = set()
    step = int(16000 * 2 * FRAME_S)
    async with websockets.connect(f"ws://127.0.0.1:{port}/api/ws/v2/screen/{session_id}", max_size=None) as ws:
        await ws.send(StreamV2Start(client="measure").model_dump_json())
        assert json.loads(await ws.recv())["type"] == "ready"
        t0 = time.monotonic()

        async def send():
            for k, i in enumerate(range(0, len(pcm), step)):
                target = t0 + k * FRAME_S          # real-time pacing
                await asyncio.sleep(max(0.0, target - time.monotonic()))
                await ws.send(pcm[i:i + step])
            await asyncio.sleep(max(0.0, t0 + len(pcm) / 32000 - time.monotonic()))
            await ws.send(json.dumps({"type": "end"}))

        sender = asyncio.create_task(send())
        while True:
            msg = json.loads(await ws.recv())
            now = time.monotonic()
            if msg["type"] != "assessment":
                continue
            sent_at = t0 + msg["audio_end_s"]       # when the window's last sample left
            if not msg["is_final"]:
                updates.append(now - sent_at)
            for seg in msg["current"]["transcript"]["segments"]:
                key = (seg["start_s"], seg["end_s"], seg["text"])
                if key not in seen_segments:
                    seen_segments.add(key)
                    if not msg["is_final"]:
                        commits.append(now - (t0 + seg["end_s"]))
            degraded = degraded or msg["coverage_degraded"]
            if msg["is_final"]:
                finals += 1
                break
        await sender
    return {"updates": updates, "commits": commits, "degraded": degraded, "finals": finals}


async def level(port: int, n: int, call_s: float) -> dict:
    limit = call_s * 3 + 120   # a call that never gets its final assessment is an error, not a hang
    calls = [asyncio.wait_for(one_call(port, f"measure-{n}-{k}-{int(time.time())}", _call_audio(call_s, k)), limit)
             for k in range(n)]
    results = await asyncio.gather(*calls, return_exceptions=True)
    ok = [r for r in results if isinstance(r, dict)]
    errors = [f"{type(r).__name__}: {r}" for r in results if not isinstance(r, dict)]
    return {"sessions": n, "call_s": call_s, "completed": len(ok), "errors": errors,
            "update_latency_s": _stats([x for r in ok for x in r["updates"]]),
            "commit_latency_s": _stats([x for r in ok for x in r["commits"]]),
            "sessions_with_coverage_gaps": sum(r["degraded"] for r in ok)}


# Acceptance per level. Levels count screened voices: a WebRTC call is two of them.
# GPU memory is judged as this server's share (usage above what the GPU held before it
# started; other apps come and go), plus headroom left on the whole card.
ACCEPT = {"update_p95_s": 4.0, "coverage_gap_sessions": 0, "server_gpu_mb": 6144, "card_headroom_mb": 512}


def _gpu_used_mb():
    try:
        out = subprocess.run(["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits"],
                             capture_output=True, text=True, timeout=5).stdout.strip().splitlines()[0]
        return int(out)
    except Exception:  # noqa: BLE001 — no GPU
        return None


def _ready(port: int) -> dict:
    with urllib.request.urlopen(f"http://127.0.0.1:{port}/api/ready", timeout=5) as r:
        return json.loads(r.read())


def _verdict(result: dict, ready: dict, baseline_mb) -> tuple[list[str], list[str]]:
    """(hard failures, acceptance misses). A hard failure means the run cannot be trusted:
    errors, incomplete sessions, a model off the expected device or not loaded."""
    hard, miss = [], []
    if result["errors"] or result["completed"] != result["sessions"]:
        hard.append(f"{result['sessions'] - result['completed']} incomplete session(s): {result['errors'][:3]}")
    if not ready.get("ready"):
        hard.append(f"server not ready: {ready.get('problems')}")
    if ready.get("fallbacks"):
        hard.append(f"model fallbacks: {ready['fallbacks']}")
    for name, info in (ready.get("models") or {}).items():
        if isinstance(info, dict) and info.get("device") not in (ready.get("device"),):
            hard.append(f"{name} on {info.get('device')}, expected {ready.get('device')}")
    p95 = (result["update_latency_s"] or {}).get("p95")
    if p95 is None or p95 > ACCEPT["update_p95_s"]:
        miss.append(f"update p95 {p95} s > {ACCEPT['update_p95_s']} s")
    if result["sessions_with_coverage_gaps"] > ACCEPT["coverage_gap_sessions"]:
        miss.append(f"{result['sessions_with_coverage_gaps']} session(s) with coverage gaps")
    vram = ready.get("vram") or {}
    used, total = vram.get("gpu_used_mb"), vram.get("gpu_total_mb")
    if used is not None and baseline_mb is not None:
        server = used - baseline_mb
        result["server_gpu_mb"] = server
        if server > ACCEPT["server_gpu_mb"]:
            miss.append(f"server GPU memory {server} MB > {ACCEPT['server_gpu_mb']} MB")
        if total is not None and total - used < ACCEPT["card_headroom_mb"]:
            miss.append(f"only {total - used} MB left on the card (< {ACCEPT['card_headroom_mb']} MB)")
    return hard, miss


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split(chr(10) * 2)[0])
    ap.add_argument("--levels", type=int, nargs="+", default=[1, 2, 4, 8])
    ap.add_argument("--call-s", type=float, default=180.0)
    args = ap.parse_args()
    port = _free_port()
    levels, failed_hard = [], False
    baseline_mb = _gpu_used_mb()
    print(f"GPU memory in use before the server starts: {baseline_mb} MB", flush=True)
    with tempfile.TemporaryDirectory() as tmp:
        proc, cold_s = start_server(port, Path(tmp) / "measure.db", Path(tmp) / "server.log")
        print(f"cold readiness: {cold_s:.1f}s", flush=True)
        try:
            start_state = _ready(port)
            print(f"device {start_state.get('device')}, models {start_state.get('models')}", flush=True)
            for n in args.levels:
                result = asyncio.run(level(port, n, args.call_s))
                state = _ready(port)
                hard, miss = _verdict(result, state, baseline_mb)
                result.update({"vram": state.get("vram"), "models": state.get("models"),
                               "hard_failures": hard, "acceptance_misses": miss,
                               "passed": not hard and not miss})
                levels.append(result)
                print(json.dumps(result), flush=True)
                if hard:
                    failed_hard = True
                    break
                if miss:
                    break   # higher levels only get worse
        finally:
            proc.terminate()
            proc.wait(timeout=30)
            proc.log_file.close()

    passing = [lv["sessions"] for lv in levels if lv["passed"]]
    report = {"device": start_state.get("device"), "models": start_state.get("models"),
              "cold_readiness_s": round(cold_s, 1), "frame_s": FRAME_S, "hop_s": config.STREAM_HOP_S,
              "acceptance": ACCEPT, "gpu_baseline_mb": baseline_mb, "max_passing_voices": max(passing) if passing else 0, "levels": levels,
              "note": "In-process localhost; no network or telephone codec. Real models."}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"wrote {OUT}; max passing level: {report['max_passing_voices']} voice(s)")
    if failed_hard:
        print("LOAD GATE FAILED: the run hit errors or a model fallback; numbers are not trustworthy")
        return 1
    if not passing:
        print("LOAD GATE FAILED: even one voice misses the acceptance limits")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
