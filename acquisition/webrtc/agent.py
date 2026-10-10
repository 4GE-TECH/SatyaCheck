"""The screening agent for one app-to-app call (LiveKit).

The agent joins the call's room as a participant that may subscribe and publish data,
never media (token grants: server/webrtc_screening.py). It is visible, so clients can verify
that verdicts come from it and see it leave; they keep it out of the call UI by identity. For each of the two voices:

  * it screens a voice only once the *other* person (the listener) is bound to the call:
    a caller talking before anyone has joined is heard by nobody, so it is not screened;
  * it asks LiveKit for 16 kHz mono and feeds `AudioFrame`s through a `StreamSession`
    (the same reader/consumer split Exotel uses) into a runner built by server/;
  * a phone that drops and rejoins resumes the same session (same id, same timeline);
  * verdicts about a voice go to its listener only, as data messages on VERDICT_TOPIC.

Everything about *what* is sent (alerts, bands, coverage, packet size) is server/'s
(`voice_factory` hooks, server/webrtc_screening.py). acquisition/ never imports server/.

If the agent itself loses the room while the phones keep talking, that stretch was not
screened: listeners are told "screening unavailable" when possible, and on reconnect the
outage is reported as unscreened time. If the agent leaves for good, clients see its
participant disconnect and must show screening as unavailable (webrtc/BACKEND_API.md).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from typing import Awaitable, Callable, Optional, Protocol

from contracts import AudioSource, SessionOpen

from acquisition._stream_session import StreamSession
from acquisition.webrtc.frames import RATE, FrameAssembler

log = logging.getLogger("satyacheck.acquisition.webrtc")

VERDICT_TOPIC = "satyacheck.verdict"

Publish = Callable[[str, dict], Awaitable[None]]


class VoiceHooks(Protocol):
    """What server/ provides for one screened voice."""
    runner: object                                   # async open / push / close

    async def resync(self) -> None: ...              # send the listener the full current state
    async def heartbeat(self) -> None: ...           # same, on a timer (reliable packets are not replayed)
    async def unavailable(self, reason: str) -> None: ...
    async def resume(self, outage_s: float) -> None: ...


VoiceFactory = Callable[[str, str, str, Publish], VoiceHooks]   # (session_id, owner_id, listener, publish)


@dataclass
class _Voice:
    speaker: str
    listener: str
    session_id: str
    assembler: FrameAssembler
    session: StreamSession
    hooks: VoiceHooks
    pump: Optional[asyncio.Task] = None
    track: object = None


@dataclass
class CallAgent:
    """One call. `run()` until `stop()`; `bind_listener()` when the callee joins."""
    url: str
    token: str
    call_id: str
    caller_id: str
    voice_factory: VoiceFactory
    heartbeat_s: float = 5.0
    room_factory: Callable[[], object] = None        # tests pass a fake room
    stream_factory: Callable[[object], object] = None   # track -> async iterator of PCM events
    callee_id: Optional[str] = None
    voices: dict = field(default_factory=dict)
    _pending_tracks: dict = field(default_factory=dict)
    _stopped: asyncio.Event = field(default_factory=asyncio.Event)
    _outage_started: Optional[float] = None
    room: object = None

    # --- lifecycle -----------------------------------------------------------------------

    async def run(self) -> None:
        """Connect and serve until stopped. Never raises; failures are logged and reported."""
        try:
            self.room = (self.room_factory or _livekit_room)()
            self._wire(self.room)
            await self.room.connect(self.url, self.token)
            log.info(f"[{self.call_id}] screening agent joined the room")
            for participant in list(getattr(self.room, "remote_participants", {}).values()):
                for pub in list(getattr(participant, "track_publications", {}).values()):
                    if getattr(pub, "track", None) is not None:
                        self._on_track(pub.track, participant)
            while not self._stopped.is_set():
                try:
                    await asyncio.wait_for(self._stopped.wait(), timeout=self.heartbeat_s)
                except asyncio.TimeoutError:
                    await self._each_voice("heartbeat")
        except Exception as e:  # noqa: BLE001 — the call itself must never depend on the agent
            log.error(f"[{self.call_id}] screening agent failed: {type(e).__name__}: {e}")
            await self._each_voice("unavailable", f"screening agent failed: {type(e).__name__}")
        finally:
            await self._finish_voices()
            try:
                if self.room is not None:
                    await self.room.disconnect()
            except Exception:  # noqa: BLE001
                pass

    async def stop(self, reason: str = "call ended") -> None:
        log.info(f"[{self.call_id}] screening agent stopping: {reason}")
        self._stopped.set()

    def bind_listener(self, callee_id: str) -> None:
        """The callee joined: from now on each voice has a listener and can be screened."""
        if self.callee_id is not None:
            return                              # immutable once bound
        self.callee_id = callee_id
        for identity, (track, participant) in list(self._pending_tracks.items()):
            self._on_track(track, participant)

    # --- room events -----------------------------------------------------------------------

    def _wire(self, room) -> None:
        room.on("track_subscribed", lambda track, pub, participant: self._on_track(track, participant))
        room.on("track_unsubscribed", lambda track, pub, participant: self._pause(participant.identity))
        room.on("participant_disconnected", lambda participant: self._pause(participant.identity))
        room.on("participant_connected", lambda participant: self._spawn(self._listener_joined(participant.identity)))
        room.on("reconnecting", lambda *a: self._agent_lost())
        room.on("reconnected", lambda *a: self._spawn(self._agent_back()))
        room.on("disconnected", lambda *a: self._spawn(self.stop("agent disconnected from the room")))

    def _listener_of(self, speaker: str) -> Optional[str]:
        if speaker == self.caller_id:
            return self.callee_id
        if self.callee_id is not None and speaker == self.callee_id:
            return self.caller_id
        return None

    def _on_track(self, track, participant) -> None:
        identity = getattr(participant, "identity", "")
        if getattr(track, "kind", None) not in (1, "audio") and not _is_audio(track):
            return
        if identity not in (self.caller_id, self.callee_id):
            log.warning(f"[{self.call_id}] ignoring audio from {identity!r}: not a party to this call")
            return
        listener = self._listener_of(identity)
        if listener is None:
            self._pending_tracks[identity] = (track, participant)
            log.info(f"[{self.call_id}] {_who(identity, self.caller_id)} is talking before the other "
                     f"person joined; nobody is listening yet, so it is not screened")
            return
        self._pending_tracks.pop(identity, None)
        voice = self.voices.get(identity) or self._open_voice(identity, listener)
        if voice.pump is not None and not voice.pump.done():
            voice.pump.cancel()
        voice.track = track
        voice.pump = self._spawn(self._pump(voice, track))

    def _open_voice(self, speaker: str, listener: str) -> _Voice:
        role = "caller" if speaker == self.caller_id else "callee"
        session_id = f"rtc_{self.call_id}_{role}"
        hooks = self.voice_factory(session_id, listener, listener, self._publish)
        session = StreamSession(hooks.runner, f"webrtc {session_id}")
        session.put(SessionOpen(session_id=session_id, source=AudioSource.WEBRTC))
        voice = _Voice(speaker=speaker, listener=listener, session_id=session_id,
                       assembler=FrameAssembler(session_id), session=session, hooks=hooks)
        self.voices[speaker] = voice
        log.info(f"[{self.call_id}] screening the {role}'s voice for its listener ({session_id})")
        return voice

    def _pause(self, identity: str) -> None:
        voice = self.voices.get(identity)
        if voice and voice.pump is not None and not voice.pump.done():
            voice.pump.cancel()
            log.info(f"[{self.call_id}] {voice.session_id}: track gone; the session waits for it to return")

    async def _pump(self, voice: _Voice, track) -> None:
        try:
            stream = (self.stream_factory or _livekit_stream)(track)
            async for pcm in _pcm_events(stream):
                for frame in voice.assembler.feed(pcm):
                    voice.session.put(frame)
        except asyncio.CancelledError:
            raise
        except Exception as e:  # noqa: BLE001 — this voice stops being screened; the call goes on
            log.error(f"[{self.call_id}] {voice.session_id}: audio stream failed: {type(e).__name__}: {e}")
            await _safe(voice.hooks.unavailable(f"audio stream failed: {type(e).__name__}"))

    async def _listener_joined(self, identity: str) -> None:
        """A listener (re)joined: reliable packets are not replayed, so send the full state."""
        for voice in self.voices.values():
            if voice.listener == identity:
                await _safe(voice.hooks.resync())

    def _agent_lost(self) -> None:
        if self._outage_started is None:
            self._outage_started = time.monotonic()
            log.warning(f"[{self.call_id}] screening agent lost the room; reconnecting")

    async def _agent_back(self) -> None:
        if self._outage_started is None:
            return
        outage = time.monotonic() - self._outage_started
        self._outage_started = None
        log.warning(f"[{self.call_id}] screening agent back after {outage:.1f}s; that stretch was not screened")
        for voice in self.voices.values():
            await _safe(voice.hooks.resume(outage))

    async def _each_voice(self, method: str, *args) -> None:
        for voice in list(self.voices.values()):
            await _safe(getattr(voice.hooks, method)(*args))

    async def _finish_voices(self) -> None:
        for voice in list(self.voices.values()):
            if voice.pump is not None and not voice.pump.done():
                voice.pump.cancel()
            voice.session.put(voice.assembler.flush(final=True))
            await voice.session.finish()
            log.info(f"[{self.call_id}] {voice.session_id} closed after {voice.assembler.seconds:.1f}s of audio")

    async def _publish(self, identity: str, payload: dict) -> None:
        """A verdict to one listener only. Never raises (a dropped packet is resent by the heartbeat)."""
        try:
            await self.room.local_participant.publish_data(
                json.dumps(payload, ensure_ascii=False).encode(), reliable=True,
                destination_identities=[identity], topic=VERDICT_TOPIC)
        except Exception as e:  # noqa: BLE001
            log.warning(f"[{self.call_id}] could not send a verdict to its listener: {type(e).__name__}: {e}")

    def _spawn(self, coro) -> asyncio.Task:
        return asyncio.get_running_loop().create_task(coro)


def _who(identity: str, caller: str) -> str:
    return "the caller" if identity == caller else "the callee"


def _is_audio(track) -> bool:
    try:
        from livekit import rtc

        return getattr(track, "kind", None) == rtc.TrackKind.KIND_AUDIO
    except Exception:  # noqa: BLE001
        return False


def _livekit_room():
    from livekit import rtc

    return rtc.Room()


def _livekit_stream(track):
    from livekit import rtc

    return rtc.AudioStream(track, sample_rate=RATE, num_channels=1)


async def _pcm_events(stream):
    """int16 PCM bytes from a LiveKit AudioStream (events carry `.frame.data`) or a test
    iterator that yields bytes directly."""
    async for event in stream:
        if isinstance(event, (bytes, bytearray)):
            yield bytes(event)
        else:
            yield bytes(event.frame.data)


async def _safe(awaitable) -> None:
    try:
        await awaitable
    except Exception as e:  # noqa: BLE001
        log.warning(f"webrtc: hook failed: {type(e).__name__}: {e}")
