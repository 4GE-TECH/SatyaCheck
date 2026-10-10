"""The screening agent against a fake LiveKit room (acquisition/webrtc/agent.py) and the
server's per-voice hooks (server/webrtc_screening.py): a voice is screened only once its
listener is bound, it belongs to that listener, verdicts reach that listener only, and an
agent or stream failure is reported while the call goes on."""

from __future__ import annotations

import asyncio
import functools
import json
from types import SimpleNamespace

from acquisition.webrtc.agent import VERDICT_TOPIC, CallAgent
from contracts import AudioFrame, AudioSource, SessionOpen, TrustBand

SECOND = b"\x10\x00" * 16000      # 1 s of 16 kHz s16le


def _sync(test):
    """Run an async test on a fresh loop (no pytest-asyncio dependency)."""
    @functools.wraps(test)
    def wrapper():
        asyncio.run(test())
    return wrapper


class FakeRoom:
    def __init__(self):
        self.handlers, self.sent = {}, []
        self.remote_participants = {}
        self.local_participant = SimpleNamespace(publish_data=self._publish)

    def on(self, event, cb):
        self.handlers[event] = cb

    def emit(self, event, *args):
        return self.handlers[event](*args)

    async def connect(self, url, token):
        self.url, self.token = url, token

    async def disconnect(self):
        self.disconnected = True

    async def _publish(self, payload, *, reliable=True, destination_identities=(), topic=""):
        self.sent.append((list(destination_identities), topic, json.loads(payload)))


class Recorder:
    """VoiceHooks stand-in: records what the agent asked of it."""

    def __init__(self, session_id, owner_id, listener, publish):
        self.session_id, self.owner_id, self.listener, self.publish = session_id, owner_id, listener, publish
        self.calls = []
        outer = self

        class _Runner:
            async def open(self, msg):
                outer.calls.append(("open", msg))

            async def push(self, frame, score=True):
                outer.calls.append(("push", frame))

            async def close(self, msg):
                outer.calls.append(("close", msg))

        self.runner = _Runner()

    async def resync(self):
        self.calls.append(("resync",))

    async def heartbeat(self):
        self.calls.append(("heartbeat",))

    async def unavailable(self, reason):
        self.calls.append(("unavailable", reason))

    async def resume(self, outage_s):
        self.calls.append(("resume", outage_s))


def _track():
    return SimpleNamespace(kind=1, sid="TR")


def _person(identity):
    return SimpleNamespace(identity=identity, track_publications={})


async def _start(stream_bytes=(SECOND,), fail=False):
    room = FakeRoom()
    voices = {}

    def factory(session_id, owner, listener, publish):
        voices[session_id] = Recorder(session_id, owner, listener, publish)
        return voices[session_id]

    async def stream(track):
        if fail:
            raise RuntimeError("decoder exploded")
        for chunk in stream_bytes:
            yield chunk
            await asyncio.sleep(0)

    agent = CallAgent(url="ws://lk", token="t", call_id="c1", caller_id="alice", voice_factory=factory,
                      heartbeat_s=0.05, room_factory=lambda: room, stream_factory=stream)
    task = asyncio.create_task(agent.run())
    await asyncio.sleep(0.01)
    return agent, room, voices, task


async def _settle():
    for _ in range(10):
        await asyncio.sleep(0.01)


@_sync
async def test_the_callers_voice_waits_for_a_listener_then_belongs_to_them():
    agent, room, voices, task = await _start()
    room.emit("track_subscribed", _track(), None, _person("alice"))
    await _settle()
    assert voices == {}                                  # nobody is listening yet
    agent.bind_listener("bob")
    await _settle()
    voice = voices["rtc_c1_caller"]
    assert voice.owner_id == voice.listener == "bob"
    opened = [c[1] for c in voice.calls if c[0] == "open"]
    assert opened and isinstance(opened[0], SessionOpen) and opened[0].source == AudioSource.WEBRTC
    frames = [c[1] for c in voice.calls if c[0] == "push"]
    assert [f.t_start_s for f in frames] == [0.0, 0.5]
    await agent.stop()
    await task
    final = [c[1] for c in voice.calls if c[0] == "push"][-1]
    assert isinstance(final, AudioFrame) and final.is_final


@_sync
async def test_each_voice_is_screened_for_the_other_person():
    agent, room, voices, task = await _start()
    agent.bind_listener("bob")
    room.emit("track_subscribed", _track(), None, _person("alice"))
    room.emit("track_subscribed", _track(), None, _person("bob"))
    await _settle()
    assert voices["rtc_c1_caller"].listener == "bob" and voices["rtc_c1_callee"].listener == "alice"
    await agent.stop()
    await task


