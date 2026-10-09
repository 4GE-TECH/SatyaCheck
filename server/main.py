"""SatyaCheck — FastAPI Application Entry Point

Stack: FastAPI + uvicorn + SQLite (sqlalchemy)
Run:   uvicorn server.main:app --reload --port 8000

C owns this file. Routing structure:
  /api/health         — Health check
  /api/mock/*         — Block 0/1 mock fixtures (deprecated after GATE C2)
  /api/persons/*      — Enrolled contacts CRUD
  /api/enroll         — Audio enrollment endpoint
  /api/screen/*       — Audio screening endpoint
  /api/report/*       — Incident report generation (Block 3)
  /api/metrics        — System metrics (Block 3)
  /api/demo/*         — Demo reset endpoint (Block 4)
  /api/ws/*           — WebSocket streaming (Block 3)
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

import config
from server.mock_router import router as mock_router

from server.persons_router import router as persons_router
from server.enroll_router  import router as enroll_router
from server.screen_router  import router as screen_router
from server.report_router  import router as report_router
from server.demo_router    import router as demo_router
from server.ws_router      import router as ws_router
from server.live_router    import router as live_router
from server.evidence_router import router as evidence_router

logging.basicConfig(level=config.LOG_LEVEL)
log = logging.getLogger("satyacheck.server")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    log.info("SatyaCheck server starting up…")
    log.info(f"  MODELS_DIR : {config.MODELS_DIR}")
    log.info(f"  DB_PATH    : {config.DB_PATH}")
    log.info(f"  USE_REAL_SPEAKER={config.USE_REAL_SPEAKER} | USE_REAL_SPOOF={config.USE_REAL_SPOOF} | USE_REAL_NLP={config.USE_REAL_NLP}")

    # Initialise DB when database.py is ready (Block 1)
    try:
        from server.database import init_db, get_person_by_id
        init_db()
        log.info("  DB init: OK")
        
        # Configure nlp_rag with person_lookup for challenge questions
        try:
            from nlp_rag.api import configure as configure_nlp
            configure_nlp(person_lookup=get_person_by_id)
            log.info("  nlp_rag person_lookup configured: OK")
            _log_retrieval_status()
        except Exception as nlp_err:
            log.warning(f"  nlp_rag configuration skipped: {nlp_err}")
    except ImportError:
        log.warning("  server.database not yet available — skipping DB init (Block 0 mode)")

    yield
    log.info("SatyaCheck server shutting down.")


def _retrieval_status() -> dict:
    """nlp_rag's retrieval wiring, or an 'unknown' status if it cannot be read."""
    try:
        from nlp_rag.api import retrieval_status
        return retrieval_status()
    except Exception as e:
        return {"configured": False, "available": False, "reason": f"status unreadable: {e}"}


def _log_retrieval_status() -> None:
    """ERROR, not WARNING: a markers-only intent branch still returns valid verdicts,
    so this line is the only place the degradation is visible. See
    nlp_rag/tests/test_import_order.py for the known cause."""
    status = _retrieval_status()
    if status["available"]:
        log.info("  nlp_rag retrieval: OK")
    else:
        log.error(
            f"  nlp_rag retrieval UNAVAILABLE — intent branch runs markers-only: "
            f"{status.get('reason') or 'no reason recorded'}"
        )


app = FastAPI(
    title="SatyaCheck API",
    version="0.1.0",
    description=(
        "Voice-clone scam detection API. "
        "Fuses speaker identity, anti-spoof, and script intent into an explainable trust score."
    ),
    lifespan=lifespan,
)

# ── CORS ─────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Routers ──────────────────────────────────────────────────────────
app.include_router(mock_router)

app.include_router(persons_router)
app.include_router(enroll_router)
app.include_router(screen_router)
app.include_router(report_router)
app.include_router(demo_router)
app.include_router(ws_router)
app.include_router(live_router)
app.include_router(evidence_router)


from server.pipeline.runner import SessionRunner  # noqa: E402


