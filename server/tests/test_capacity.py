"""Upgrade plan, Phase 3: admission control, the shared inference limit, readiness."""

from __future__ import annotations

import threading
import time

from fastapi.testclient import TestClient

import config


def test_ready_without_warm_up_and_503_until_warm(monkeypatch):
    from server import capacity
    from server.main import app

    monkeypatch.setattr(config, "WARM_MODELS", False)
    r = TestClient(app).get("/api/ready")
    assert r.status_code == 200 and r.json()["ready"] is True and r.json()["device"] in ("cpu", "cuda")

    monkeypatch.setattr(config, "WARM_MODELS", True)
    monkeypatch.setattr(capacity, "_ready", threading.Event())
    monkeypatch.setattr(capacity, "model_devices", lambda: _loaded("cpu"))
    assert TestClient(app).get("/api/ready").status_code == 503
    capacity._ready.set()
    assert TestClient(app).get("/api/ready").status_code == 200


def _loaded(device, fallback=None, missing=()):
    return {name: {"device": None if name in missing else device, "fallback": fallback}
            for name in ("ecapa", "model_a", "whisper", "bge_m3")}


def _warm(monkeypatch, devices, preference="auto", error=None):
    from server import capacity

    monkeypatch.setattr(config, "WARM_MODELS", True)
    monkeypatch.setattr(config, "DEVICE_PREFERENCE", preference)
    for flag in ("USE_REAL_SPEAKER", "USE_REAL_SPOOF", "USE_REAL_NLP"):
        monkeypatch.setattr(config, flag, True)
    ready = threading.Event()
    ready.set()
    monkeypatch.setattr(capacity, "_ready", ready)
    monkeypatch.setattr(capacity, "_warm_error", [error] if error else [])
    monkeypatch.setattr(capacity, "model_devices", lambda: devices)
    return capacity.readiness()


def test_a_failed_warm_up_is_not_ready(monkeypatch):
    state = _warm(monkeypatch, _loaded("cuda"), error="RuntimeError: CUDA out of memory")
    assert state["ready"] is False and any("warm-up failed" in p for p in state["problems"])


def test_a_model_that_never_loaded_is_not_ready(monkeypatch):
    state = _warm(monkeypatch, _loaded("cuda", missing=("ecapa",)))
    assert state["ready"] is False and "ecapa did not load" in state["problems"]


def test_cpu_models_when_cuda_was_required_are_not_ready(monkeypatch):
    state = _warm(monkeypatch, _loaded("cpu"), preference="cuda")
    assert state["ready"] is False and any("cuda was required" in p for p in state["problems"])


def test_a_fallback_under_auto_stays_ready_but_is_reported(monkeypatch):
    devices = _loaded("cuda")
    devices["model_a"] = {"device": "cpu", "fallback": "RuntimeError: CUDA error"}
    state = _warm(monkeypatch, devices)
    assert state["ready"] is True and state["fallbacks"] == {"model_a": "RuntimeError: CUDA error"}


def test_the_session_limit_follows_the_device_unless_set(monkeypatch):
    from server import capacity

    monkeypatch.setattr(config, "MAX_LIVE_SESSIONS", None)
    monkeypatch.setattr(config, "MAX_LIVE_SESSIONS_BY_DEVICE", {"cpu": 2, "cuda": 6})
    monkeypatch.setattr(config, "torch_device", lambda: "cuda")
    assert capacity.max_live_sessions() == 6
    monkeypatch.setattr(config, "torch_device", lambda: "cpu")
    assert capacity.max_live_sessions() == 2
    monkeypatch.setattr(config, "MAX_LIVE_SESSIONS", 0)   # an explicit 0 refuses everything
    assert capacity.max_live_sessions() == 0


def test_admission_counts_and_releases(monkeypatch):
    from server.capacity import Admission

    monkeypatch.setattr(config, "MAX_LIVE_SESSIONS", 2)
    a = Admission()
    assert a.try_acquire() and a.try_acquire() and not a.try_acquire()
    a.release()
    assert a.try_acquire()


def test_inference_slots_cap_concurrent_model_calls(monkeypatch):
    from server import capacity

    monkeypatch.setattr(capacity, "_slots", threading.BoundedSemaphore(2))
    running, peak, lock = [0], [0], threading.Lock()

    def call():
        with capacity.inference_slot("test"):
            with lock:
                running[0] += 1
                peak[0] = max(peak[0], running[0])
            time.sleep(0.05)
            with lock:
                running[0] -= 1

    threads = [threading.Thread(target=call) for _ in range(6)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert peak[0] == 2


def test_a_finished_v2_session_frees_its_admission_slot(monkeypatch, isolated_db):
    import json

    import server.orchestrator as orch
    from contracts import AntiSpoofResult, SpeakerVerificationResult, StreamV2Start
    from server.capacity import admission
    from server.main import app

    monkeypatch.setattr(config, "USE_REAL_SPEAKER", True)
    monkeypatch.setattr(config, "USE_REAL_SPOOF", True)
    monkeypatch.setattr(config, "USE_REAL_NLP", False)
    monkeypatch.setattr(orch, "_real_speaker_branch", lambda p, owner_id=None: SpeakerVerificationResult.neutral())
    monkeypatch.setattr(orch, "_real_spoof_branch", lambda p: AntiSpoofResult(risk=0.05, details={"available": True}))
    before = admission.active
    with TestClient(app).websocket_connect("/api/ws/v2/screen/cap-1") as ws:
        ws.send_text(StreamV2Start().model_dump_json())
        assert json.loads(ws.receive_text())["type"] == "ready"
        assert admission.active == before + 1
        ws.send_text(json.dumps({"type": "end"}))
        while not json.loads(ws.receive_text()).get("is_final"):
            pass
    time.sleep(0.1)
    assert admission.active == before


from server.tests.isolated_db import isolated_db  # noqa: E402,F401  (fixture)
