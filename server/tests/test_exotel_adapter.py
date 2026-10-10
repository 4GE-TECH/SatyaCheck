"""Item 1: the Exotel Stream-applet adapter (unidirectional), end to end.

Exotel connects to us as a WebSocket client and sends JSON text frames: connected,
start, media, stop. `acquisition.exotel` turns them into C1 objects (SessionOpen,
AudioFrame at 16 kHz mono s16le, SessionClose); `acquisition.exotel.router` mounts that
on a WebSocket route, feeding an injected session runner.

Every message fixture below is built ONLY from shapes quoted in the research notes, from
Exotel's own docs:

  [P]  https://developer.exotel.com/docs/agentstream/websocket-protocol
       event matrix; media.timestamp = "ms from the start of the stream"; stop.reason
       'stopped' | 'callended'; raw PCM s16le mono, 8000 default, 8000/16000/24000.
  [A]  https://developer.exotel.com/docs/agentstream/stream-voicebot-applet
       start: {stream_sid, call_sid, account_sid, from, to, custom_parameters,
       media_format}; "SequenceNumber string sequence_number No".
  [S]  https://support.exotel.com/support/solutions/articles/3000108630-working-with-the-stream-and-voicebot-applet
       encoding 'raw' in one example and 'audio/x-raw' in another; a start key typed "to ".
  [G]  https://raw.githubusercontent.com/exotel/Agent-Stream/main/docs/AGENTSTREAM_WSS_PROTOCOL.md
       camelCase streamSid/callSid; "bridges should tolerate missing optional fields".
  [X]  https://developer.exotel.com/docs/agentstream/stream-voicebot-extension
       mu-law (G.711) 8 kHz default (conflicts with [P]); optional per-message 'track'.

Speaker and anti-spoof are fakes and the transcriber says nothing, so this pins what the
adapter does with Exotel's messages — not what the models say.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import re

import numpy as np
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from contracts import (
    AntiSpoofResult,
    AudioFrame,
    AudioSource,
    CallerMetadata,
    ScriptAnalysisResult,
    SessionClose,
    SessionOpen,
    SpeakerVerificationResult,
    TranscriptResult,
)

SR = 16_000
SAFE_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
FROM = "+919876543210"  # [A] start example


# --- reference G.711 mu-law, written independently of the implementation ------------

def _ref_ulaw(code: int) -> int:
    """ITU-T G.711 mu-law expansion, the textbook bit form."""
    u = ~code & 0xFF
    sign, exponent, mantissa = u & 0x80, (u >> 4) & 0x07, u & 0x0F
    magnitude = (((mantissa << 3) + 0x84) << exponent) - 0x84
    return -magnitude if sign else magnitude


_REF_TABLE = np.array([_ref_ulaw(c) for c in range(256)], dtype=np.int64)


def _ulaw_encode(pcm: np.ndarray) -> bytes:
    """Nearest mu-law code for each sample (test-only encoder)."""
    order = np.argsort(_REF_TABLE)
    values = _REF_TABLE[order]
    idx = np.clip(np.searchsorted(values, pcm.astype(np.int64)), 1, 255)
    left, right = values[idx - 1], values[idx]
    pick = np.where(np.abs(pcm - left) <= np.abs(right - pcm), idx - 1, idx)
    return order[pick].astype(np.uint8).tobytes()


# --- message fixtures ([P] [A] [S] [G]) ------------------------------------------------

def _connected() -> str:
    return json.dumps({"event": "connected"})  # [P]


def _start(stream_sid="stream-abc123", call_sid="call-xyz789", encoding="raw",
           sample_rate="8000", camel=False, seq=1, media_format=True, to_key="to") -> str:
    inner = {
        "stream_sid": stream_sid, "call_sid": call_sid, "account_sid": "acct-1",
        "from": FROM, to_key: "+911234567890", "custom_parameters": {"queuename": "premium"},
    }
    if media_format:
        inner["media_format"] = {"encoding": encoding, "sample_rate": sample_rate,
                                 "bit_rate": "128"}
    if camel:  # [G]
        inner["streamSid"] = inner.pop("stream_sid")
        inner["callSid"] = inner.pop("call_sid")
        inner["accountSid"] = inner.pop("account_sid")
        msg = {"event": "start", "sequenceNumber": seq, "streamSid": stream_sid, "start": inner}
    else:
        msg = {"event": "start", "sequence_number": seq, "stream_sid": stream_sid, "start": inner}
    return json.dumps(msg)


def _media(payload: bytes, seq, chunk, timestamp, stream_sid="stream-abc123",
           track=None, camel=False) -> str:
    media = {"chunk": chunk, "timestamp": timestamp,
             "payload": base64.b64encode(payload).decode()}
    msg = {"event": "media", "media": media}
    msg["sequenceNumber" if camel else "sequence_number"] = seq
    msg["streamSid" if camel else "stream_sid"] = stream_sid
    if track is not None:
        msg["track"] = track  # [X]
    return json.dumps(msg)


def _stop(seq, reason="callended", stream_sid="stream-abc123") -> str:
    return json.dumps({"event": "stop", "sequence_number": seq, "stream_sid": stream_sid,
                       "stop": {"call_sid": "call-xyz789", "account_sid": "acct-1",
                                "reason": reason}})  # [P]


def _tone(rate: int, seconds: float, freq: float = 1000.0, amp: float = 0.5,
          gated: bool = False) -> np.ndarray:
    t = np.arange(int(round(rate * seconds))) / rate
    x = amp * np.sin(2 * np.pi * freq * t)
    if gated:
        x = x * ((t % 0.5) < 0.4)
    return np.round(x * 32767).astype("<i2")


def _media_stream(pcm: bytes, rate: int, msg_ms: int, *, first_seq=2, stream_sid="stream-abc123",
                  bytes_per_sample=2, as_str=False, camel=False, track=None) -> list[str]:
    step = int(rate * msg_ms / 1000) * bytes_per_sample
    out = []
    for k, i in enumerate(range(0, len(pcm), step)):
        seq, chunk, ts = first_seq + k, k + 1, k * msg_ms
        if as_str:
            seq, chunk, ts = str(seq), str(chunk), str(ts)
        out.append(_media(pcm[i:i + step], seq, chunk, ts, stream_sid=stream_sid,
                          track=track, camel=camel))
    return out


def _frames(outputs) -> list[AudioFrame]:
    return [o for o in outputs if isinstance(o, AudioFrame)]


def _decode_all(messages, **kw):
    from acquisition.exotel import ExotelStreamDecoder

    dec = ExotelStreamDecoder(**kw)
    out = []
    for m in messages:
        out.extend(dec.feed(m))
    return dec, out


def _pcm(frames) -> np.ndarray:
    return np.frombuffer(b"".join(f.pcm_s16le for f in frames), dtype="<i2")


def _peak_and_db(x: np.ndarray, rate: int = SR) -> tuple[float, float]:
    x = x.astype(np.float64) / 32768.0
    x = x[len(x) // 10: -len(x) // 10]
    spec = np.abs(np.fft.rfft(x * np.hanning(len(x))))
    peak = float(np.fft.rfftfreq(len(x), 1 / rate)[int(np.argmax(spec))])
    return peak, float(20 * np.log10(np.sqrt(np.mean(x ** 2))))


# =====================================================================================
# Codec: G.711 mu-law and the streaming resampler
# =====================================================================================

def test_mulaw_known_code_points():
    from acquisition.exotel.codec import mulaw_decode

    got = mulaw_decode(bytes([0xFF, 0x7F, 0x00, 0x80]))
    assert got.dtype == np.int16
    assert got.tolist() == [0, 0, -32124, 32124]


def test_mulaw_matches_the_itu_formula_for_every_code():
    from acquisition.exotel.codec import mulaw_decode

    got = mulaw_decode(bytes(range(256))).astype(np.int64)
    assert np.array_equal(got, _REF_TABLE)
    # Sign symmetry of G.711: flipping the sign bit negates the value.
    assert np.array_equal(got[:128], -got[128:])


@pytest.mark.parametrize("rate", [8000, 24000])
def test_resampler_chunked_equals_whole(rate):
    from acquisition.exotel.codec import StreamingResampler

    rng = np.random.default_rng(7)
    x = rng.normal(0, 3000, size=rate * 2)
    whole = StreamingResampler(rate, SR).process(x)
    chunked_r = StreamingResampler(rate, SR)
    sizes = [1, 7, 160, 333, 800, 1, 2400]
    parts, i, k = [], 0, 0
    while i < len(x):
        n = sizes[k % len(sizes)]
        parts.append(chunked_r.process(x[i:i + n]))
        i, k = i + n, k + 1
    chunked = np.concatenate(parts)
    assert len(whole) == len(chunked) == len(x) * SR // rate
    assert np.max(np.abs(whole - chunked)) <= 1e-6


def test_resampler_16k_is_identity():
    from acquisition.exotel.codec import StreamingResampler

    x = np.arange(100, dtype=np.float64)
    assert np.array_equal(StreamingResampler(SR, SR).process(x), x)


def test_a_1khz_tone_at_8k_comes_out_at_16k_with_its_level():
    _, out = _decode_all([_start(sample_rate=8000)]
                         + _media_stream(_tone(8000, 2.0).tobytes(), 8000, 100))
    frames = _frames(out)
    pcm = _pcm(frames)
    assert len(pcm) == 2 * SR
    peak, db = _peak_and_db(pcm)
    assert abs(peak - 1000.0) <= 2.0, peak
    assert abs(db - 20 * np.log10(0.5 / np.sqrt(2))) <= 1.0, db


def test_a_1khz_tone_at_24k_comes_out_at_16k_with_its_level():
    _, out = _decode_all([_start(sample_rate="24000")]
                         + _media_stream(_tone(24000, 2.0).tobytes(), 24000, 100))
    pcm = _pcm(_frames(out))
    assert len(pcm) == 2 * SR
    peak, db = _peak_and_db(pcm)
    assert abs(peak - 1000.0) <= 2.0 and abs(db - 20 * np.log10(0.5 / np.sqrt(2))) <= 1.0


def test_16k_s16le_passes_through_bit_exact():
    pcm = _tone(SR, 1.0, freq=440.0).tobytes()
    _, out = _decode_all([_start(sample_rate=16000)] + _media_stream(pcm, SR, 20))
    assert b"".join(f.pcm_s16le for f in _frames(out)) == pcm


@pytest.mark.parametrize("encoding", ["mulaw", "audio/x-mulaw", "ulaw", "audio/x-mulaw;rate=8000"])
def test_mulaw_payloads_decode_to_the_tone(encoding):
    tone = _tone(8000, 2.0)
    law = _ulaw_encode(tone)
    _, out = _decode_all([_start(encoding=encoding, sample_rate=8000)]
                         + _media_stream(law, 8000, 100, bytes_per_sample=1))
    pcm = _pcm(_frames(out))
    assert len(pcm) == 2 * SR
    peak, db = _peak_and_db(pcm)
    assert abs(peak - 1000.0) <= 2.0 and abs(db - 20 * np.log10(0.5 / np.sqrt(2))) <= 1.0


@pytest.mark.parametrize("encoding", ["raw", "audio/x-raw", "slin", "pcm", "RAW"])
def test_linear_pcm_encodings_are_accepted(encoding):
    _, out = _decode_all([_start(encoding=encoding, sample_rate=16000)]
                         + _media_stream(_tone(SR, 0.2).tobytes(), SR, 100))
    assert len(_frames(out)) == 2


# =====================================================================================
# Decoder: messages -> C1 objects
# =====================================================================================

def test_start_opens_an_exotel_session_with_telephony_caller_context():
    _, out = _decode_all([_connected(), _start()])
    assert len(out) == 1 and isinstance(out[0], SessionOpen)
    opened = out[0]
    assert opened.source == AudioSource.EXOTEL
    assert opened.caller_context == CallerMetadata(claimed_number=FROM, channel_type="telephony")
    assert SAFE_ID.fullmatch(opened.session_id)
    assert "stream-abc123" in opened.session_id


def test_camel_case_ids_and_a_padded_to_key_are_tolerated():
    dec, out = _decode_all([_start(camel=True, to_key="to ")]
                           + _media_stream(_tone(8000, 0.2).tobytes(), 8000, 100, camel=True))
    opened = out[0]
    assert isinstance(opened, SessionOpen) and "stream-abc123" in opened.session_id
    assert opened.caller_context.claimed_number == FROM
    assert len(_frames(out)) == 2


def test_string_sequence_numbers_chunks_and_timestamps():
    _, out = _decode_all([_start(seq="1")]
                         + _media_stream(_tone(8000, 0.5).tobytes(), 8000, 100, as_str=True))
    frames = _frames(out)
    assert [f.seq for f in frames] == [0, 1, 2, 3, 4]
    assert [f.t_start_s for f in frames] == pytest.approx([0.0, 0.1, 0.2, 0.3, 0.4])
    assert all(len(f.pcm_s16le) == 2 * 1600 for f in frames)


def test_frames_are_contiguous_from_zero_whatever_exotel_numbered_them():
    # Exotel numbers every message (start is 1); media starting at 2 is not a gap.
    _, out = _decode_all([_start()] + _media_stream(_tone(8000, 0.3).tobytes(), 8000, 100,
                                                    first_seq=2))
    assert [f.seq for f in _frames(out)] == [0, 1, 2]


def test_malformed_json_is_logged_and_ignored(caplog):
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        dec, out = _decode_all(["{not json", "[1, 2]", json.dumps({"no_event": 1}), _start()])
    assert len(out) == 1 and isinstance(out[0], SessionOpen)
    msgs = " ".join(r.getMessage() for r in caplog.records)
    assert "malformed" in msgs.lower() and "event" in msgs.lower()


def test_unknown_events_are_logged_and_ignored(caplog):
    with caplog.at_level(logging.INFO, logger="satyacheck"):
        _, out = _decode_all([_start(), json.dumps({"event": "teleport", "x": 1}),
                              json.dumps({"event": "dtmf", "dtmf": {"digit": "1"}})])
    assert len(out) == 1
    assert any("teleport" in r.getMessage() for r in caplog.records)


def test_feed_never_raises_on_hostile_input():
    from acquisition.exotel import ExotelStreamDecoder

    dec = ExotelStreamDecoder()
    for junk in [None, 5, b"\xff\xfe", "", "null", json.dumps({"event": None}),
                 json.dumps({"event": "start", "start": "nope"}),
                 json.dumps({"event": "media", "media": {"payload": "!!!notb64"}}),
                 json.dumps({"event": "media", "media": None}),
                 json.dumps({"event": "stop", "stop": 7})]:
        assert isinstance(dec.feed(junk), list)


def test_an_unknown_encoding_is_an_error_naming_it_and_media_is_dropped(caplog):
    with caplog.at_level(logging.ERROR, logger="satyacheck"):
        _, out = _decode_all([_start(encoding="opus")]
                             + _media_stream(_tone(8000, 0.3).tobytes(), 8000, 100))
    assert isinstance(out[0], SessionOpen)  # the call is still a session
    assert _frames(out) == []
    errors = [r for r in caplog.records if r.levelno >= logging.ERROR]
    assert errors and any("opus" in r.getMessage() for r in errors)


def test_an_unsupported_sample_rate_is_an_error_and_media_is_dropped(caplog):
    with caplog.at_level(logging.ERROR, logger="satyacheck"):
        _, out = _decode_all([_start(sample_rate="11025")]
                             + _media_stream(_tone(11025, 0.3).tobytes(), 11025, 100))
    assert _frames(out) == []
    assert any("11025" in r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR)


def test_sample_rate_falls_back_to_the_url_then_the_default():
    tone16 = _tone(SR, 0.2).tobytes()
    _, out = _decode_all([_start(media_format=False)] + _media_stream(tone16, SR, 100),
                         url_sample_rate="16000")
    assert b"".join(f.pcm_s16le for f in _frames(out)) == tone16  # 16 kHz: passthrough
    _, out = _decode_all([_start(media_format=False)]
                         + _media_stream(_tone(8000, 0.2).tobytes(), 8000, 100))
    assert config.EXOTEL_DEFAULT_SAMPLE_RATE == 8000
    assert len(_pcm(_frames(out))) == int(0.2 * SR)  # read as 8 kHz, upsampled


def test_track_filter(monkeypatch, caplog):
    tone = _tone(8000, 0.2).tobytes()
    monkeypatch.setattr(config, "EXOTEL_TRACK", "inbound")
    with caplog.at_level(logging.DEBUG, logger="satyacheck"):
        _, out = _decode_all([_start()] + _media_stream(tone, 8000, 100, track="outbound")
                             + _media_stream(tone, 8000, 100, track="inbound", first_seq=10)
                             + _media_stream(tone, 8000, 100, first_seq=20))
    assert len(_frames(out)) == 4  # 2 inbound + 2 with no track field
    assert any("outbound" in r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG)
    monkeypatch.setattr(config, "EXOTEL_TRACK", "any")
    _, out = _decode_all([_start()] + _media_stream(tone, 8000, 100, track="outbound"))
    assert len(_frames(out)) == 2


def test_a_sequence_gap_is_logged_and_the_frame_lands_at_its_timestamp(caplog):
    tone = _tone(8000, 1.0).tobytes()
    msgs = _media_stream(tone, 8000, 100)
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        _, out = _decode_all([_start()] + msgs[:3] + msgs[6:])  # lose 3 media messages
    frames = _frames(out)
    assert [f.seq for f in frames[:3]] == [0, 1, 2]
    assert frames[3].seq > 3, "the gap must reach the buffer as a seq jump"
    assert frames[3].t_start_s == pytest.approx(0.6)
    assert any("gap" in r.getMessage().lower() for r in caplog.records)


def test_out_of_order_and_duplicate_media_are_dropped_and_logged(caplog):
    msgs = _media_stream(_tone(8000, 0.5).tobytes(), 8000, 100)
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        _, out = _decode_all([_start()] + [msgs[0], msgs[2], msgs[1], msgs[2], msgs[3]])
    frames = _frames(out)
    assert [f.seq for f in frames] == sorted({f.seq for f in frames})
    assert len(frames) == 3  # 0, 2, 3 — the late 1 and the repeated 2 are dropped
    assert any("out of order" in r.getMessage().lower() for r in caplog.records)


def test_media_before_start_is_dropped_and_logged(caplog):
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        _, out = _decode_all(_media_stream(_tone(8000, 0.2).tobytes(), 8000, 100))
    assert out == []
    assert any("before start" in r.getMessage().lower() for r in caplog.records)


def test_stop_closes_with_the_reason_and_a_second_close_is_not_emitted():
    from acquisition.exotel import ExotelStreamDecoder

    dec = ExotelStreamDecoder()
    opened = dec.feed(_start())[0]
    closes = dec.feed(_stop(9, reason="stopped"))
    assert len(closes) == 1 and isinstance(closes[0], SessionClose)
    assert closes[0].session_id == opened.session_id and "stopped" in closes[0].reason
    assert dec.end("socket disconnected") is None
    assert dec.feed(_stop(10)) == []


def test_end_without_stop_closes_once():
    from acquisition.exotel import ExotelStreamDecoder

    dec = ExotelStreamDecoder()
    dec.feed(_start())
    close = dec.end("socket disconnected (code 1006)")
    assert isinstance(close, SessionClose) and "1006" in close.reason
    assert dec.end("again") is None
    assert ExotelStreamDecoder().end("never started") is None


@pytest.mark.parametrize("raw", [
    "..\\..\\evil", "../../etc/passwd", "a/b\\c:d*e?f", "  ", "\x00\x01",
    "x" * 500, "-leading-dash", "MZ00ff12ab34cd56ef7890",
])
def test_session_ids_are_always_plain_names(raw):
    from acquisition.exotel import safe_session_id

    sid = safe_session_id(raw)
    assert SAFE_ID.fullmatch(sid), sid
    assert "/" not in sid and "\\" not in sid and ".." not in sid


def test_distinct_unsafe_ids_stay_distinct_and_missing_ids_get_one():
    from acquisition.exotel import safe_session_id

    assert safe_session_id("a/b") != safe_session_id("a\\b")
    assert safe_session_id("MZ123") == safe_session_id("MZ123")
    _, out = _decode_all([json.dumps({"event": "start", "start": {"from": FROM}})])
    assert SAFE_ID.fullmatch(out[0].session_id)


def test_the_call_sid_is_used_when_there_is_no_stream_sid():
    _, out = _decode_all([json.dumps({"event": "start", "start": {"call_sid": "CA77", "from": FROM}})])
    assert "CA77" in out[0].session_id


def test_odd_byte_payloads_carry_the_half_sample_to_the_next_message():
    pcm = _tone(SR, 0.1).tobytes()
    cut = 1001
    msgs = [_start(sample_rate=16000), _media(pcm[:cut], 2, 1, 0), _media(pcm[cut:], 3, 2, 31)]
    _, out = _decode_all(msgs)
    assert b"".join(f.pcm_s16le for f in _frames(out)) == pcm


# =====================================================================================
# Router: the WebSocket route, auth, and the session runner it feeds
# =====================================================================================

class _NoText:
    def push(self, chunk, sample_rate=SR):
        return TranscriptResult.empty()

    def flush(self):
        return TranscriptResult.empty()


class _Recorder:
    name = "recorder"

    def __init__(self):
        self.events = []

    async def deliver(self, event):
        self.events.append(event)


@pytest.fixture
def db_factory(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'exotel.db'}")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


@pytest.fixture
def branches(monkeypatch):
    import server.orchestrator as orch

    monkeypatch.setattr(config, "USE_REAL_SPEAKER", True)
    monkeypatch.setattr(config, "USE_REAL_SPOOF", True)
    monkeypatch.setattr(orch, "_real_speaker_branch", lambda p, owner_id=None: SpeakerVerificationResult.neutral())
    monkeypatch.setattr(orch, "_real_spoof_branch",
                        lambda p: AntiSpoofResult(risk=0.2, details={"available": True}))
    monkeypatch.setattr(config, "ESCALATION_PERSISTENCE_N", 1)


class _FakeRunner:
    """Records what the route hands the runner; scores nothing."""

    def __init__(self):
        self.opened, self.frames, self.closed = [], [], []

    async def open(self, msg):
        self.opened.append(msg)

    async def push(self, frame, score=True):
        self.frames.append(frame)
        return []

    async def close(self, msg):
        self.closed.append(msg)
        return []


@pytest.fixture
def auth(monkeypatch):
    monkeypatch.setattr(config, "EXOTEL_BASIC_USER", "exo-key")
    monkeypatch.setattr(config, "EXOTEL_BASIC_PASS", "s3cret-token")
    monkeypatch.setattr(config, "EXOTEL_ALLOWED_IPS", [])
    monkeypatch.setattr(config, "EXOTEL_ALLOW_UNAUTHENTICATED", False)
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", False)


def _basic(user="exo-key", password="s3cret-token") -> dict:
    token = base64.b64encode(f"{user}:{password}".encode()).decode()
    return {"authorization": f"Basic {token}"}


def _app(runner_factory):
    from fastapi import FastAPI

    from acquisition.api import build_exotel_router

    app = FastAPI()
    app.include_router(build_exotel_router(runner_factory))
    return app


def _client(runner_factory):
    from fastapi.testclient import TestClient

    return TestClient(_app(runner_factory))


def _run_call(client, messages, headers=None, query=""):
    """Send every message, then wait for the server to close (it does on 'stop')."""
    # `headers={}` means "send no Authorization header" — `headers or _basic()` would
    # silently turn it into valid credentials.
    with client.websocket_connect(config.EXOTEL_WS_PATH + query,
                                  headers=_basic() if headers is None else headers) as ws:
        for m in messages:
            ws.send_text(m)
        return ws.receive()


def _real_runner_factory(db_factory, made):
    from server.pipeline.dispatcher import Dispatcher
    from server.pipeline.runner import SessionRunner

    def factory():
        rec = _Recorder()
        runner = SessionRunner(dispatcher=Dispatcher([rec]), session_factory=db_factory,
                               transcriber_factory=_NoText,
                               analyze=lambda t: ScriptAnalysisResult.neutral())
        made.append((runner, rec))
        return runner

    return factory


def test_a_full_exotel_call_produces_verdicts_and_one_final(auth, branches, db_factory):
    made = []
    client = _client(_real_runner_factory(db_factory, made))
    pcm = _tone(8000, 7.0, freq=220.0, amp=0.3, gated=True).tobytes()
    media = _media_stream(pcm, 8000, 100)
    reply = _run_call(client, [_connected(), _start()] + media + [_stop(len(media) + 2)])
    # Unidirectional: the only thing the server ever sends is the close.
    assert reply["type"] == "websocket.close", reply
    (runner, rec), = made
    events = rec.events
    # 7 s of audio sent as fast as the socket allows, i.e. faster than real time: the route
    # scores the newest window and buffers the backlog (it would score windows at 2, 4 and
    # 6 s if the audio arrived in real time), then the 7 s tail as the one final verdict.
    assert 2 <= len(events) <= 4
    assert [e.is_final for e in events][-1] is True and sum(e.is_final for e in events) == 1
    assert all(SAFE_ID.fullmatch(e.session_id) and "stream-abc123" in e.session_id
               for e in events)
    assert all(e.response.caller_context == CallerMetadata(claimed_number=FROM,
                                                           channel_type="telephony")
               for e in events)


def test_the_route_closes_the_session_on_stop_with_the_reason(auth):
    fake = _FakeRunner()
    client = _client(lambda: fake)
    media = _media_stream(_tone(8000, 0.5).tobytes(), 8000, 100)
    _run_call(client, [_connected(), _start()] + media + [_stop(9, reason="stopped")])
    assert len(fake.opened) == 1 and fake.opened[0].source == AudioSource.EXOTEL
    assert len(fake.frames) == 5
    assert len(fake.closed) == 1 and "stopped" in fake.closed[0].reason


def test_a_socket_drop_without_stop_still_closes_the_session(auth):
    fake = _FakeRunner()
    client = _client(lambda: fake)
    with client.websocket_connect(config.EXOTEL_WS_PATH, headers=_basic()) as ws:
        ws.send_text(_start())
        for m in _media_stream(_tone(8000, 0.3).tobytes(), 8000, 100):
            ws.send_text(m)
    assert len(fake.closed) == 1
    assert "disconnect" in fake.closed[0].reason


def test_the_url_sample_rate_reaches_the_decoder(auth):
    fake = _FakeRunner()
    client = _client(lambda: fake)
    tone16 = _tone(SR, 0.2).tobytes()
    _run_call(client, [_start(media_format=False)] + _media_stream(tone16, SR, 100)
              + [_stop(5)], query="?sample-rate=16000")
    assert b"".join(f.pcm_s16le for f in fake.frames) == tone16


def test_unconfigured_credentials_refuse_everything_and_say_how(monkeypatch, caplog):
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setattr(config, "EXOTEL_BASIC_USER", "")
    monkeypatch.setattr(config, "EXOTEL_BASIC_PASS", "")
    monkeypatch.setattr(config, "EXOTEL_ALLOWED_IPS", [])
    monkeypatch.setattr(config, "EXOTEL_ALLOW_UNAUTHENTICATED", False)
    fake = _FakeRunner()
    client = _client(lambda: fake)
    with caplog.at_level(logging.ERROR, logger="satyacheck"):
        for _ in range(2):
            with pytest.raises(WebSocketDisconnect) as exc:
                _run_call(client, [_start()], headers=_basic())
            assert exc.value.code == 1008
    errors = [r.getMessage() for r in caplog.records if r.levelno >= logging.ERROR]
    explains = [m for m in errors if "EXOTEL_BASIC_USER" in m]
    assert len(explains) == 1, "explain the missing configuration once, not per call"
    assert fake.opened == []


def test_wrong_credentials_are_refused_and_logged_without_the_secret(auth, caplog):
    from starlette.websockets import WebSocketDisconnect

    fake = _FakeRunner()
    client = _client(lambda: fake)
    with caplog.at_level(logging.DEBUG, logger="satyacheck"):
        for headers in [_basic(password="wrong-pass"), _basic(user="nobody"), {},
                        {"authorization": "Bearer abc"}, {"authorization": "Basic !!!"}]:
            with pytest.raises(WebSocketDisconnect) as exc:
                _run_call(client, [_start()], headers=headers)
            assert exc.value.code == 1008
    assert fake.opened == []
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "refused" in logged.lower()
    for secret in ("s3cret-token", "wrong-pass", "exo-key"):
        assert secret not in logged


def test_right_credentials_are_accepted_and_never_logged(auth, caplog):
    fake = _FakeRunner()
    client = _client(lambda: fake)
    with caplog.at_level(logging.DEBUG, logger="satyacheck"):
        _run_call(client, [_start(), _stop(2)])
    assert len(fake.opened) == 1
    logged = " ".join(r.getMessage() for r in caplog.records)
    assert "s3cret-token" not in logged and base64.b64encode(b"exo-key:s3cret-token").decode() not in logged


def test_an_ip_outside_the_allowlist_is_refused(auth, monkeypatch, caplog):
    from starlette.websockets import WebSocketDisconnect

    monkeypatch.setattr(config, "EXOTEL_ALLOWED_IPS", ["10.20.30.0/24"])
    fake = _FakeRunner()
    client = _client(lambda: fake)
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        with pytest.raises(WebSocketDisconnect) as exc:
            _run_call(client, [_start()])
    assert exc.value.code == 1008 and fake.opened == []
    assert any("allowlist" in r.getMessage().lower() for r in caplog.records)
    # The TestClient's peer is named "testclient"; allow it by name and it is accepted.
    monkeypatch.setattr(config, "EXOTEL_ALLOWED_IPS", ["10.20.30.0/24", "testclient"])
    _run_call(client, [_start(), _stop(2)])
    assert len(fake.opened) == 1


def test_unauthenticated_mode_is_explicit_opt_in(monkeypatch, caplog):
    monkeypatch.setattr(config, "EXOTEL_BASIC_USER", "")
    monkeypatch.setattr(config, "EXOTEL_BASIC_PASS", "")
    monkeypatch.setattr(config, "EXOTEL_ALLOWED_IPS", [])
    monkeypatch.setattr(config, "EXOTEL_ALLOW_UNAUTHENTICATED", True)
    fake = _FakeRunner()
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        _run_call(_client(lambda: fake), [_start(), _stop(2)], headers={})
    assert len(fake.opened) == 1
    assert any("unauthenticated" in r.getMessage().lower() for r in caplog.records)


def test_a_silent_exotel_stream_is_called_silent_by_the_runner(auth, branches, db_factory, caplog):
    made = []
    client = _client(_real_runner_factory(db_factory, made))
    zeros = bytes(2 * 8000 * 5)  # 5 s of s16 digital zero at 8 kHz
    media = _media_stream(zeros, 8000, 100)
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        _run_call(client, [_start()] + media + [_stop(len(media) + 2)])
    silent = [r for r in caplog.records if "stream silent" in r.getMessage()]
    assert len(silent) == 1 and "source=exotel" in silent[0].getMessage()
    (_, rec), = made
    assert rec.events and rec.events[-1].is_final


def test_mulaw_digital_silence_is_also_called_silent(auth, branches, db_factory, caplog):
    made = []
    client = _client(_real_runner_factory(db_factory, made))
    media = _media_stream(b"\xff" * 8000 * 5, 8000, 100, bytes_per_sample=1)
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        _run_call(client, [_start(encoding="mulaw")] + media + [_stop(len(media) + 2)])
    assert [r for r in caplog.records if "stream silent" in r.getMessage()]


def test_hostile_stream_sid_writes_nothing_under_data_sessions(auth, branches, db_factory,
                                                                monkeypatch, tmp_path):
    # This path does not retain audio at all (RETAIN_SESSION_AUDIO is the app path's
    # enrol-from-a-call aid); the id is sanitised regardless, because it is also the
    # database key and a log label.
    monkeypatch.setattr(config, "RETAIN_SESSION_AUDIO", True)
    monkeypatch.setattr(config, "DATA_DIR", tmp_path / "data")
    made = []
    client = _client(_real_runner_factory(db_factory, made))
    sid = "..\\..\\..\\evil"
    media = _media_stream(_tone(8000, 3.0, gated=True).tobytes(), 8000, 100, stream_sid=sid)
    _run_call(client, [_start(stream_sid=sid)] + media + [_stop(40, stream_sid=sid)])
    (_, rec), = made
    assert rec.events and all(SAFE_ID.fullmatch(e.session_id) for e in rec.events)
    assert not (tmp_path / "data" / "sessions").exists()
    assert not list(tmp_path.parent.glob("evil*"))


# --- mounting ------------------------------------------------------------------------

def test_the_route_is_not_mounted_when_the_flag_is_off(monkeypatch):
    from fastapi import FastAPI

    import server.main

    assert config.ENABLE_EXOTEL is False, "ENABLE_EXOTEL must default to off"
    paths = {getattr(r, "path", None) for r in server.main.app.routes}
    assert config.EXOTEL_WS_PATH not in paths
    app = FastAPI()
    assert server.main.mount_exotel(app) is False
    assert config.EXOTEL_WS_PATH not in {getattr(r, "path", None) for r in app.routes}


def test_the_route_is_mounted_when_the_flag_is_on(monkeypatch, auth):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    import server.main

    monkeypatch.setattr(config, "ENABLE_EXOTEL", True)
    fake = _FakeRunner()
    app = FastAPI()
    assert server.main.mount_exotel(app, runner_factory=lambda: fake) is True
    assert config.EXOTEL_WS_PATH in {getattr(r, "path", None) for r in app.routes}
    _run_call(TestClient(app), [_start(), _stop(2)])
    assert len(fake.opened) == 1


def test_the_servers_exotel_runner_has_no_app_socket_sink():
    import server.main

    runner = server.main._exotel_runner()
    names = [s.name for s in runner.dispatcher.sinks]
    assert "app_overlay" not in names
    assert {"guardian", "report"} <= set(names)


# =====================================================================================
# Caller context reaches every dispatched response, and never moves the score
# =====================================================================================

def _runner_events(db_factory, ctx, sid):
    from server.pipeline.dispatcher import Dispatcher
    from server.pipeline.runner import SessionRunner

    rec = _Recorder()
    runner = SessionRunner(dispatcher=Dispatcher([rec]), session_factory=db_factory,
                           transcriber_factory=_NoText,
                           analyze=lambda t: ScriptAnalysisResult(risk=0.4,
                                                                  details={"available": True}))
    pcm = _tone(SR, 5.0, freq=220.0, amp=0.3, gated=True).tobytes()

    async def go():
        await runner.open(SessionOpen(session_id=sid, source=AudioSource.EXOTEL,
                                      caller_context=ctx))
        for k, i in enumerate(range(0, len(pcm), 3200)):
            await runner.push(AudioFrame(session_id=sid, seq=k, t_start_s=k * 0.1,
                                         pcm_s16le=pcm[i:i + 3200]))
        await runner.close(SessionClose(session_id=sid, reason="test"))

    asyncio.run(go())
    return rec.events


def test_caller_context_reaches_every_dispatched_response(branches, db_factory):
    ctx = CallerMetadata(claimed_number=FROM, channel_type="telephony")
    events = _runner_events(db_factory, ctx, "ctx-1")
    assert len(events) >= 3 and events[-1].is_final
    assert all(e.response.caller_context == ctx for e in events)


def test_caller_context_never_changes_the_fused_risk(branches, db_factory):
    variants = [None,
                CallerMetadata(claimed_number=FROM, channel_type="telephony"),
                CallerMetadata(claimed_number="+910000000000", claimed_name="HDFC Bank",
                               claimed_identity="p-1", channel_type="telephony")]
    runs = [_runner_events(db_factory, c, f"ctx-inv-{k}") for k, c in enumerate(variants)]
    fused = [[(e.response.fusion.risk_score, e.response.fusion.band, e.response.fusion.weights_used)
              for e in run] for run in runs]
    assert fused[0] and all(f == fused[0] for f in fused[1:])
    assert any(e.response.fusion.band.value != "insufficient" for e in runs[0]), \
        "the invariance must be checked on scored windows, not only insufficient ones"


# --- a call where every media message is dropped must say so, loudly ----------------------------
# Seen live: three Exotel calls opened and stopped with zero scored audio, and the only
# drop path that logs at DEBUG (track mismatch) made that invisible.

def test_a_track_mismatch_warns_once_with_the_value_exotel_sent(monkeypatch, caplog):
    monkeypatch.setattr(config, "EXOTEL_TRACK", "inbound")
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        _decode_all([_start()] + _media_stream(_tone(8000, 0.5).tobytes(), 8000, 100, track="both"))
    warnings = [r.getMessage() for r in caplog.records if "track" in r.getMessage()]
    assert len(warnings) == 1, warnings
    assert "'both'" in warnings[0] and "EXOTEL_TRACK" in warnings[0]


def test_the_end_of_a_call_logs_what_happened_to_its_media(monkeypatch, caplog):
    monkeypatch.setattr(config, "EXOTEL_TRACK", "inbound")
    msgs = ([_start()] + _media_stream(_tone(8000, 0.3).tobytes(), 8000, 100)
            + _media_stream(_tone(8000, 0.2).tobytes(), 8000, 100, track="outbound", first_seq=10)
            + [_stop(30)])
    with caplog.at_level(logging.INFO, logger="satyacheck"):
        _decode_all(msgs)
    summary = [r.getMessage() for r in caplog.records if "media summary" in r.getMessage()]
    assert len(summary) == 1
    assert "received=5" in summary[0] and "decoded=3" in summary[0] and "track=2" in summary[0]


def test_a_call_with_no_media_at_all_warns_at_the_end(caplog):
    with caplog.at_level(logging.WARNING, logger="satyacheck"):
        _decode_all([_connected(), _start(), _stop(2)])
    assert any("no media" in r.getMessage().lower() for r in caplog.records if r.levelno >= logging.WARNING)


def test_encoding_base64_is_base64_wrapped_linear_pcm():
    """Seen live from Exotel's Stream applet: media_format.encoding == "base64". That names
    the payload wrapping, not the codec; Exotel's base docs and sample server treat the
    audio as raw s16le PCM, so it must decode as such rather than drop the call."""
    pcm = _tone(SR, 0.5, freq=440.0).tobytes()
    _, out = _decode_all([_start(encoding="base64", sample_rate=16000)] + _media_stream(pcm, SR, 100))
    assert b"".join(f.pcm_s16le for f in _frames(out)) == pcm


def test_the_first_media_message_shape_is_logged_once(caplog):
    """So a live call shows whether Exotel tags media with a track (caller vs victim)."""
    with caplog.at_level(logging.INFO, logger="satyacheck"):
        _decode_all([_start()] + _media_stream(_tone(8000, 0.3).tobytes(), 8000, 100, track="inbound"))
    shape = [r.getMessage() for r in caplog.records if "first media message" in r.getMessage()]
    assert len(shape) == 1 and "track='inbound'" in shape[0]


def test_a_slow_runner_never_loses_the_end_of_the_call(auth):
    """Seen live: scoring slower than real time blocked the socket reader, the backlog was
    discarded at hang-up, and the last ~20 s of the call were never heard. The route must
    keep reading while scoring catches up, deliver every frame, and close only after them."""
    import time as _time

    class SlowRunner(_FakeRunner):
        def __init__(self):
            super().__init__()
            self.scored = 0

        async def push(self, frame, score=True):
            self.frames.append(frame)
            if score:
                self.scored += 1
                await asyncio.sleep(0.05)   # slower than the 20 ms of audio per frame
            return []

    slow = SlowRunner()
    client = _client(lambda: slow)
    media = _media_stream(_tone(8000, 6.0).tobytes(), 8000, 20)   # 300 frames
    started = _time.monotonic()
    _run_call(client, [_connected(), _start()] + media + [_stop(400)])
    assert len(slow.frames) == 300, "every frame reaches the runner"
    assert len(slow.closed) == 1
    assert slow.scored < 300, "backlog frames are buffered, not each scored"
    assert slow.frames[-1].seq == 299
    assert _time.monotonic() - started < 300 * 0.05, "the route did not score every frame serially"