class _RetainingRunner(SessionRunner):
    """A SessionRunner that, when RETAIN_SESSION_AUDIO is on, also writes the whole call to
    data/sessions/<id>/chunk_0000.wav — the file enrol_from_call globs, and the only way
    to replay a live call that scored oddly. The app WebSocket path retains its own chunks
    in ws_router; this is for transports with no such path (Exotel)."""

    def _part(self, session_id: str):
        from server.ws_router import _session_audio_dir

        d = _session_audio_dir(session_id)
        return None if d is None else d / "call.pcm.part"

    async def push(self, frame, score: bool = True):
        if config.RETAIN_SESSION_AUDIO and frame.pcm_s16le:
            try:
                part = self._part(frame.session_id)
                if part is not None:
                    part.parent.mkdir(parents=True, exist_ok=True)
                    with open(part, "ab") as f:
                        f.write(frame.pcm_s16le)
            except Exception as e:  # noqa: BLE001 — never break a live call over a debug artefact
                log.warning(f"[{frame.session_id}] could not retain call audio: {e}")
        events = await super().push(frame, score)
        if frame.is_final:
            self._seal(frame.session_id)
        return events

    async def close(self, msg):
        events = await super().close(msg)
        self._seal(msg.session_id)
        return events

    def _seal(self, session_id: str) -> None:
        import wave

        try:
            part = self._part(session_id)
            if part is None or not part.is_file():
                return
            with wave.open(str(part.with_name("chunk_0000.wav")), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(config.TARGET_SAMPLE_RATE)
                w.writeframes(part.read_bytes())
            part.unlink()
            log.info(f"[{session_id}] call audio retained at {part.with_name('chunk_0000.wav')}")
        except Exception as e:  # noqa: BLE001
            log.warning(f"[{session_id}] could not write retained call audio: {e}")


def _exotel_runner():
    """A SessionRunner for one Exotel call: no app socket to talk to, so the dispatcher
    carries the guardian and report sinks only."""
    from server.pipeline.dispatcher import build_dispatcher

    return _RetainingRunner(dispatcher=build_dispatcher(ws=None))


def mount_exotel(target: FastAPI, runner_factory=None) -> bool:
    """Mount the Exotel Stream route when config.ENABLE_EXOTEL is on. Returns whether it did."""
    if not config.ENABLE_EXOTEL:
        return False
    from acquisition.api import build_exotel_router

    target.include_router(build_exotel_router(runner_factory or _exotel_runner))
    log.info(f"  Exotel stream route mounted at {config.EXOTEL_WS_PATH}")
    return True


mount_exotel(app)


# ── Health ────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["system"])
async def health_check() -> JSONResponse:
    retrieval = _retrieval_status()
    return JSONResponse(content={
        "status": "ok",
        "version": app.version,
        "use_real_speaker": config.USE_REAL_SPEAKER,
        "use_real_spoof": config.USE_REAL_SPOOF,
        "use_real_nlp": config.USE_REAL_NLP,
        "use_real_fusion": config.USE_REAL_FUSION,
        "nlp_retrieval_available": retrieval["available"],
        "nlp_retrieval_reason": retrieval.get("reason"),
    })


# ── Metrics ───────────────────────────────────────────────────────────
@app.get("/api/metrics", tags=["system"])
async def get_metrics() -> JSONResponse:
    """Session and trust-score band distribution metrics for the metrics screen."""
    try:
        from sqlalchemy import func as sqlfunc
        from server.database import SessionLocal, ScreeningSession, ScreeningResult
        import json
        db = SessionLocal()
        try:
            total_sessions = db.query(ScreeningSession).count()
            complete_sessions = db.query(ScreeningSession).filter(
                ScreeningSession.status == "complete"
            ).count()
            results = db.query(ScreeningResult).filter(ScreeningResult.is_final == True).all()
            band_counts: dict = {}
            scores: list = []
            for r in results:
                try:
                    data = json.loads(r.response_json)
                    band = data.get("fusion", {}).get("band", "unknown")
                    score = data.get("fusion", {}).get("trust_score", 50.0)
                    band_counts[band] = band_counts.get(band, 0) + 1
                    scores.append(score)
                except Exception:
                    pass
            avg_score = round(sum(scores) / len(scores), 1) if scores else None
        finally:
            db.close()
        return JSONResponse(content={
            "total_sessions": total_sessions,
            "complete_sessions": complete_sessions,
            "band_distribution": band_counts,
            "average_trust_score": avg_score,
            "total_scored": len(scores),
        })
    except Exception as e:
        return JSONResponse(content={"error": str(e)}, status_code=500)


# ── Dev entry point ───────────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "server.main:app",
        host=config.HOST,
        port=config.PORT,
        reload=True,
        log_level=config.LOG_LEVEL.lower(),
    )
