"""Upload adapter: a whole file (any format ffmpeg reads) -> fixed-duration AudioFrames.

The file is decoded once to 16 kHz mono s16le and cut into `frame_s` frames on one
timeline; the last frame carries `is_final` (the whole call is known). Frame size does
not change what the checks hear — the session buffer re-windows on hop boundaries.

Never raises (CLAUDE.md rule 5): undecodable input returns [] with the reason logged.
Imports only contracts, config and the stdlib.

Owned by the Track 1 (acquisition) person.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Union

import config
from acquisition._ffmpeg import decode_to_pcm16
from contracts import AudioFrame

log = logging.getLogger("satyacheck.acquisition.upload")

DEFAULT_FRAME_S = 1.0


def decode_upload(
    data: Union[bytes, str, Path],
    session_id: str,
    frame_s: float = DEFAULT_FRAME_S,
    mark_final: bool = True,
) -> list[AudioFrame]:
    """Decode a whole upload (bytes or a path) into AudioFrames. Never raises."""
    try:
        if isinstance(data, (str, Path)):
            try:
                data = Path(data).read_bytes()
            except OSError as e:
                log.warning(f"[{session_id}] upload could not be read: {e}")
                return []
        if not frame_s or frame_s <= 0:
            log.warning(f"[{session_id}] upload frame_s={frame_s!r} is invalid; "
                        f"using {DEFAULT_FRAME_S}s")
            frame_s = DEFAULT_FRAME_S
        pcm = decode_to_pcm16(data, session_id)
        if not pcm:
            log.warning(f"[{session_id}] upload of {len(data)} bytes holds no decodable "
                        f"audio; nothing to screen")
            return []
        sr = config.TARGET_SAMPLE_RATE
        step = max(1, int(round(frame_s * sr))) * 2
        frames = [
            AudioFrame(session_id=session_id, seq=k, t_start_s=(i // 2) / sr,
                       pcm_s16le=pcm[i:i + step])
            for k, i in enumerate(range(0, len(pcm), step))
        ]
        if mark_final and frames:
            frames[-1] = frames[-1].model_copy(update={"is_final": True})
        return frames
    except Exception as e:  # noqa: BLE001
        log.error(f"[{session_id}] upload decode failed: {type(e).__name__}: {e}")
        return []


if __name__ == "__main__":
    import sys

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    path = Path(sys.argv[1]) if len(sys.argv) > 1 else (
        config.REPO_ROOT / "data" / "eval_set" / "clips" / "friend_test.wav")
    frames = decode_upload(path, "smoke")
    assert decode_upload(b"not audio" * 50, "smoke-garbage") == []
    total = sum(len(f.pcm_s16le) for f in frames) / 2 / config.TARGET_SAMPLE_RATE
    print(f"[OK] upload: {path.name} -> {len(frames)} frames, {total:.2f}s, "
          f"final={frames[-1].is_final if frames else None}")
