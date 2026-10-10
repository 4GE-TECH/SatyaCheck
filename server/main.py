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

from fastapi import Depends, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response

import config
from server.auth import current_owner
from server.mock_router import router as mock_router

from server.persons_router import router as persons_router
from server.enroll_router  import router as enroll_router
from server.screen_router  import router as screen_router
from server.report_router  import router as report_router
from server.demo_router    import router as demo_router
from server.ws_router      import router as ws_router
from server.live_router    import router as live_router
from server.evidence_router import router as evidence_router
from server.account_router import router as account_router
from server.ws_v2_router import router as ws_v2_router

logging.basicConfig(level=config.LOG_LEVEL)
log = logging.getLogger("satyacheck.server")

from server.observability import ObservabilityMiddleware, install_logging  # noqa: E402

install_logging()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown lifecycle."""
    log.info("SatyaCheck server starting up…")
    log.info(f"  MODELS_DIR : {config.MODELS_DIR}")
    log.info(f"  DB_PATH    : {config.DB_PATH}")
    log.info(f"  USE_REAL_SPEAKER={config.USE_REAL_SPEAKER} | USE_REAL_SPOOF={config.USE_REAL_SPOOF} | USE_REAL_NLP={config.USE_REAL_NLP}")

    from server.auth import log_mode
    log_mode()
    if config.WARM_MODELS:
        import threading

        from server.capacity import warm_models
        threading.Thread(target=warm_models, name="warm-models", daemon=True).start()
        log.info("  warming models in the background; /api/ready is 503 until done")

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
    from server import webrtc_screening

    if webrtc_screening.manager is not None:
        await webrtc_screening.manager.stop_all()
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

# Request IDs and Prometheus timings. Added last, so it wraps CORS and sees every request.
app.add_middleware(ObservabilityMiddleware)

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
app.include_router(account_router)
app.include_router(ws_v2_router)


from server.transport_runner import _RetainingRunner, make_retaining_runner  # noqa: E402,F401


def _exotel_runner():
    """A SessionRunner for one Exotel call: no app socket to talk to, so the dispatcher
    carries the guardian and report sinks only. A telephony stream has no user token: its
    calls belong to EXOTEL_OWNER_ID (the dev account in dev mode)."""
    return make_retaining_runner(config.EXOTEL_OWNER_ID or None)


def mount_exotel(target: FastAPI, runner_factory=None) -> bool:
    """Mount the Exotel Stream route when config.ENABLE_EXOTEL is on. Returns whether it did."""
    if not config.ENABLE_EXOTEL:
        return False
    if config.AUTH_MODE != "dev" and not config.EXOTEL_OWNER_ID:
        log.error("  Exotel route NOT mounted: set EXOTEL_OWNER_ID to the account that owns "
                  "telephony calls (jwt mode has no dev account to fall back on)")
        return False
    from acquisition.api import build_exotel_router

    target.include_router(build_exotel_router(runner_factory or _exotel_runner))
    log.info(f"  Exotel stream route mounted at {config.EXOTEL_WS_PATH}")
    return True


mount_exotel(app)


def mount_webrtc(target: FastAPI) -> bool:
    """Mount the app-to-app call endpoints when ENABLE_WEBRTC is on. Refuses (logged) in dev
    auth mode: a call needs two real, distinct accounts, never the shared dev account."""
    if not config.ENABLE_WEBRTC:
        return False
    if config.AUTH_MODE != "jwt":
        log.error("  WebRTC calls NOT mounted: they need AUTH_MODE=jwt (two real accounts; the dev "
                  "account would give both phones the same identity)")
        return False
    if not (config.LIVEKIT_API_KEY and config.LIVEKIT_API_SECRET):
        log.error("  WebRTC calls NOT mounted: set LIVEKIT_API_KEY and LIVEKIT_API_SECRET")
        return False
    from server.webrtc_router import router as webrtc_router

    target.include_router(webrtc_router)
    log.info(f"  WebRTC calls mounted at /api/webrtc (LiveKit {config.LIVEKIT_URL}, "
             f"agent via {config.LIVEKIT_AGENT_URL}, at most {config.WEBRTC_MAX_CALLS} calls)")
    return True


mount_webrtc(app)


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
        "nlp_retrieval_available": retrieval["available"],
        "nlp_retrieval_reason": retrieval.get("reason"),
    })


@app.get("/api/ready", tags=["system"])
async def ready_check() -> JSONResponse:
    """503 until the models are warm (WARM_MODELS), so no call lands on a cold server."""
    from server.capacity import readiness

    state = readiness()
    return JSONResponse(content=state, status_code=200 if state["ready"] else 503)


# ── Metrics ───────────────────────────────────────────────────────────
@app.get("/api/metrics", tags=["system"])
async def get_metrics(owner_id: str = Depends(current_owner)) -> JSONResponse:
    """The calling account's session and trust-score band distribution."""
    try:
        from server.database import owner_session, ScreeningSession, ScreeningResult
        import json
        db = owner_session(owner_id)
        try:
            total_sessions = db.query(ScreeningSession).filter(ScreeningSession.owner_id == owner_id).count()
            complete_sessions = db.query(ScreeningSession).filter(
                ScreeningSession.owner_id == owner_id, ScreeningSession.status == "complete"
            ).count()
            results = db.query(ScreeningResult).filter(
                ScreeningResult.owner_id == owner_id, ScreeningResult.is_final == True).all()
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


@app.get("/metrics", include_in_schema=False)
async def prometheus_metrics(request: Request) -> Response:
    """Prometheus scrape: aggregate counts and timings, no account or call data."""
    from server.observability import exposition, metrics_allowed

    if not metrics_allowed(request.headers.get("authorization")):
        return Response(status_code=401 if config.METRICS_TOKEN else 404)
    body, content_type = exposition()
    return Response(content=body, media_type=content_type)


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
