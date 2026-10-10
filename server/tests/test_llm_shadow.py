"""Upgrade plan, Phase 4 Stage A: the LLM runs in shadow and changes nothing.

The shadow reading is stored beside the deterministic score, per account, with no
transcript text; it runs off the scoring and ASR paths; and a call scored with the shadow
on gets exactly the verdict it gets with it off.
"""

from __future__ import annotations

import asyncio
import json
import time

import numpy as np
import pytest

import config
from contracts import (AntiSpoofResult, AudioFrame, AudioSource, ScriptAnalysisResult, SessionClose, SessionOpen,
                       SpeakerVerificationResult, TranscriptResult)
from nlp_rag.llm_intent import LlmFinding, LlmIntent
from server.tests.isolated_db import isolated_db  # noqa: F401  (fixture)

TEXT = "Main bank se bol raha hoon. Abhi OTP batao. Kisi ko mat batana."


class StubClient:
    def __init__(self, delay=0.0):
        self.delay, self.calls = delay, 0
        outer = self

        class _M:
            def parse(self, **kw):
                outer.calls += 1
                time.sleep(outer.delay)
                intent = LlmIntent(scam_likelihood=0.95, summary="asks for an OTP", findings=[
                    LlmFinding(category="credential_request", quote="Abhi OTP batao", negated=False,
                               reported_speech=False)])
                return type("R", (), {"parsed_output": intent, "stop_reason": "end_turn"})()
        self.messages = _M()


@pytest.fixture
def shadow_on(monkeypatch):
    from server import llm_shadow

    monkeypatch.setattr(config, "LLM_PROVIDER", "anthropic")
    monkeypatch.setattr(config, "LLM_DISCLOSURE_RECORDED", True)
    monkeypatch.setattr(config, "LLM_RETENTION_RECORD", "reviewed")
    stub = StubClient()
    monkeypatch.setattr(llm_shadow, "_client", lambda: stub)
    return stub


def _rows(isolated_db):
    from server.database import LlmShadowRecord

    with isolated_db() as db:
        return [(r.owner_id, r.session_id, json.loads(r.record_json)) for r in db.query(LlmShadowRecord)]


def test_a_shadow_reading_is_stored_per_account_without_transcript_text(isolated_db, shadow_on):
    from server import llm_shadow

    llm_shadow.submit("acct-a", "call-1", 3, TEXT, deterministic_risk=0.72, final=True)
    llm_shadow.wait_idle()
    [(owner, session, record)] = _rows(isolated_db)
    assert (owner, session) == ("acct-a", "call-1")
    assert record["deterministic_risk"] == 0.72 and record["llm_likelihood"] == 0.95
    assert record["validated"] == 1 and record["influence"] == "none" and record["transcript_rev"] == 3
    assert "OTP" not in json.dumps(record)


def test_nothing_is_called_or_stored_when_the_llm_is_off(isolated_db, monkeypatch):
    from server import llm_shadow

    monkeypatch.setattr(config, "LLM_PROVIDER", "off")
    llm_shadow.submit("acct-a", "call-1", 1, TEXT, deterministic_risk=0.5, final=True)
    llm_shadow.wait_idle()
    assert _rows(isolated_db) == []


def test_a_busy_session_skips_intermediate_readings_but_never_the_final(isolated_db, shadow_on):
    from server import llm_shadow

    shadow_on.delay = 0.2
    for rev in range(1, 6):
        llm_shadow.submit("acct-a", "call-2", rev, TEXT, deterministic_risk=0.5, final=False)
    llm_shadow.submit("acct-a", "call-2", 6, TEXT, deterministic_risk=0.5, final=True)
    llm_shadow.wait_idle()
    revs = [r["transcript_rev"] for _, _, r in _rows(isolated_db)]
    assert 6 in revs and len(revs) < 6, revs


def _run_call(monkeypatch, tmp_path):
    """A short call through the real runner with stubbed branches; returns final verdicts."""
    import server.orchestrator as orch
    from server.pipeline.dispatcher import Dispatcher
    from server.pipeline.runner import SessionRunner

    monkeypatch.setattr(config, "USE_REAL_SPEAKER", True)
    monkeypatch.setattr(config, "USE_REAL_SPOOF", True)
    monkeypatch.setattr(orch, "_real_speaker_branch", lambda p, owner_id=None: SpeakerVerificationResult.neutral())
    monkeypatch.setattr(orch, "_real_spoof_branch", lambda p: AntiSpoofResult(risk=0.3, details={"available": True}))

    class Words:
        def push(self, chunk, sample_rate=16000):
            return TranscriptResult(text=TEXT, detected_language="hi", confidence=0.9)

        def flush(self):
            return TranscriptResult(text=TEXT, detected_language="hi", confidence=0.9)

    runner = SessionRunner(dispatcher=Dispatcher([]), owner_id="acct-a", transcriber_factory=Words,
                           analyze=lambda t: ScriptAnalysisResult(risk=0.6, details={"available": True}))
    t = np.arange(16000 * 7) / 16000
    pcm = (0.3 * np.sin(2 * np.pi * 220 * t) * ((t % 0.5) < 0.4) * 32767).astype("<i2").tobytes()

    async def go():
        await runner.open(SessionOpen(session_id="z-call", source=AudioSource.APP_WS))
        events = []
        for k, i in enumerate(range(0, len(pcm), 16000)):
            events += await runner.push(AudioFrame(session_id="z-call", seq=k, t_start_s=k * 0.5,
                                                   pcm_s16le=pcm[i:i + 16000]))
        events += await runner.close(SessionClose(session_id="z-call", reason="test"))
        return [(e.window_index, e.response.fusion.risk_score, e.response.fusion.band.value,
                 [c.code for c in e.response.fusion.reason_codes]) for e in events]

    return asyncio.run(go())


def test_the_shadow_has_zero_influence_on_every_verdict(isolated_db, monkeypatch, tmp_path, shadow_on):
    from server import llm_shadow

    with_shadow = _run_call(monkeypatch, tmp_path)
    llm_shadow.wait_idle()
    assert _rows(isolated_db), "the shadow ran"
    monkeypatch.setattr(config, "LLM_PROVIDER", "off")
    without = _run_call(monkeypatch, tmp_path)
    assert with_shadow == without
