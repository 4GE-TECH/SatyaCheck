"""acquisition/ public surface — the only names server/ may import from here.

Adapters turn a transport's audio into `contracts.AudioFrame` (16 kHz mono s16le) on
one continuing timeline. The transport is named only on `contracts.SessionOpen.source`,
set by whoever mounts the adapter; no frame carries it, so no check can see it
(server/tests/test_transport_invariant.py).

acquisition/ imports only contracts, config, the stdlib, numpy and an ffmpeg subprocess.
"""

from __future__ import annotations

from acquisition.app_ws import AppWsDecoder
from acquisition.upload import DEFAULT_FRAME_S, decode_upload


def build_exotel_router(runner_factory):
    """The Exotel Stream WebSocket route (imported lazily: FastAPI is only needed here)."""
    from acquisition.exotel.router import build_exotel_router as _build

    return _build(runner_factory)


__all__ = ["AppWsDecoder", "decode_upload", "DEFAULT_FRAME_S", "build_exotel_router"]
