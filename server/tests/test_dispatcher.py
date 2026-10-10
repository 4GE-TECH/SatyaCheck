"""Item 6: one place that sends each verdict to every output.

Today `ws_router` sends the two app messages, writes the DB row and publishes a guardian
alert inline, one after another — so a slow guardian connection delays the overlay, an
exception in one output skips the rest, and a guardian is pinged on *every* window while
a call stays red. The dispatcher fans out to independent sinks: each is isolated, each
has a timeout, and the guardian hears about escalations, not repetitions.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import config
from contracts import TrustBand, create_mock_fixture
from server.pipeline import dispatcher as dp


def _event(i=0, band="red", escalated=False, final=False, session="s1"):
    response = create_mock_fixture(band).model_copy(update={"session_id": session})
    return dp.VerdictEvent(session_id=session, response=response, window_index=i,
                           escalated=escalated, is_final=final, owner_id=config.DEV_OWNER_ID)


class Recorder:
    def __init__(self, name="recorder", delay=0.0, fail=False):
        self.name, self.delay, self.fail, self.seen = name, delay, fail, []

    async def deliver(self, event):
        if self.delay:
            await asyncio.sleep(self.delay)
        if self.fail:
            raise RuntimeError(f"{self.name} is down")
        self.seen.append(event.window_index)


def _run(coro):
    return asyncio.run(coro)


# --- isolation, ordering, timeouts -------------------------------------------------------

def test_a_failing_sink_does_not_stop_the_others(caplog):
    good, bad = Recorder("good"), Recorder("bad", fail=True)
    d = dp.Dispatcher([bad, good])
    with caplog.at_level(logging.ERROR, logger="satyacheck.pipeline.dispatcher"):
        outcome = _run(d.dispatch(_event()))
    assert good.seen == [0]
    assert outcome == {"bad": False, "good": True}
    assert any("bad" in r.getMessage() and "is down" in r.getMessage() for r in caplog.records)


def test_events_reach_each_sink_in_window_order():
    rec = Recorder()
    d = dp.Dispatcher([rec, Recorder("slow", delay=0.01)])

    async def stream():
        for i in range(10):
            await d.dispatch(_event(i))

    _run(stream())
    assert rec.seen == list(range(10))


def test_a_slow_sink_times_out_without_holding_the_verdict(caplog):
    fast, slow = Recorder("fast"), Recorder("slow", delay=5.0)
    d = dp.Dispatcher([slow, fast], timeout_s=0.2)
    started = time.perf_counter()
    with caplog.at_level(logging.ERROR, logger="satyacheck.pipeline.dispatcher"):
        outcome = _run(d.dispatch(_event()))
    assert time.perf_counter() - started < 1.5
    assert fast.seen == [0] and outcome["slow"] is False
    assert any("timed out" in r.getMessage() for r in caplog.records)


# --- the sinks ------------------------------------------------------------------------------

class FakeSocket:
    def __init__(self):
        self.sent = []

    async def send_text(self, text):
        self.sent.append(json.loads(text))

    async def send_json(self, data):
        self.sent.append(data)


def test_app_overlay_sends_the_two_messages_the_app_reads():
    ws = FakeSocket()
    _run(dp.AppOverlaySink(ws).deliver(_event(3)))
    assert [m["type"] for m in ws.sent] == ["screening_update", "overlay_update"]
    assert ws.sent[0]["chunk_index"] == 3
    assert ws.sent[1]["state"] == "red"


def test_guardian_hears_escalations_not_repetitions(monkeypatch):
    published = []

    async def fake_publish(response, owner_id=None):
        published.append(response.fusion.band)

    monkeypatch.setattr(dp, "_publish_alert", fake_publish)
    sink = dp.GuardianSink()
    for i, escalated in enumerate([True, False, False, True, False]):
        _run(sink.deliver(_event(i, escalated=escalated)))
    assert len(published) == 2


def test_guardian_ignores_an_escalation_to_a_non_alerting_band(monkeypatch):
    published = []

    async def fake_publish(response, owner_id=None):
        published.append(response)

    monkeypatch.setattr(dp, "_publish_alert", fake_publish)
    _run(dp.GuardianSink().deliver(_event(0, band="caution", escalated=True)))
    assert published == []


def test_report_sink_persists_every_verdict_and_marks_the_last(tmp_path):
    from server.database import Base, ScreeningResult, ScreeningSession

    engine = create_engine(f"sqlite:///{tmp_path / 'r.db'}")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    with Session() as db:
        db.add(ScreeningSession(session_id="s1", owner_id=config.DEV_OWNER_ID, status="streaming"))
        db.commit()

    sink = dp.ReportSink(session_factory=Session)
    _run(sink.deliver(_event(0)))
    _run(sink.deliver(_event(1, final=True)))
    with Session() as db:
        rows = db.query(ScreeningResult).filter_by(session_id="s1").order_by(ScreeningResult.id).all()
        status = db.get(ScreeningSession, "s1").status
    assert [(r.chunk_index, r.is_final) for r in rows] == [(0, False), (1, True)]
    assert status == "complete"


def test_bank_api_is_a_quiet_stub():
    assert _run(dp.BankApiSink().deliver(_event())) is None


# --- building from config ---------------------------------------------------------------------

def test_the_default_sinks():
    assert config.DISPATCH_SINKS == ["app_overlay", "guardian", "report", "live_feed"]


def test_build_from_config_skips_unknown_names(monkeypatch, caplog):
    monkeypatch.setattr(config, "DISPATCH_SINKS", ["app_overlay", "carrier_pigeon", "bank_api"])
    with caplog.at_level(logging.WARNING, logger="satyacheck.pipeline.dispatcher"):
        d = dp.build_dispatcher(ws=FakeSocket())
    assert [s.name for s in d.sinks] == ["app_overlay", "bank_api"]
    assert any("carrier_pigeon" in r.getMessage() for r in caplog.records)


def test_app_overlay_is_skipped_without_a_socket():
    d = dp.build_dispatcher(ws=None)
    assert "app_overlay" not in [s.name for s in d.sinks]
