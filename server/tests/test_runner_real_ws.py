"""The real-model WebSocket tests, rerun with `config.USE_PIPELINE_RUNNER = True`.

`test_ws_rolling_buffer.py` and `test_overlay_update.py` run the per-chunk path as
they always have. The same test functions are collected again here with the runner
switched on, so both paths face the same real clips, real ECAPA, AASIST and Whisper.

One of them cannot hold on the runner path, by design rather than by defect — see
`test_runner_rolling_buffer_lockstep`. Its intent (context accumulates into the
transcript; the transcript is real speech, not a hallucinated tail) is re-asserted for
the runner's protocol in `test_runner_transcript_accumulates_across_the_call`.
"""

from __future__ import annotations

import base64
import json
import uuid

import pytest

import config
from server.tests import test_overlay_update as _overlay
from server.tests import test_ws_rolling_buffer as _rolling

pytestmark = _rolling.pytestmark


@pytest.fixture(autouse=True)
def pipeline_runner_on(monkeypatch):
    monkeypatch.setattr(config, "USE_PIPELINE_RUNNER", True)


client = _rolling.client
friend_enrolled = _overlay.friend_enrolled
isolated_db = _overlay.isolated_db

test_runner_a_spoken_scam_script_through_the_live_websocket_is_never_green = (
    _overlay.test_a_spoken_scam_script_through_the_live_websocket_is_never_green)
test_runner_a_genuine_benign_call_through_the_live_websocket_does_not_turn_red = (
    _overlay.test_a_genuine_benign_call_through_the_live_websocket_does_not_turn_red)


@pytest.mark.xfail(strict=True, reason=(
    "Per-chunk protocol expectation. The test reads one verdict per 3 s chunk in "
    "lockstep and requires the first (3 s of audio) to carry a transcript. The runner "
    "emits a verdict per 2 s window and never waits for ASR, and nlp_rag's "
    "StreamingTranscriber does not decode before STREAM_MIN_DECODE_S=9 s of audio, so "
    "the first windows abstain on text. Measured: lengths [0, 0, 0, 0, 0, 125]. "
    "Strict: if this ever passes, the runner started waiting on ASR."))
def test_runner_rolling_buffer_lockstep(client):
    _rolling.test_the_last_chunk_carries_accumulated_context_not_an_isolated_tail(client)


def _stream_all(client, path) -> list[dict]:
    """Send every 3 s chunk, then read until the server closes the socket."""
    from starlette.websockets import WebSocketDisconnect

    chunks = _rolling._split_into_wav_chunks(path, chunk_s=3.0)
    session_id = f"test-runner-real-{uuid.uuid4().hex[:8]}"
    messages = []
    with client.websocket_connect(f"/api/ws/screen/{session_id}") as ws:
        for i, chunk in enumerate(chunks):
            ws.send_text(json.dumps({
                "type": "audio_chunk", "session_id": session_id, "chunk_index": i,
                "audio_base64": base64.b64encode(chunk).decode(),
                "is_final": i == len(chunks) - 1,
            }))
        try:
            while True:
                messages.append(json.loads(ws.receive_text()))
        except WebSocketDisconnect:
            pass
    return messages


def test_runner_transcript_accumulates_across_the_call(client):
    messages = _stream_all(client, _rolling.SCAM_CLIP)
    updates = [m for m in messages if m["type"] == "screening_update"]
    overlays = [m for m in messages if m["type"] == "overlay_update"]

    # 16.1 s of audio: hop windows ending at 2, 4, ... 16 s, then the 16.1 s tail.
    assert [u["chunk_index"] for u in updates] == list(range(9)), [u["chunk_index"] for u in updates]
    assert len(overlays) == len(updates)
    assert [m["type"] for m in messages] == ["screening_update", "overlay_update"] * len(updates)

    lengths = [len(u["response"]["transcript"]["text"]) for u in updates]
    # The streaming transcript is cumulative and never regresses to empty.
    assert lengths == sorted(lengths), f"transcript regressed mid-call: {lengths}"
    final = updates[-1]["response"]["transcript"]
    assert len(final["text"]) > 40, f"final transcript is not the accumulated call: {final!r}"
    assert final["confidence"] > 0.3, f"low-confidence final transcript: {final!r}"
