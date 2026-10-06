"""Latency and false-positive rate on the (simulated) Exotel path — item 14.

    python -m scripts.measure_pipeline --clips data/eval_set/clips/friend_test.wav --genuine \\
        [--manifest <ifd>/manifest.csv --split test --limit 20 --seed 0] \\
        [--speed 1] [--encoding raw|mulaw] [--label genuine] [--out data/measurements/exotel_genuine.json]

Each file is replayed as one Exotel Stream call — connected, start, 100 ms media
messages at 8 kHz (raw s16le or mu-law), stop — through the real Exotel route
(acquisition/exotel) and the real SessionRunner, with the branches the current config
flags select. Messages are paced in real time by default; --speed N sends N times
faster, which also understates the CPU contention a live call would see.

Reported, with n:
  * latency: frame arrival -> verdict dispatched, per window (p50 / p95 / max, ms);
  * time to first transcript per call (p50 / p95, s);
  * false-positive rate: share of GENUINE calls whose final (latched) band is suspicious
    or high_risk; caution reported separately, with the files that tripped either.

What this is not: a live Exotel call. The 8 kHz conversion here is a resample, not the
telephone network; real calls add a codec, jitter and network latency. Measure those on
the team's Exotel number before quoting numbers as "on a phone call".

Writes numbers and file names only — never audio. Exit codes: 0 ok, 1 no input, 3 a
call produced no verdict at all.
"""

from __future__ import annotations

import argparse
import base64
import csv
import glob
import json
import logging
import math
import secrets
import sys
import tempfile
import time
from pathlib import Path
from typing import Optional, Sequence

import numpy as np

import config

log = logging.getLogger("satyacheck.measure")

WARNING_BANDS = {"suspicious", "high_risk"}
MESSAGE_MS = 100
CALL_RATE = 8000


# --- arithmetic -----------------------------------------------------------------------------

def percentile(values: Sequence[float], q: float) -> float:
    """Linear-interpolation percentile (numpy's default); NaN for no values."""
    return float(np.percentile(np.asarray(values, dtype=float), q)) if len(values) else float("nan")


def _stats(values: Sequence[float], digits: int = 1) -> dict:
    clean = [v for v in values if v is not None and not math.isnan(v)]
    if not clean:
        return {"n": 0, "p50": None, "p95": None, "max": None}
    return {"n": len(clean), "p50": round(percentile(clean, 50), digits),
            "p95": round(percentile(clean, 95), digits), "max": round(max(clean), digits)}


def summarise(sessions: list[dict]) -> dict:
    genuine = [s for s in sessions if s.get("genuine")]
    fp = [s["file"] for s in genuine if s.get("final_band") in WARNING_BANDS]
    caution = [s["file"] for s in genuine if s.get("final_band") == "caution"]
    latencies = [ms for s in sessions for ms in s.get("latencies_ms", [])]
    return {
        "n_sessions": len(sessions),
        "n_genuine": len(genuine),
        "n_windows": len(latencies),
        "latency_ms": _stats(latencies),
        "first_transcript_s": _stats([s.get("first_transcript_s") for s in sessions], 2),
        "false_positive_rate": (len(fp) / len(genuine)) if genuine else None,
        "false_positive_files": fp,
        "caution_rate": (len(caution) / len(genuine)) if genuine else None,
        "caution_files": caution,
    }


# --- building an Exotel call from a file ---------------------------------------------------------

def _mulaw_encode(pcm: np.ndarray) -> bytes:
    """ITU-T G.711 mu-law compression (bias 0x84, clip 32635)."""
    x = pcm.astype(np.int32)
    sign = np.where(x < 0, 0x80, 0x00)
    magnitude = np.minimum(np.abs(x), 32635) + 0x84
    exponent = np.floor(np.log2(magnitude)).astype(np.int32) - 7
    exponent = np.clip(exponent, 0, 7)
    mantissa = (magnitude >> (exponent + 3)) & 0x0F
    return (~(sign | (exponent << 4) | mantissa) & 0xFF).astype(np.uint8).tobytes()


