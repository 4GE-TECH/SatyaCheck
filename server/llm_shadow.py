"""SatyaCheck — the LLM shadow log (upgrade plan, Phase 4 Stage A).

When nlp_rag.llm_intent is switched on, every committed transcript update of a live
session is read by the LLM here, OFF the scoring and ASR paths, and the reading is stored
next to the deterministic score it would be compared with. Nothing reads these rows back
into scoring: the shadow has zero influence on risk, band, claims or reason codes.

  * one worker thread; a session that already has a reading in flight skips intermediate
    updates (the next one supersedes them anyway) but its final transcript always runs;
  * rows are per account (owner_id), hold counts and statuses only — never transcript
    text — and fall under the results retention clock and account deletion.

C owns this file.
"""

from __future__ import annotations

import json
import logging
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

import config

log = logging.getLogger("satyacheck.llm_shadow")

_EXECUTOR = ThreadPoolExecutor(max_workers=1, thread_name_prefix="satyacheck-llm-shadow")
_lock = threading.Lock()
_in_flight: set[str] = set()
_pending = 0
_idle = threading.Event()
_idle.set()


def _client():
    from nlp_rag.llm_intent import _client as llm_client

    return llm_client()


def enabled() -> bool:
    return config.LLM_PROVIDER != "off"


def submit(owner_id: str, session_id: str, transcript_rev: int, text: str,
           deterministic_risk: float, final: bool = False) -> bool:
    """Queue one shadow reading. False when skipped (off, nothing to read, or busy)."""
    global _pending
    if not enabled() or not owner_id or not (text or "").strip():
        return False
    with _lock:
        if session_id in _in_flight and not final:
            log.debug(f"[{session_id}] shadow reading in flight; rev {transcript_rev} skipped")
            return False
        _in_flight.add(session_id)
        _pending += 1
        _idle.clear()
    _EXECUTOR.submit(_run, owner_id, session_id, transcript_rev, text, deterministic_risk, final)
    return True


def _run(owner_id, session_id, transcript_rev, text, deterministic_risk, final) -> None:
    global _pending
    try:
        from nlp_rag.llm_intent import shadow_record
        from server.database import LlmShadowRecord, owner_session

        record = shadow_record(text, deterministic_risk, client=_client())
        record.update(transcript_rev=int(transcript_rev), final=bool(final))
        with owner_session(owner_id) as db:
            db.add(LlmShadowRecord(record_id=f"llm_{uuid.uuid4().hex[:12]}", owner_id=owner_id,
                                   session_id=session_id, transcript_rev=int(transcript_rev),
                                   status=record["status"], record_json=json.dumps(record)))
            db.commit()
        log.info(f"[{session_id}] shadow rev {transcript_rev}: {record['status']}, llm "
                 f"{record['llm_likelihood']} vs deterministic {record['deterministic_risk']} "
                 f"({record['validated']}/{record['findings']} findings would validate)")
    except Exception as e:  # noqa: BLE001 — shadow work never affects a call
        log.error(f"[{session_id}] shadow reading failed: {type(e).__name__}: {e}")
    finally:
        with _lock:
            _in_flight.discard(session_id)
            _pending -= 1
            if _pending <= 0:
                _idle.set()


def wait_idle(timeout: float = 30.0) -> bool:
    """Until every queued reading is stored (tests, shutdown)."""
    return _idle.wait(timeout)
