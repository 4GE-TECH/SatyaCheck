"""Exotel Stream applet (unidirectional) messages -> C1 objects.

Exotel connects to us as a WebSocket client and sends JSON text frames: `connected`,
`start`, `media`, `stop`. Every behaviour below is from Exotel's own documentation as
researched for item 1 (quotes and URLs in the team's research notes):

  * envelope and event matrix, media.timestamp in ms from stream start, stop.reason
    'stopped' | 'callended'           developer.exotel.com/docs/agentstream/websocket-protocol
  * start: stream_sid, call_sid, account_sid, from, to, custom_parameters, media_format
                                      developer.exotel.com/docs/agentstream/stream-voicebot-applet
  * camelCase streamSid/callSid; "tolerate missing optional fields"
                                      github.com/exotel/Agent-Stream (AGENTSTREAM_WSS_PROTOCOL.md)

Where Exotel's pages disagree we do not guess — we branch on what the stream says and
log what we assumed:

  * encoding: base docs say raw s16le PCM; the newer extension guide says mu-law by
    default. Both are decoded, chosen by start.media_format.encoding. A missing encoding
    is read as raw PCM (the base docs) and logged; anything else is an ERROR and the
    call's media is dropped rather than decoded as noise.
  * sample rate: start.media_format.sample_rate, else the '?sample-rate=' on the URL,
    else config.EXOTEL_DEFAULT_SAMPLE_RATE (8000, the documented default). 8000, 16000
    and 24000 are documented; anything else is an ERROR.
  * the optional per-message 'track' field (extension guide only) is filtered by
    config.EXOTEL_TRACK; no field means accept.

Never raises (CLAUDE.md rule 5): malformed, hostile or out-of-order input is logged and
dropped, because silently absorbed input is indistinguishable from audio that was heard.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import logging
import re
import uuid
from typing import Optional, Union

import numpy as np

import config
from contracts import AudioFrame, AudioSource, CallerMetadata, SessionClose, SessionOpen

from acquisition.exotel.codec import StreamingResampler, mulaw_decode

log = logging.getLogger("satyacheck.acquisition.exotel")

TARGET_RATE = config.TARGET_SAMPLE_RATE
SUPPORTED_RATES = (8000, 16000, 24000)
_LINEAR = {"raw", "audio/x-raw", "slin", "pcm", "linear16", "s16le", "pcm_s16le", "audio/l16"}
# Seen live from the Stream applet: encoding "base64" — the payload wrapping, not a codec.
# Exotel's base docs and sample server treat that audio as raw s16le PCM.
_BASE64_WRAPPED_LINEAR = {"base64"}
_MULAW = {"mulaw", "ulaw", "audio/x-mulaw", "audio/x-ulaw", "audio/mulaw", "pcmu", "g711_ulaw"}

_SAFE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")


def safe_session_id(raw) -> str:
    """A session id that is always a plain folder name ([A-Za-z0-9][A-Za-z0-9_-]{0,127}).

    Exotel's ids are used as the database key, a log label and (on other paths) a folder
    name, so they are never trusted as given. A clean id is kept unchanged; anything
    else is sanitised and suffixed with a hash of the original so distinct raw ids stay
    distinct.
    """
    text = "" if raw is None else str(raw)
    if _SAFE.fullmatch(text):
        return text
    if not text.strip():
        return f"exotel-{uuid.uuid4().hex[:16]}"
    cleaned = re.sub(r"[^A-Za-z0-9_-]", "_", text)[:96].strip("_-") or "x"
    if not cleaned[0].isalnum():
        cleaned = "x" + cleaned
    digest = hashlib.sha256(text.encode("utf-8", "surrogatepass")).hexdigest()[:12]
    return f"{cleaned}-{digest}"


def _int(value) -> Optional[int]:
    """Exotel sends numbers as ints on some pages and strings on others."""
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, str) and value.strip().lstrip("-").isdigit():
        return int(value.strip())
    return None


def _first(d: dict, *keys):
    for k in keys:
        if isinstance(d, dict) and d.get(k) not in (None, ""):
            return d.get(k)
    return None


Output = Union[SessionOpen, AudioFrame, SessionClose]


class ExotelStreamDecoder:
    """One Exotel stream (one WebSocket connection). Not thread-safe."""

    def __init__(self, url_sample_rate=None) -> None:
        self.url_sample_rate = _int(url_sample_rate)
        self.session_id: Optional[str] = None
        self.closed = False
        self._drop_media = False
        self._linear = True
        self._resampler: Optional[StreamingResampler] = None
        self._carry = b""
        self._first_seq: Optional[int] = None
        self._last_seq: Optional[int] = None
        self._next_local = 0
        self._decoded = 0          # samples emitted at TARGET_RATE
        self._warned_before_start = False
        # What happened to this call's media, logged when it ends: a call whose every
        # message was dropped must not look like a call that sent nothing.
        self._media_seen = 0
        self._frames_out = 0
        self._dropped: dict[str, int] = {}

    def _drop(self, reason: str, first_warning: str) -> list:
        self._dropped[reason] = self._dropped.get(reason, 0) + 1
        if self._dropped[reason] == 1:
            log.warning(f"[{self.session_id}] exotel: {first_warning}")
        return []

    def _summary(self) -> None:
        dropped = " ".join(f"{k}={v}" for k, v in sorted(self._dropped.items())) or "none"
        log.info(f"[{self.session_id}] exotel: media summary: received={self._media_seen} "
                 f"decoded={self._frames_out} dropped: {dropped}")
        if self._media_seen == 0:
            log.warning(f"[{self.session_id}] exotel: the call ended with no media at all — check that "
                        f"the call flow keeps the call alive after the Stream applet (e.g. a Connect applet)")
        elif self._frames_out == 0:
            log.warning(f"[{self.session_id}] exotel: every media message was dropped ({dropped}); "
                        f"nothing was scored")

    # --- public -------------------------------------------------------------------------

    def feed(self, message) -> list[Output]:
        """One WebSocket text frame in; zero or more C1 objects out. Never raises."""
        try:
            msg = self._parse(message)
            if msg is None:
                return []
            event = msg["event"]
            if event == "connected":
                log.info("exotel: connected")
                return []
            if event == "start":
                return self._start(msg)
            if event == "media":
                return self._media(msg)
            if event == "stop":
                return self._stop(msg)
            log.info(f"exotel: ignoring event {event!r} (not part of the unidirectional Stream applet)")
            return []
        except Exception as e:  # noqa: BLE001 — a hostile frame must not end the call
            log.error(f"exotel: failed to handle a message: {type(e).__name__}: {e}")
            return []

    def end(self, reason: str) -> Optional[SessionClose]:
        """The socket ended. Closes the session once if it was open and not yet stopped."""
        if self.session_id is None or self.closed:
            return None
        self.closed = True
        self._summary()
        return SessionClose(session_id=self.session_id, reason=reason)

    # --- events -----------------------------------------------------------------------------

    def _parse(self, message) -> Optional[dict]:
        if isinstance(message, (bytes, bytearray)):
            try:
                message = bytes(message).decode("utf-8")
            except UnicodeDecodeError:
                log.warning("exotel: malformed message (binary, not UTF-8 JSON); ignored")
                return None
        if not isinstance(message, str):
            log.warning(f"exotel: malformed message of type {type(message).__name__}; ignored")
            return None
        try:
            msg = json.loads(message)
        except ValueError:
            log.warning(f"exotel: malformed JSON ({message[:60]!r}); ignored")
            return None
        if not isinstance(msg, dict) or not isinstance(msg.get("event"), str):
            log.warning("exotel: malformed message without a string 'event' field; ignored")
            return None
        return msg

    def _start(self, msg: dict) -> list[Output]:
        if self.session_id is not None:
            log.warning(f"[{self.session_id}] exotel: duplicate start ignored")
            return []
        start = msg.get("start")
        if not isinstance(start, dict):
            log.warning("exotel: start event without a start object; using what the envelope has")
            start = {}
        raw_id = _first(start, "stream_sid", "streamSid") or _first(msg, "stream_sid", "streamSid") \
            or _first(start, "call_sid", "callSid") or _first(msg, "call_sid", "callSid")
        self.session_id = safe_session_id(raw_id)
        claimed = _first(start, "from")
        context = CallerMetadata(claimed_number=str(claimed) if claimed else None,
                                 channel_type="telephony")

        media_format = start.get("media_format") or start.get("mediaFormat") or {}
        if not isinstance(media_format, dict):
            media_format = {}
        self._configure_audio(media_format)
        log.info(f"[{self.session_id}] exotel: stream started "
                 f"(call {safe_session_id(_first(start, 'call_sid', 'callSid')) if _first(start, 'call_sid', 'callSid') else '?'})")
        return [SessionOpen(session_id=self.session_id, source=AudioSource.EXOTEL,
                            caller_context=context)]

    def _configure_audio(self, media_format: dict) -> None:
        log.info(f"[{self.session_id}] exotel: media_format as sent: {media_format!r}")
        encoding = str(media_format.get("encoding") or "").strip().lower()
        base = encoding.split(";")[0].strip()
        if not base:
            log.info(f"[{self.session_id}] exotel: no media_format.encoding; assuming raw "
                     f"s16le PCM (Exotel base docs)")
            self._linear = True
        elif base in _LINEAR:
            self._linear = True
        elif base in _BASE64_WRAPPED_LINEAR:
            log.info(f"[{self.session_id}] exotel: encoding {encoding!r} names the payload wrapping; "
                     f"decoding as raw s16le PCM (Exotel base docs)")
            self._linear = True
        elif base in _MULAW:
            self._linear = False
        else:
            log.error(f"[{self.session_id}] exotel: unsupported encoding {encoding!r}; "
                      f"this call's audio will be dropped, not guessed")
            self._drop_media = True
            return

        rate = _int(media_format.get("sample_rate", media_format.get("sampleRate")))
        source = "media_format"
        if rate is None:
            rate, source = self.url_sample_rate, "the URL"
        if rate is None:
            rate, source = config.EXOTEL_DEFAULT_SAMPLE_RATE, "config default"
        if rate not in SUPPORTED_RATES:
            log.error(f"[{self.session_id}] exotel: unsupported sample rate {rate} (from {source}); "
                      f"documented rates are {SUPPORTED_RATES}; this call's audio will be dropped")
            self._drop_media = True
            return
        if not self._linear and rate != 8000:
            log.warning(f"[{self.session_id}] exotel: mu-law at {rate} Hz is unusual; decoding anyway")
        self._resampler = StreamingResampler(rate, TARGET_RATE)
        log.info(f"[{self.session_id}] exotel: {'s16le' if self._linear else 'mu-law'} at {rate} Hz "
                 f"(rate from {source})")

    def _media(self, msg: dict) -> list[Output]:
        if self.session_id is None:
            if not self._warned_before_start:
                log.warning("exotel: media before start; dropped")
                self._warned_before_start = True
            return []
        if self.closed:
            return []
        self._media_seen += 1
        if self._media_seen == 1:
            media_keys = sorted(msg["media"]) if isinstance(msg.get("media"), dict) else None
            log.info(f"[{self.session_id}] exotel: first media message: keys={sorted(msg)} "
                     f"media keys={media_keys} track={msg.get('track')!r}")
        if self._drop_media:
            self._dropped["format"] = self._dropped.get("format", 0) + 1
            return []
        track = msg.get("track")
        wanted = str(config.EXOTEL_TRACK).lower()
        if track is not None and wanted != "any" and str(track).lower() != wanted:
            log.debug(f"[{self.session_id}] exotel: dropping media for track {track!r} "
                      f"(EXOTEL_TRACK={wanted})")
            return self._drop("track", f"dropping media for track {track!r} (EXOTEL_TRACK={wanted}); "
                                       f"set EXOTEL_TRACK=any to accept every track")
        media = msg.get("media")
        if not isinstance(media, dict):
            log.warning(f"[{self.session_id}] exotel: media event without a media object; dropped")
            return []
        try:
            payload = base64.b64decode(media.get("payload") or "", validate=True)
        except (binascii.Error, ValueError, TypeError):
            log.warning(f"[{self.session_id}] exotel: media payload is not base64; dropped")
            return []

        seq = _int(_first(msg, "sequence_number", "sequenceNumber"))
        if seq is not None:
            if self._last_seq is not None and seq <= self._last_seq:
                log.warning(f"[{self.session_id}] exotel: out of order or duplicate media "
                            f"seq={seq} (last {self._last_seq}); dropped")
                return []
            if self._last_seq is not None and seq > self._last_seq + 1:
                log.warning(f"[{self.session_id}] exotel: sequence gap: {seq - self._last_seq - 1} "
                            f"media message(s) missing before seq={seq}")
            if self._first_seq is None:
                self._first_seq = seq
            self._last_seq = seq
            local = max(seq - self._first_seq, self._next_local)
        else:
            local = self._next_local

        pcm = self._decode(payload)
        if pcm.size == 0:
            return []
        timestamp_ms = _int(media.get("timestamp"))
        t_start = timestamp_ms / 1000.0 if timestamp_ms is not None and timestamp_ms >= 0 \
            else self._decoded / TARGET_RATE
        self._next_local = local + 1
        self._decoded += pcm.size
        self._frames_out += 1
        return [AudioFrame(session_id=self.session_id, seq=local, t_start_s=t_start,
                           pcm_s16le=pcm.astype("<i2").tobytes())]

    def _decode(self, payload: bytes) -> np.ndarray:
        if self._linear:
            data = self._carry + payload
            if len(data) % 2:
                self._carry, data = data[-1:], data[:-1]
            else:
                self._carry = b""
            samples = np.frombuffer(data, dtype="<i2")
        else:
            samples = mulaw_decode(payload)
        if samples.size == 0 or self._resampler is None:
            return np.zeros(0, dtype=np.int16)
        if self._resampler.identity:
            return samples.astype(np.int16)
        out = self._resampler.process(samples.astype(np.float64))
        return np.clip(np.round(out), -32768, 32767).astype(np.int16)

    def _stop(self, msg: dict) -> list[Output]:
        if self.session_id is None or self.closed:
            return []
        stop = msg.get("stop")
        reason = stop.get("reason") if isinstance(stop, dict) else None
        self.closed = True
        log.info(f"[{self.session_id}] exotel: stop ({reason or 'no reason given'})")
        self._summary()
        return [SessionClose(session_id=self.session_id,
                             reason=f"exotel stop: {reason or 'unspecified'}")]