def _call_audio(path: Path) -> Optional[np.ndarray]:
    """Any audio file -> int16 at 8 kHz (a resample standing in for the phone channel)."""
    from scipy.signal import resample_poly

    from acquisition._ffmpeg import decode_to_pcm16

    pcm16k = decode_to_pcm16(path.read_bytes(), label=path.name)
    if not pcm16k:
        log.error(f"could not decode {path}")
        return None
    x = np.frombuffer(pcm16k, dtype="<i2").astype(np.float64)
    return np.clip(np.round(resample_poly(x, 1, 2)), -32768, 32767).astype(np.int16)


def _messages(audio: np.ndarray, encoding: str, stream_sid: str) -> list[str]:
    msgs = [json.dumps({"event": "connected"}), json.dumps({
        "event": "start", "sequence_number": 1, "stream_sid": stream_sid,
        "start": {"stream_sid": stream_sid, "call_sid": f"CA{stream_sid}", "from": "+910000000000",
                  "to": "+911111111111", "custom_parameters": {},
                  "media_format": {"encoding": "audio/x-mulaw" if encoding == "mulaw" else "raw",
                                   "sample_rate": str(CALL_RATE), "bit_rate": "64"}}})]
    step = CALL_RATE * MESSAGE_MS // 1000
    for k, i in enumerate(range(0, len(audio), step)):
        chunk = audio[i:i + step]
        payload = _mulaw_encode(chunk) if encoding == "mulaw" else chunk.astype("<i2").tobytes()
        msgs.append(json.dumps({"event": "media", "sequence_number": k + 2, "stream_sid": stream_sid,
                                "media": {"chunk": k + 1, "timestamp": k * MESSAGE_MS,
                                          "payload": base64.b64encode(payload).decode()}}))
    msgs.append(json.dumps({"event": "stop", "sequence_number": len(msgs) + 1, "stream_sid": stream_sid,
                            "stop": {"reason": "callended"}}))
    return msgs


# --- replaying one call -----------------------------------------------------------------------------

def replay(path: Path, genuine: bool, speed: float, encoding: str, runner_kwargs: dict,
           session_factory) -> Optional[dict]:
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    from acquisition.api import build_exotel_router
    from server.pipeline.dispatcher import Dispatcher
    from server.pipeline.runner import SessionRunner

    audio = _call_audio(path)
    if audio is None:
        return None
    latencies, events, made = [], [], []

    def observer(event, seconds):
        latencies.append(seconds * 1000.0)
        events.append(event)

    def factory():
        runner = SessionRunner(dispatcher=Dispatcher([]), session_factory=session_factory,
                               observer=observer, **runner_kwargs)
        made.append(runner)
        return runner

    app = FastAPI()
    app.include_router(build_exotel_router(factory))
    user, password = "measure", secrets.token_hex(16)
    saved = (config.EXOTEL_BASIC_USER, config.EXOTEL_BASIC_PASS, config.EXOTEL_ALLOWED_IPS)
    config.EXOTEL_BASIC_USER, config.EXOTEL_BASIC_PASS, config.EXOTEL_ALLOWED_IPS = user, password, []
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    first_transcript = None
    try:
        with TestClient(app) as client, client.websocket_connect(
                config.EXOTEL_WS_PATH, headers={"authorization": f"Basic {token}"}) as ws:
            messages = _messages(audio, encoding, stream_sid=f"m{secrets.token_hex(6)}")
            started = None
            for m in messages:
                ws.send_text(m)
                if '"event": "media"' in m:
                    started = started or time.monotonic()
                    time.sleep(MESSAGE_MS / 1000.0 / speed)
                if first_transcript is None and made and started is not None:
                    worker = next((made[0].worker(sid) for sid in list(made[0]._sessions)), None)
                    latest = worker.latest if worker else None
                    if latest is not None and latest.transcript.text.strip():
                        first_transcript = time.monotonic() - started
            ws.receive()  # the server closes after stop
    finally:
        config.EXOTEL_BASIC_USER, config.EXOTEL_BASIC_PASS, config.EXOTEL_ALLOWED_IPS = saved
    if not events:
        log.error(f"{path.name}: the call produced no verdict at all")
        return {"file": path.name, "genuine": genuine, "final_band": None, "latencies_ms": [],
                "first_transcript_s": first_transcript, "error": "no verdict"}
    final = events[-1]
    return {
        "file": path.name,
        "genuine": genuine,
        "audio_s": round(len(audio) / CALL_RATE, 2),
        "n_windows": len(events),
        "final_band": final.response.fusion.band.value,
        "final_is_final": final.is_final,
        "bands": [e.response.fusion.band.value for e in events],
        "latencies_ms": [round(ms, 1) for ms in latencies],
        "first_transcript_s": None if first_transcript is None else round(first_transcript, 2),
    }


