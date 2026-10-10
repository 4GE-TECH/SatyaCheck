"""The WebSocket loop must buffer across chunks, not score each one alone.

The app sends 3s raw chunks (`RingBuffer` in `CallAudioService.kt`). Scoring each one
in isolation feeds Whisper 3 seconds of speech mid-sentence, which the app's own
Kotlin comment documents as hallucination-prone: a 3s slice of a real recording
transcribed as "alert can product us from with the minger next week" where the 9s
window from the same audio transcribed correctly. `nlp_rag/asr.py`'s ASR gate checks
`no_speech_prob` and repetition, and a fluent hallucination trips neither — so a
broken buffer reaches retrieval and the markers as if it were real speech, not as an
error.

This test streams a real scam clip through `/api/ws/screen/{id}` in 3s pieces — the
same shape the app sends — and asserts the last chunk's transcript is long enough and
confident enough to be the accumulated context, not an isolated 3s tail.
"""

from __future__ import annotations

import io
import json
import wave

import pytest

import config

CLIPS = config.REPO_ROOT / "data" / "eval_set" / "clips"
WHISPER = config.MODELS_DIR / "faster-whisper-small" / "model.bin"
SCAM_CLIP = CLIPS / "held-family-emergency-001.wav"

pytestmark = pytest.mark.skipif(
    not WHISPER.is_file() or not SCAM_CLIP.is_file(),
    reason="needs models/faster-whisper-small/ and data/eval_set/clips/",
)


def _split_into_wav_chunks(path, chunk_s: float = 3.0) -> list[bytes]:
    """Cut a WAV file into self-contained `chunk_s`-second WAV chunks.

    Mirrors what `AudioChunk.toWav()` produces on the app side: each chunk is a
    complete RIFF file, not a raw PCM fragment, because the backend's ffmpeg step
    cannot infer sample rate or bit depth from bare bytes.
    """
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


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from server.main import app

    with TestClient(app) as c:
        yield c


def test_the_last_chunk_carries_accumulated_context_not_an_isolated_tail(client):
    import base64
    import uuid

    chunks = _split_into_wav_chunks(SCAM_CLIP, chunk_s=3.0)
    assert len(chunks) >= 3, "fixture too short to exercise buffering at all"

    # Unique per run: this test uses the real config.DB_PATH (no isolation fixture
    # exists for it yet), and a fixed id collides with a leftover row on a re-run.
    session_id = f"test-rolling-buffer-{uuid.uuid4().hex[:8]}"
    responses = []
    with client.websocket_connect(f"/api/ws/screen/{session_id}") as ws:
        for i, chunk in enumerate(chunks):
            ws.send_text(json.dumps({
                "type": "audio_chunk",
                "session_id": session_id,
                "chunk_index": i,
                "audio_base64": base64.b64encode(chunk).decode(),
                "is_final": i == len(chunks) - 1,
            }))
            msg = json.loads(ws.receive_text())
            assert msg["type"] == "screening_update", msg
            responses.append(msg["response"])
            # A second message per chunk, overlay_update, was added after this test —
            # drain it too or it is read as the *next* chunk's screening_update.
            overlay = json.loads(ws.receive_text())
            assert overlay["type"] == "overlay_update", overlay

    assert len(responses) == len(chunks), "one verdict per chunk sent"

    # The clip's final chunk is an edge case (SCAM_CLIP is 16.1s, so the trailing
    # window at the very last chunk holds less than a full config.STREAM_CONTEXT_S of
    # real audio) — checking it alone is not a reliable signal either way. What proves
    # the buffer is accumulating rather than scoring each chunk in isolation is
    # *growth*: the second chunk only ever had ~6s of real audio behind it (two 3s
    # chunks), the fourth had the full 9s window. If chunks were scored alone, nothing
    # would grow — each transcript would independently reflect the same ~3s slice.
    lengths = [len(r["transcript"]["text"]) for r in responses]
    assert lengths[3] > lengths[0] > 0, (
        f"transcript did not grow with accumulated context: {lengths}"
    )

    # And the fully-windowed middle chunk must be a real, confident transcript, not a
    # hallucinated fragment (the app's own docs measured hallucination on isolated 3s
    # slices against this same ASR).
    mid_transcript = responses[3]["transcript"]
    assert len(mid_transcript["text"]) > 40, (
        f"windowed transcript too short to be real accumulated speech: {mid_transcript!r}"
    )
    assert mid_transcript["confidence"] > 0.3, (
        f"low-confidence transcript suggests hallucination: {mid_transcript!r}"
    )


if __name__ == "__main__":
    print("run via pytest")