@_sync
async def test_a_stranger_in_the_room_is_never_screened():
    agent, room, voices, task = await _start()
    agent.bind_listener("bob")
    room.emit("track_subscribed", _track(), None, _person("mallory"))
    await _settle()
    assert voices == {}
    await agent.stop()
    await task


@_sync
async def test_a_reconnect_resumes_the_same_session_and_timeline():
    agent, room, voices, task = await _start()
    agent.bind_listener("bob")
    room.emit("track_subscribed", _track(), None, _person("alice"))
    await _settle()
    room.emit("participant_disconnected", _person("alice"))
    room.emit("track_subscribed", _track(), None, _person("alice"))
    await _settle()
    voice = voices["rtc_c1_caller"]
    assert len(voices) == 1 and sum(1 for c in voice.calls if c[0] == "open") == 1
    starts = [c[1].t_start_s for c in voice.calls if c[0] == "push"]
    assert starts == [0.0, 0.5, 1.0, 1.5]                # continues, does not restart at 0
    await agent.stop()
    await task


@_sync
async def test_a_listener_who_rejoins_gets_the_full_state_again():
    agent, room, voices, task = await _start()
    agent.bind_listener("bob")
    room.emit("track_subscribed", _track(), None, _person("alice"))
    await _settle()
    room.emit("participant_connected", _person("bob"))
    await _settle()
    assert ("resync",) in voices["rtc_c1_caller"].calls
    await agent.stop()
    await task


@_sync
async def test_an_agent_outage_is_reported_as_unscreened_time():
    agent, room, voices, task = await _start()
    agent.bind_listener("bob")
    room.emit("track_subscribed", _track(), None, _person("alice"))
    await _settle()
    room.emit("reconnecting")
    await asyncio.sleep(0.05)
    room.emit("reconnected")
    await _settle()
    resumed = [c for c in voices["rtc_c1_caller"].calls if c[0] == "resume"]
    assert resumed and resumed[0][1] >= 0.04
    await agent.stop()
    await task


@_sync
async def test_a_failed_audio_stream_says_screening_is_unavailable_and_the_agent_stays():
    agent, room, voices, task = await _start(fail=True)
    agent.bind_listener("bob")
    room.emit("track_subscribed", _track(), None, _person("alice"))
    await _settle()
    assert any(c[0] == "unavailable" for c in voices["rtc_c1_caller"].calls)
    assert not task.done()
    await agent.stop()
    await task


@_sync
async def test_heartbeats_resend_state_while_the_call_runs():
    agent, room, voices, task = await _start()
    agent.bind_listener("bob")
    room.emit("track_subscribed", _track(), None, _person("alice"))
    await asyncio.sleep(0.2)
    assert sum(1 for c in voices["rtc_c1_caller"].calls if c == ("heartbeat",)) >= 2
    await agent.stop()
    await task


@_sync
async def test_the_listener_gets_bounded_packets_and_only_the_listener():
    from server.pipeline.dispatcher import VerdictEvent
    from server.tests.test_live_session import _response
    from server.webrtc_screening import ScreenedVoice

    sent = []

    async def publish(identity, payload):
        sent.append((identity, payload))

    voice = ScreenedVoice("rtc_c1_caller", "bob", "bob", publish, runner_factory=lambda owner, dispatcher: SimpleNamespace(
        owner_id=owner, dispatcher=dispatcher))
    assert voice.runner.owner_id == "bob"
    sink = voice.runner.dispatcher.sinks[0]
    await sink.deliver(VerdictEvent(session_id="rtc_c1_caller", response=_response(TrustBand.HIGH_RISK),
                                    window_index=3, start_s=4, end_s=13, transcript_rev=1))
    await voice.unavailable("audio stream failed")
    await voice.resume(7.5)
    assert {who for who, _ in sent} == {"bob"}
    first, down, back = (p for _, p in sent[:3])
    assert first["display_band"] == TrustBand.HIGH_RISK.value and first["alerts"]
    assert down["screening_available"] is False and down["rev"] > first["rev"]
    assert back["screening_available"] is True and back["coverage"]["unscreened_s"] >= 7.5
    assert back["alerts"] == first["alerts"]                     # the alert outlives the outage
    assert all(p["type"] == "satyacheck.verdict" for _, p in sent)


def test_the_topic_clients_must_filter_on():
    assert VERDICT_TOPIC == "satyacheck.verdict"
