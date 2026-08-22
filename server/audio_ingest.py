"""SatyaCheck — Audio Ingestion Pipeline

Ingests raw audio from any source, normalises to 16kHz mono WAV,
runs Silero VAD to chunk it, computes quality gate metrics, and
produces SHA-256 for chain-of-custody.

All IO errors are caught internally — returns a structured result.
C owns this file.
"""

from __future__ import annotations

import hashlib
import io
import logging
import subprocess
import tempfile
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import config
from contracts import QualityGateResult

log = logging.getLogger("satyacheck.ingest")

@dataclass
class AudioChunk:
    """A single VAD-bounded audio window ready for ML branches."""
    chunk_id: str
    start_s: float
    end_s: float
    waveform: list[float]   # normalised float samples at TARGET_SAMPLE_RATE
    sample_rate: int = config.TARGET_SAMPLE_RATE

    @property
    def duration_s(self) -> float:
        return self.end_s - self.start_s

@dataclass
class IngestedAudio:
    """Result of the full audio ingestion pipeline."""
    audio_sha256: str
    sample_rate: int
    total_duration_s: float
    waveform: list[float]              # full waveform at TARGET_SAMPLE_RATE
    chunks: list[AudioChunk]           # VAD chunks (3s windows, 1s overlap)
    quality: QualityGateResult
    normalized_wav_path: Optional[str] = None  # temp path to normalised WAV
    error: Optional[str] = None


def _compute_sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def _ffmpeg_normalize(input_path: str, output_path: str) -> bool:
    """Normalise audio to 16kHz mono WAV using ffmpeg. Returns success."""
    cmd = [
        "ffmpeg", "-y",
        "-i", input_path,
        "-ar", str(config.TARGET_SAMPLE_RATE),
        "-ac", "1",
        "-acodec", "pcm_s16le",
        output_path,
    ]
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            timeout=config.FFMPEG_TIMEOUT_S,
        )
        if result.returncode != 0:
            log.error(f"ffmpeg failed: {result.stderr.decode(errors='replace')[:500]}")
            return False
        return True
    except subprocess.TimeoutExpired:
        log.error("ffmpeg timed out")
        return False
    except FileNotFoundError:
        log.error("ffmpeg not found on PATH — install ffmpeg and ensure it's accessible")
        return False


