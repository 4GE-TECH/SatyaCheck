"""ffmpeg decode to the pipeline's one audio format: 16 kHz mono s16le, raw.

Private to acquisition/. Imports only the stdlib and config (CLAUDE.md, boundaries).
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from typing import Optional

import config

log = logging.getLogger("satyacheck.acquisition")


def decode_to_pcm16(data: bytes, label: str) -> Optional[bytes]:
    """Decode any container/codec ffmpeg reads to raw 16 kHz mono s16le bytes.

    A temp file, not stdin: some containers (mp4/m4a with the index at the end) cannot be
    demuxed from a pipe. Returns None, with the reason logged, on any failure. Never raises.
    """
    if not data:
        log.warning(f"[{label}] no audio: empty input")
        return None
    tmp = None
    try:
        fd, tmp = tempfile.mkstemp(prefix="satyacheck_acq_", suffix=".bin")
        with os.fdopen(fd, "wb") as f:
            f.write(data)
        cmd = [
            "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
            "-i", tmp,
            "-vn", "-ac", "1", "-ar", str(config.TARGET_SAMPLE_RATE),
            "-acodec", "pcm_s16le", "-f", "s16le", "pipe:1",
        ]
        result = subprocess.run(cmd, capture_output=True, timeout=config.FFMPEG_TIMEOUT_S)
        if result.returncode != 0:
            err = result.stderr.decode(errors="replace").strip()[:300]
            log.warning(f"[{label}] ffmpeg could not decode {len(data)} bytes "
                        f"(exit {result.returncode}): {err}")
            return None
        pcm = result.stdout
        if len(pcm) % 2:
            pcm = pcm[:-1]
        if not pcm:
            log.warning(f"[{label}] no audio: ffmpeg decoded {len(data)} bytes to 0 samples")
            return None
        return pcm
    except subprocess.TimeoutExpired:
        log.warning(f"[{label}] ffmpeg timed out after {config.FFMPEG_TIMEOUT_S}s "
                    f"on {len(data)} bytes")
        return None
    except FileNotFoundError:
        log.error(f"[{label}] ffmpeg not found on PATH; cannot decode audio")
        return None
    except Exception as e:  # noqa: BLE001
        log.error(f"[{label}] ffmpeg decode failed: {type(e).__name__}: {e}")
        return None
    finally:
        if tmp is not None:
            try:
                os.unlink(tmp)
            except OSError:
                pass
