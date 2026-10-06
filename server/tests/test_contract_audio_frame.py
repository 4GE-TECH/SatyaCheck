"""C1: the transport-agnostic frame contract (items 1–6).

`AudioFrame` is what every check path receives, whatever the audio came through —
Exotel, the app's WebSocket, an upload, a bystander laptop. The transport is named in
exactly one place, `SessionOpen.source`, which only the runner and dispatcher see.

These tests pin the shape, because three people code against it: a field quietly added
to `AudioFrame` that names a transport is the leak item 2's invariance test exists to
catch, so the frame's field set is asserted exactly.
"""

from __future__ import annotations

import numpy as np
import pytest
from pydantic import ValidationError

from contracts import AudioFrame, AudioSource, CallerMetadata, SessionClose, SessionOpen


def _pcm(n: int = 160) -> bytes:
    """Non-UTF-8 bytes on purpose: real PCM is arbitrary binary."""
    return (np.arange(n, dtype="<i2") * 397 - 30000).astype("<i2").tobytes()


def test_frame_has_exactly_the_agreed_fields():
    assert set(AudioFrame.model_fields) == {
        "session_id", "seq", "t_start_s", "pcm_s16le", "sample_rate", "is_final",
    }


def test_no_transport_detail_on_the_frame():
    for name in AudioFrame.model_fields:
        assert name not in {"source", "channel_type", "codec", "transport"}


def test_frame_is_16k_only():
    AudioFrame(session_id="s", seq=0, t_start_s=0.0, pcm_s16le=_pcm())
    with pytest.raises(ValidationError):
        AudioFrame(session_id="s", seq=0, t_start_s=0.0, pcm_s16le=_pcm(), sample_rate=8000)


@pytest.mark.parametrize("field, value", [("seq", -1), ("t_start_s", -0.5)])
def test_frame_rejects_negative_positions(field, value):
    kwargs = {"session_id": "s", "seq": 0, "t_start_s": 0.0, "pcm_s16le": _pcm(), field: value}
    with pytest.raises(ValidationError):
        AudioFrame(**kwargs)


def test_binary_pcm_survives_a_json_round_trip():
    """Default Pydantic serialises bytes as UTF-8, which fails on real PCM."""
    frame = AudioFrame(session_id="s", seq=3, t_start_s=1.5, pcm_s16le=_pcm(), is_final=True)
    again = AudioFrame.model_validate_json(frame.model_dump_json())
    assert again == frame


def test_session_open_names_the_source_and_carries_optional_context():
    opened = SessionOpen(session_id="s", source=AudioSource.EXOTEL)
    assert opened.caller_context is None and opened.opened_at
    with_ctx = SessionOpen(session_id="s", source="app_ws",
                           caller_context=CallerMetadata(claimed_number="+911234567890"))
    assert with_ctx.source is AudioSource.APP_WS
    with pytest.raises(ValidationError):
        SessionOpen(session_id="s", source="webrtc")


def test_sources_are_the_four_agreed_ones():
    assert {s.value for s in AudioSource} == {"exotel", "app_ws", "upload", "bystander"}


def test_session_close_needs_a_reason():
    SessionClose(session_id="s", reason="stop event")
    with pytest.raises(ValidationError):
        SessionClose(session_id="s")