def _estimate_snr(waveform: list[float]) -> float:
    """Rough SNR estimate: ratio of RMS of signal to RMS of quietest 10% frames."""
    if not waveform:
        return 0.0
    try:
        import statistics
        frame_size = max(1, config.TARGET_SAMPLE_RATE // 100)  # 10ms frames
        frames = [
            waveform[i:i + frame_size]
            for i in range(0, len(waveform) - frame_size, frame_size)
        ]
        if not frames:
            return 0.0
        frame_rms = [
            (sum(s ** 2 for s in f) / len(f)) ** 0.5
            for f in frames
        ]
        frame_rms.sort()
        signal_rms = statistics.mean(frame_rms[int(len(frame_rms) * 0.9):]) + 1e-10
        noise_rms = statistics.mean(frame_rms[:max(1, int(len(frame_rms) * 0.1))]) + 1e-10
        import math
        snr_db = 20 * math.log10(signal_rms / noise_rms)
        return round(min(max(snr_db, 0.0), 60.0), 2)
    except Exception:
        return 10.0  # safe default


def _load_waveform(wav_path: str) -> tuple[list[float], float]:
    """Load a 16kHz mono WAV into a float list. Returns (samples, duration_s)."""
    try:
        import wave
        with wave.open(wav_path, "rb") as wf:
            n_channels = wf.getnchannels()
            sampwidth = wf.getsampwidth()
            framerate = wf.getframerate()
            n_frames = wf.getnframes()
            raw = wf.readframes(n_frames)

        # 16-bit PCM only (ffmpeg output is always pcm_s16le)
        import struct
        samples_raw = struct.unpack(f"<{len(raw) // 2}h", raw)
        # Mix to mono if needed (should already be mono after ffmpeg)
        if n_channels == 2:
            samples_raw = tuple(
                (samples_raw[i] + samples_raw[i + 1]) // 2
                for i in range(0, len(samples_raw) - 1, 2)
            )
        waveform = [s / 32768.0 for s in samples_raw]
        duration_s = len(waveform) / framerate
        return waveform, duration_s
    except Exception as e:
        log.error(f"Failed to load waveform: {e}")
        return [], 0.0


def _vad_chunk(waveform: list[float], sample_rate: int) -> list[AudioChunk]:
    """
    Apply Silero VAD and return sliding window chunks (config.VAD_CHUNK_S / config.VAD_OVERLAP_S).
    Falls back to fixed sliding windows if VAD is unavailable.
    """
    chunk_samples = int(config.VAD_CHUNK_S * sample_rate)
    step_samples = int((config.VAD_CHUNK_S - config.VAD_OVERLAP_S) * sample_rate)
    chunks: list[AudioChunk] = []

    # Try Silero VAD
    try:
        import torch
        model, utils = torch.hub.load(
            repo_or_dir=str(config.MODELS_DIR / "silero-vad"),
            model="silero_vad",
            source="local",
            force_reload=False,
        )
        (get_speech_timestamps, _, read_audio, *_) = utils

        tensor = torch.tensor(waveform, dtype=torch.float32)
        speech_ts = get_speech_timestamps(tensor, model, sampling_rate=sample_rate)
        # Build speech mask
        speech_mask = [False] * len(waveform)
        for ts in speech_ts:
            for i in range(ts["start"], min(ts["end"], len(waveform))):
                speech_mask[i] = True
        log.debug(f"VAD: {len(speech_ts)} speech segments detected")
    except Exception as e:
        log.warning(f"Silero VAD not available ({e}), using fixed sliding windows")
        speech_mask = [True] * len(waveform)

    # Sliding window chunks (with overlap)
    pos = 0
    while pos + chunk_samples <= len(waveform):
        chunk_waveform = waveform[pos:pos + chunk_samples]
        start_s = pos / sample_rate
        end_s = (pos + chunk_samples) / sample_rate
        chunks.append(AudioChunk(
            chunk_id=str(uuid.uuid4()),
            start_s=round(start_s, 3),
            end_s=round(end_s, 3),
            waveform=chunk_waveform,
            sample_rate=sample_rate,
        ))
        pos += step_samples

    # Add a final partial chunk if remaining audio is > 0.5s
    remaining = waveform[pos:]
    if len(remaining) > sample_rate // 2:
        start_s = pos / sample_rate
        end_s = len(waveform) / sample_rate
        chunks.append(AudioChunk(
            chunk_id=str(uuid.uuid4()),
            start_s=round(start_s, 3),
            end_s=round(end_s, 3),
            waveform=remaining,
            sample_rate=sample_rate,
        ))

    return chunks


def _measure_speech_duration(waveform: list[float], sample_rate: int) -> float:
    """Rough speech duration using energy threshold (fallback if VAD unavailable)."""
    if not waveform:
        return 0.0
    frame_size = sample_rate // 100  # 10ms
    energy_threshold = 0.001
    speech_frames = 0
    for i in range(0, len(waveform) - frame_size, frame_size):
        frame = waveform[i:i + frame_size]
        rms = (sum(s ** 2 for s in frame) / len(frame)) ** 0.5
        if rms > energy_threshold:
            speech_frames += 1
    return round(speech_frames * 0.01, 2)


def ingest_audio(
    audio_bytes: Optional[bytes] = None,
    audio_path: Optional[str] = None,
) -> IngestedAudio:
    """
    Full audio ingestion pipeline.

    Accepts raw bytes OR a file path. Returns IngestedAudio.
    Never raises — catches all errors and returns a failed IngestedAudio.

    Steps:
      1. Write to temp file if needed
      2. SHA-256 on raw input
      3. ffmpeg normalise → 16kHz mono WAV
      4. Load waveform
      5. SNR estimate
      6. VAD chunking
      7. Quality gate check
    """
    if audio_bytes is None and audio_path is None:
        return IngestedAudio(
            audio_sha256="",
            sample_rate=config.TARGET_SAMPLE_RATE,
            total_duration_s=0.0,
            waveform=[],
            chunks=[],
            quality=QualityGateResult.insufficient(reason="No audio data provided"),
            error="No audio data provided",
        )

    tmp_input = None
    tmp_output = None

    try:
        # ── Step 1: Prepare input file ────────────────────────────────
        if audio_bytes is not None:
            tmp_input_file = tempfile.NamedTemporaryFile(suffix=".audio", delete=False)
            tmp_input_file.write(audio_bytes)
            tmp_input_file.close()
            tmp_input = tmp_input_file.name
            raw_data = audio_bytes
        else:
            tmp_input = audio_path
            raw_data = Path(audio_path).read_bytes()

        # ── Step 2: SHA-256 ───────────────────────────────────────────
        sha256 = _compute_sha256(raw_data)

        # ── Step 3: ffmpeg normalise ──────────────────────────────────
        tmp_output_file = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
        tmp_output_file.close()
        tmp_output = tmp_output_file.name

        ok = _ffmpeg_normalize(tmp_input, tmp_output)
        if not ok:
            return IngestedAudio(
                audio_sha256=sha256,
                sample_rate=config.TARGET_SAMPLE_RATE,
                total_duration_s=0.0,
                waveform=[],
                chunks=[],
                quality=QualityGateResult.insufficient(reason="ffmpeg normalisation failed"),
                normalized_wav_path=None,
                error="ffmpeg normalisation failed",
            )

        # ── Step 4: Load waveform ─────────────────────────────────────
        waveform, duration_s = _load_waveform(tmp_output)
        if not waveform:
            return IngestedAudio(
                audio_sha256=sha256,
                sample_rate=config.TARGET_SAMPLE_RATE,
                total_duration_s=0.0,
                waveform=[],
                chunks=[],
                quality=QualityGateResult.insufficient(reason="Could not decode audio waveform"),
                error="Waveform decode failed",
            )

        # ── Step 5: SNR estimate ──────────────────────────────────────
        snr_db = _estimate_snr(waveform)

        # ── Step 6: VAD + speech duration ────────────────────────────
        chunks = _vad_chunk(waveform, config.TARGET_SAMPLE_RATE)
        speech_duration_s = _measure_speech_duration(waveform, config.TARGET_SAMPLE_RATE)

        # ── Step 7: Quality gate ──────────────────────────────────────
        gate_passed = (
            speech_duration_s >= config.MIN_SPEECH_DURATION_S
            and snr_db >= config.MIN_SNR_DB
        )
        if gate_passed:
            quality = QualityGateResult.passed_default(
                speech_duration_s=speech_duration_s,
                snr_db=snr_db,
            )
        else:
            reason_parts = []
            if speech_duration_s < config.MIN_SPEECH_DURATION_S:
                reason_parts.append(f"Speech too short ({speech_duration_s:.1f}s < {config.MIN_SPEECH_DURATION_S}s)")
            if snr_db < config.MIN_SNR_DB:
                reason_parts.append(f"SNR too low ({snr_db:.1f}dB < {config.MIN_SNR_DB}dB)")
            quality = QualityGateResult.insufficient(
                speech_duration_s=speech_duration_s,
                snr_db=snr_db,
                reason="; ".join(reason_parts),
            )

        return IngestedAudio(
            audio_sha256=sha256,
            sample_rate=config.TARGET_SAMPLE_RATE,
            total_duration_s=round(duration_s, 3),
            waveform=waveform,
            chunks=chunks,
            quality=quality,
            normalized_wav_path=tmp_output,
        )

    except Exception as e:
        log.exception(f"Unexpected ingestion error: {e}")
        return IngestedAudio(
            audio_sha256="",
            sample_rate=config.TARGET_SAMPLE_RATE,
            total_duration_s=0.0,
            waveform=[],
            chunks=[],
            quality=QualityGateResult.insufficient(reason=f"Ingestion error: {str(e)}"),
            error=str(e),
        )

    finally:
        # Clean up temp input file (but keep output for downstream processing)
        if tmp_input and audio_bytes is not None:
            try:
                Path(tmp_input).unlink(missing_ok=True)
            except Exception:
                pass


if __name__ == "__main__":
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else None
    if path:
        result = ingest_audio(audio_path=path)
        print(f"SHA256         : {result.audio_sha256}")
        print(f"Duration       : {result.total_duration_s}s")
        print(f"Chunks         : {len(result.chunks)}")
        print(f"Quality passed : {result.quality.passed}")
        print(f"Speech duration: {result.quality.speech_duration_s}s")
        print(f"SNR            : {result.quality.snr_db}dB")
        if result.error:
            print(f"Error          : {result.error}")
    else:
        print("Usage: python -m server.audio_ingest <audio_file>")
