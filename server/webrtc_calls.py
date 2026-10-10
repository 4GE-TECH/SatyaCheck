"""App-to-app calls: who is in which call (webrtc/BACKEND_API.md).

A call has exactly two people. The caller creates it and gets a short code to share; the
callee joins with that code, and from then on the pairing is fixed: the callee can never
change, so a verdict about one voice can only ever reach the other person in the call.

  * codes are random, single-use and expire (WEBRTC_CALL_TTL_S) if nobody joins;
  * joining is rate-limited per account, so codes cannot be guessed by brute force;
  * an unknown, expired or used code, and another account's call, all answer the same
    "not found" (no existence leak);
  * calling yourself is refused (two phones on one account would share one identity).

In memory: calls live as long as this process. Restarting the server ends the calls.

C owns this file.

    python -m server.webrtc_calls     # smoke test
"""

from __future__ import annotations

import secrets
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional

import config

_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"   # no 0/O, 1/I/L: read aloud over a phone
CODE_LENGTH = 8


class CallError(Exception):
    """Refused, with the HTTP status the router answers."""

    def __init__(self, status: int, detail: str) -> None:
        super().__init__(detail)
        self.status, self.detail = status, detail


@dataclass
class Call:
    call_id: str
    code: str
    caller_id: str
    created_at: float
    callee_id: Optional[str] = None
    joined_at: Optional[float] = None
    ended_at: Optional[float] = None

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


@dataclass
class CallRegistry:
    clock: Callable[[], float] = time.monotonic
    _calls: dict = field(default_factory=dict)          # call_id -> Call
    _codes: dict = field(default_factory=dict)          # code -> call_id (until joined)
    _attempts: dict = field(default_factory=dict)       # user -> deque of join attempt times
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def _expire(self, now: float) -> None:
        for code, call_id in list(self._codes.items()):
            call = self._calls.get(call_id)
            if call is None or call.ended_at is not None or now - call.created_at > config.WEBRTC_CALL_TTL_S:
                self._codes.pop(code, None)
                if call is not None and call.callee_id is None and call.ended_at is None:
                    call.ended_at = now          # nobody joined in time

    def active(self) -> list[Call]:
        with self._lock:
            self._expire(self.clock())
            return [c for c in self._calls.values() if c.ended_at is None]

    def create(self, caller_id: str) -> Call:
        with self._lock:
            now = self.clock()
            self._expire(now)
            if sum(1 for c in self._calls.values() if c.ended_at is None) >= config.WEBRTC_MAX_CALLS:
                raise CallError(503, "The screening service is at capacity. Try again in a minute.")
            code = "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))
            while code in self._codes:
                code = "".join(secrets.choice(_ALPHABET) for _ in range(CODE_LENGTH))
            call = Call(call_id=secrets.token_hex(8), code=code, caller_id=caller_id, created_at=now)
            self._calls[call.call_id] = call
            self._codes[code] = call.call_id
            return call

    def join(self, code: str, callee_id: str) -> Call:
        with self._lock:
            now = self.clock()
            window = self._attempts.setdefault(callee_id, deque())
            while window and now - window[0] > 60:
                window.popleft()
            if len(window) >= config.WEBRTC_JOIN_ATTEMPTS_PER_MIN:
                raise CallError(429, "Too many attempts. Wait a minute, then try the code again.")
            window.append(now)
            self._expire(now)
            call_id = self._codes.get((code or "").strip().upper())
            call = self._calls.get(call_id) if call_id else None
            if call is None:
                raise CallError(404, "That call code is not valid. Check it, or ask for a new one.")
            if call.caller_id == callee_id:
                raise CallError(400, "You cannot join your own call. The other person needs their own account.")
            call.callee_id, call.joined_at = callee_id, now
            self._codes.pop(call.code, None)     # single use
            return call

    def get_for(self, call_id: str, user_id: str) -> Call:
        """The call, if this user is in it. Anything else is the same 404."""
        with self._lock:
            call = self._calls.get(call_id)
            if call is None or not call.has(user_id):
                raise CallError(404, "Call not found.")
            return call

    def end(self, call_id: str, user_id: str) -> Call:
        call = self.get_for(call_id, user_id)
        with self._lock:
            if call.ended_at is None:
                call.ended_at = self.clock()
            self._codes.pop(call.code, None)
            return call


registry = CallRegistry()


if __name__ == "__main__":
    r = CallRegistry()
    c = r.create("alice")
    print(c.code, c.room, c.agent_identity)
    assert r.join(c.code.lower(), "bob").callee_id == "bob"
    try:
        r.join(c.code, "mallory")
    except CallError as e:
        print("[OK] a used code is refused:", e.status)
    print("[OK] call registry smoke test")