# --- inputs and the CLI -------------------------------------------------------------------------------

def _from_manifest(manifest: Path, split: str, limit: int, seed: int) -> list[Path]:
    with manifest.open(newline="", encoding="utf-8") as fh:
        rows = [r for r in csv.DictReader(fh) if r.get("split") == split and str(r.get("label")) == "1"]
    rng = np.random.default_rng(seed)
    picked = [rows[i] for i in sorted(rng.permutation(len(rows))[:limit])]
    return [manifest.parent / r["filepath"] for r in picked]


def main(argv: Optional[Sequence[str]] = None, runner_kwargs: Optional[dict] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--clips", nargs="*", default=[], help="files or globs")
    ap.add_argument("--genuine", action="store_true", help="the --clips are genuine human speech")
    ap.add_argument("--manifest", type=Path, help="IFD-style manifest; label 1 rows are genuine")
    ap.add_argument("--split", default="test")
    ap.add_argument("--limit", type=int, default=20)
    ap.add_argument("--seed", type=int, default=0)
    ap.add_argument("--speed", type=float, default=1.0)
    ap.add_argument("--encoding", choices=["raw", "mulaw"], default="raw")
    ap.add_argument("--label", default="run")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)

    inputs: list[tuple[Path, bool]] = []
    for pattern in args.clips:
        for f in sorted(glob.glob(pattern)) or ([pattern] if Path(pattern).is_file() else []):
            inputs.append((Path(f), args.genuine))
    if args.manifest:
        inputs += [(p, True) for p in _from_manifest(args.manifest, args.split, args.limit, args.seed)]
    inputs = [(p, g) for p, g in inputs if p.is_file()]
    if not inputs:
        log.error("no input audio found")
        return 1

    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker

    from server.database import Base

    with tempfile.TemporaryDirectory() as tmp:
        engine = create_engine(f"sqlite:///{Path(tmp) / 'measure.db'}")
        Base.metadata.create_all(engine)
        sessions = []
        for k, (path, genuine) in enumerate(inputs, 1):
            log.info(f"[{k}/{len(inputs)}] {path.name}")
            result = replay(path, genuine, args.speed, args.encoding, runner_kwargs or {},
                            sessionmaker(bind=engine))
            if result is not None:
                sessions.append(result)
        engine.dispose()

    report = {
        "label": args.label,
        "config": {"speed": args.speed, "encoding": args.encoding, "call_rate_hz": CALL_RATE,
                   "message_ms": MESSAGE_MS, "USE_REAL_SPEAKER": config.USE_REAL_SPEAKER,
                   "USE_REAL_SPOOF": config.USE_REAL_SPOOF, "USE_REAL_NLP": config.USE_REAL_NLP,
                   "SPOOF_OOD_ENABLED": getattr(config, "SPOOF_OOD_ENABLED", None),
                   "ESCALATION_PERSISTENCE_N": config.ESCALATION_PERSISTENCE_N},
        "caveat": "simulated Exotel path (resampled to 8 kHz, local socket); not a live phone call",
        **summarise(sessions),
        "sessions": sessions,
    }
    out = args.out or config.DATA_DIR / "measurements" / f"exotel_{args.label}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, indent=2), encoding="utf-8")
    log.info(f"wrote {out}")
    return 3 if any(s.get("error") for s in sessions) else 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    sys.exit(main())
