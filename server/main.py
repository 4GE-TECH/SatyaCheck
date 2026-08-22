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
        from server.database import init_db
        init_db()
        log.info("  DB init: OK")
    except ImportError:
        log.warning("  server.database not yet available — skipping DB init (Block 0 mode)")

    yield
    log.info("SatyaCheck server shutting down.")


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


# ── Health ────────────────────────────────────────────────────────────
@app.get("/api/health", tags=["system"])
async def health_check() -> JSONResponse:
    return JSONResponse(content={
        "status": "ok",
        "version": app.version,
        "use_real_speaker": config.USE_REAL_SPEAKER,
        "use_real_spoof": config.USE_REAL_SPOOF,
        "use_real_nlp": config.USE_REAL_NLP,
        "use_real_fusion": config.USE_REAL_FUSION,
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
