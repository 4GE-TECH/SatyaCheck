"""Server side of app-to-app calls: tokens, one screening agent per call, and what each
listener is sent (webrtc/BACKEND_API.md).

  * Tokens (LiveKit JWTs, minted here, short-lived, one room each):
      - a phone may publish its microphone and subscribe; it may NOT publish data, so a
        caller can never send the listener a fake "verified" verdict;
      - the agent may subscribe and publish data, never media. It is deliberately NOT
        hidden: LiveKit does not tell clients who a hidden participant is (measured: the
        sender of a hidden agent's packets arrives as None), so clients could neither
        verify verdicts nor see the agent leave. Clients keep it out of the call UI by
        its identity.
    Clients check the sender: a verdict counts only from the `agent_identity` the API
    returned (defence in depth if a grant is ever misconfigured).
  * Each voice is screened for its listener: owner = listener (their enrolled people are
    the candidates), verdicts go to the listener only, through `LivePresenter`, so the
    escalate-only band, append-only alerts and coverage reporting hold here as they do on
    the v2 WebSocket.
  * Admission: a call takes two live-session slots (two voices) for its whole life.

C owns this file.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import timedelta
from typing import Optional

import config
from server.live_presenter import LivePresenter

log = logging.getLogger("satyacheck.webrtc")


# --- tokens -------------------------------------------------------------------------------

def phone_token(call, user_id: str) -> str:
    from livekit import api

    grants = api.VideoGrants(room_join=True, room=call.room, can_subscribe=True, can_publish=True,
                             can_publish_sources=["microphone"], can_publish_data=False)
    return (api.AccessToken(config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET)
            .with_identity(user_id).with_name("caller" if user_id == call.caller_id else "callee")
            .with_ttl(timedelta(seconds=config.WEBRTC_TOKEN_TTL_S)).with_grants(grants).to_jwt())


def agent_token(call) -> str:
    from livekit import api

    grants = api.VideoGrants(room_join=True, room=call.room, can_subscribe=True, can_publish=False,
                             can_publish_data=True, hidden=False)
    return (api.AccessToken(config.LIVEKIT_API_KEY, config.LIVEKIT_API_SECRET)
            .with_identity(call.agent_identity).with_name("SatyaCheck screening")
            .with_ttl(timedelta(seconds=config.WEBRTC_CALL_TTL_S + 3 * 3600)).with_grants(grants).to_jwt())


# --- one screened voice ---------------------------------------------------------------------

class WebRtcSink:
    """Dispatcher sink: verdicts about one voice, to its listener, as bounded packets."""
    name = "webrtc_listener"

    def __init__(self, voice: "ScreenedVoice") -> None:
        self.voice = voice

    async def deliver(self, event) -> None:
        changed, assessment = self.voice.presenter.consider(event)
        if changed or assessment is not None:
            await self.voice.send()
            from server.observability import ASSESSMENTS

            if assessment is not None:
                ASSESSMENTS.labels(assessment.display_band, "false").inc()


class ScreenedVoice:
    """The hooks the agent calls for one voice (acquisition.webrtc.agent.VoiceHooks)."""

    def __init__(self, session_id: str, owner_id: str, listener: str, publish, runner_factory=None) -> None:
        from server.pipeline.dispatcher import Dispatcher, build_dispatcher
        from server.transport_runner import make_retaining_runner

        self.session_id, self.listener, self._publish = session_id, listener, publish
        self.presenter = LivePresenter(session_id)
        self.available, self.reason = True, None
        self.outage_s = 0.0
        dispatcher = Dispatcher([WebRtcSink(self)] + build_dispatcher(ws=None).sinks)
        self.runner = (runner_factory or make_retaining_runner)(owner_id, dispatcher)

    def packet(self) -> dict:
        packet = self.presenter.compact(available=self.available, reason=self.reason)
        if self.outage_s and packet.get("coverage"):
            packet["coverage"]["unscreened_s"] = round(packet["coverage"]["unscreened_s"] + self.outage_s, 1)
            packet["coverage"]["degraded"] = True
        elif self.outage_s:
            packet["coverage"] = {"screened_s": 0.0, "unscreened_s": round(self.outage_s, 1), "degraded": True}
        return packet

    async def send(self) -> None:
        await self._publish(self.listener, self.packet())

    async def resync(self) -> None:
        await self.send()

    async def heartbeat(self) -> None:
        await self.send()

    async def unavailable(self, reason: str) -> None:
        self.available, self.reason = False, reason
        self.presenter.rev += 1
        await self.send()

    async def resume(self, outage_s: float) -> None:
        self.outage_s += max(0.0, outage_s)
        self.available, self.reason = True, None
        self.presenter.rev += 1
        await self.send()


# --- agents ---------------------------------------------------------------------------------

class AgentManager:
    """One screening agent per call, in this process's event loop."""

    def __init__(self, agent_factory=None) -> None:
        self._agents: dict = {}
        self._tasks: dict = {}
        self._admitted: dict = {}
        self._agent_factory = agent_factory

    def _make_agent(self, call):
        if self._agent_factory is not None:
            return self._agent_factory(call)
        from acquisition.api import CallAgent

        return CallAgent(url=config.LIVEKIT_AGENT_URL, token=agent_token(call), call_id=call.call_id,
                         caller_id=call.caller_id, heartbeat_s=config.WEBRTC_HEARTBEAT_S,
                         voice_factory=lambda sid, owner, listener, publish: ScreenedVoice(sid, owner, listener,
                                                                                            publish))

    def start(self, call) -> bool:
        """Admit the call's two voices and start its agent. False when at capacity."""
        from server.capacity import admission

        got = 0
        for _ in range(2):
            if admission.try_acquire():
                got += 1
        if got < 2:
            for _ in range(got):
                admission.release()
            return False
        self._admitted[call.call_id] = 2
        agent = self._make_agent(call)
        self._agents[call.call_id] = agent
        task = asyncio.get_running_loop().create_task(agent.run())
        task.add_done_callback(lambda _t, cid=call.call_id: self._release(cid))
        self._tasks[call.call_id] = task
        from server.observability import WEBRTC_CALLS

        WEBRTC_CALLS.inc()
        log.info(f"[{call.call_id}] call created; screening agent starting")
        return True

    def bind_listener(self, call) -> None:
        agent = self._agents.get(call.call_id)
        if agent is not None:
            agent.bind_listener(call.callee_id)

    async def stop(self, call_id: str, reason: str = "call ended") -> None:
        agent = self._agents.pop(call_id, None)
        if agent is not None:
            await agent.stop(reason)
        task = self._tasks.pop(call_id, None)
        if task is not None:
            try:
                await asyncio.wait_for(task, timeout=30)
            except Exception as e:  # noqa: BLE001
                log.warning(f"[{call_id}] agent did not stop cleanly: {type(e).__name__}: {e}")

    def _release(self, call_id: str) -> None:
        from server.capacity import admission

        for _ in range(self._admitted.pop(call_id, 0)):
            admission.release()
        self._agents.pop(call_id, None)
        self._tasks.pop(call_id, None)

    async def stop_all(self) -> None:
        for call_id in list(self._agents):
            await self.stop(call_id, "server shutting down")

    def running(self, call_id: str) -> bool:
        task = self._tasks.get(call_id)
        return task is not None and not task.done()


manager: Optional[AgentManager] = None


def get_manager() -> AgentManager:
    global manager
    if manager is None:
        manager = AgentManager()
    return manager
