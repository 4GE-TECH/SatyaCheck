"""App-to-app calls: who is in which call (webrtc/BACKEND_API.md).

A call has exactly two people, fixed when it is placed: the caller rings one of their
connections (server/contacts.py), and only that person can answer. So a verdict about one
voice can only ever reach the other person in the call.

    ringing --accept--> active --hang up--> ended
       |--decline / cancel / no answer in WEBRTC_RING_TIMEOUT_S--> ended

  * only the callee can accept or decline, and only while it rings; the callee's room
    token is minted at accept, so nobody is in the room for them before they answer;
  * someone already ringing or in a call is busy;
  * another account's call answers the same "not found" as a call that never existed
    (no existence leak);
  * calls that end without a request (unanswered) are queued for the router to stop their
    screening agent (`drain_ended`).

In memory: calls live as long as this process. Restarting the server ends the calls.

C owns this file.

    python -m server.webrtc_calls     # smoke test
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Callable, Optional

import config


class CallError(Exception):
    """Refused, with the HTTP status the router answers."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


@dataclass
class Call:
    call_id: str
    caller_id: str
    callee_id: str
    created_at: float
    status: str = "ringing"                 # ringing | active | ended
    accepted_at: Optional[float] = None
    ended_at: Optional[float] = None
    ended_reason: Optional[str] = None      # declined | missed | cancelled | hung_up

    @property
    def room(self) -> str:
        return f"satyacheck-{self.call_id}"

    @property
    def agent_identity(self) -> str:
        return f"satyacheck-agent-{self.call_id}"

    def has(self, user_id: str) -> bool:
        return user_id in (self.caller_id, self.callee_id)

    def other(self, user_id: str) -> Optional[str]:
        return self.callee_id if user_id == self.caller_id else self.caller_id if user_id == self.callee_id else None

    def rings_for_s(self, now: float) -> int:
        return max(0, int(config.WEBRTC_RING_TIMEOUT_S - (now - self.created_at)))


@dataclass
class CallRegistry:
    clock: Callable[[], float] = time.monotonic
    _calls: dict = field(default_factory=dict)          # call_id -> Call
    _ended: list = field(default_factory=list)          # call_ids ended on their own, for drain_ended()
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _end(self, call: Call, reason: str, now: float) -> None:
        if call.status != "ended":
            call.status, call.ended_at, call.ended_reason = "ended", now, reason

    def _expire(self, now: float) -> None:
        for call in self._calls.values():
            if call.status == "ringing" and now - call.created_at > config.WEBRTC_RING_TIMEOUT_S:
                self._end(call, "missed", now)
                self._ended.append(call.call_id)
        # Forget ended calls once nobody can still be polling them.
        for call_id in [c.call_id for c in self._calls.values()
                        if c.status == "ended" and now - (c.ended_at or now) > config.WEBRTC_CALL_TTL_S]:
            self._calls.pop(call_id, None)

    def _live_for(self, user_id: str) -> Optional[Call]:
        return next((c for c in self._calls.values() if c.status != "ended" and c.has(user_id)), None)

    def active(self) -> list[Call]:
        with self._lock:
            self._expire(self.clock())
            return [c for c in self._calls.values() if c.status != "ended"]

    def drain_ended(self) -> list[str]:
        """Calls that ended without anyone asking (unanswered): their agents need stopping."""
        with self._lock:
            self._expire(self.clock())
            ended, self._ended = self._ended, []
            return ended

    def create(self, caller_id: str, callee_id: str) -> Call:
        with self._lock:
            now = self.clock()
            self._expire(now)
            if caller_id == callee_id:
                raise CallError(400, "You cannot call yourself.")
            if self._live_for(caller_id) is not None:
                raise CallError(409, "You are already in a call. Hang up first.")
            if self._live_for(callee_id) is not None:
                raise CallError(409, "They are on another call. Try again in a few minutes.")
            if sum(1 for c in self._calls.values() if c.status != "ended") >= config.WEBRTC_MAX_CALLS:
                raise CallError(503, "The screening service is at capacity. Try again in a minute.")
            call = Call(call_id=secrets.token_hex(8), caller_id=caller_id, callee_id=callee_id, created_at=now)
            self._calls[call.call_id] = call
            return call

    def incoming_for(self, user_id: str) -> list[Call]:
        """Calls ringing for this user, oldest first."""
        with self._lock:
            self._expire(self.clock())
            return sorted((c for c in self._calls.values() if c.status == "ringing" and c.callee_id == user_id),
                          key=lambda c: c.created_at)

    def _ringing_for_callee(self, call_id: str, user_id: str) -> Call:
        call = self._calls.get(call_id)
        if call is None or call.callee_id != user_id or call.status != "ringing":
            raise CallError(404, "This call is no longer ringing.")
        return call

    def accept(self, call_id: str, user_id: str) -> Call:
        with self._lock:
            now = self.clock()
            self._expire(now)
            call = self._ringing_for_callee(call_id, user_id)
            call.status, call.accepted_at = "active", now
            return call

    def decline(self, call_id: str, user_id: str) -> Call:
        with self._lock:
            now = self.clock()
            self._expire(now)
            call = self._ringing_for_callee(call_id, user_id)
            self._end(call, "declined", now)
            return call

    def get_for(self, call_id: str, user_id: str) -> Call:
        """The call, if this user is in it. Anything else is the same 404."""
        with self._lock:
            self._expire(self.clock())
            call = self._calls.get(call_id)
            if call is None or not call.has(user_id):
                raise CallError(404, "Call not found.")
            return call

    def end(self, call_id: str, user_id: str) -> Call:
        call = self.get_for(call_id, user_id)
        with self._lock:
            if call.status == "ringing":
                reason = "cancelled" if user_id == call.caller_id else "declined"
            else:
                reason = "hung_up"
            self._end(call, reason, self.clock())
            return call


registry = CallRegistry()


if __name__ == "__main__":
    r = CallRegistry()
    c = r.create("alice", "bob")
    print(c.room, c.agent_identity, c.status)
    assert [x.call_id for x in r.incoming_for("bob")] == [c.call_id]
    try:
        r.accept(c.call_id, "mallory")
    except CallError as e:
        print("[OK] only the callee can answer:", e.status)
    assert r.accept(c.call_id, "bob").status == "active"
    try:
        r.create("carol", "bob")
    except CallError as e:
        print("[OK] a callee in a call is busy:", e.status)
    print("[OK] call registry smoke test")
