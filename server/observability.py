"""Request IDs and Prometheus metrics (upgrade plan, Phase 6).

Request IDs: every HTTP request gets one, taken from a well-formed `X-Request-ID` header
(a proxy's) or made fresh. It goes back in the response header and onto every log line
written while the request runs, so a user's "it said caution at 3:41" can be traced to the
lines that explain it.

Metrics: aggregate counts and timings only. No label ever carries an account, a session,
a phone number or a transcript, because a scrape endpoint is read by people who should
not see any of those. Routes are labelled by their template (`/api/screen/{session_id}`),
never the concrete path.

    python -m server.observability     # smoke test: prints a sample exposition
"""

from __future__ import annotations

import contextvars
import hmac
import logging
import re
import time
import uuid

from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Gauge, Histogram, generate_latest

import config

log = logging.getLogger("satyacheck.observability")

request_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("request_id", default="-")
_VALID_ID = re.compile(r"^[A-Za-z0-9._-]{8,64}$")

REGISTRY = CollectorRegistry()
HTTP_REQUESTS = Counter("satyacheck_http_requests_total", "HTTP requests by route template and status class",
                        ["method", "route", "status"], registry=REGISTRY)
HTTP_SECONDS = Histogram("satyacheck_http_request_seconds", "HTTP request duration by route template",
                         ["method", "route"], registry=REGISTRY,
                         buckets=(0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 120))
INFERENCE_SECONDS = Histogram("satyacheck_inference_seconds", "Time a model call held an inference slot",
                              ["branch"], registry=REGISTRY,
                              buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 4, 8, 16, 32))
INFERENCE_WAIT_SECONDS = Histogram("satyacheck_inference_wait_seconds", "Time a model call waited for a slot",
                                   ["branch"], registry=REGISTRY,
                                   buckets=(0.001, 0.01, 0.1, 0.5, 1, 2, 4, 8, 16))
LIVE_SESSIONS = Gauge("satyacheck_live_sessions", "Live streaming sessions currently admitted", registry=REGISTRY)
LIVE_REFUSED = Counter("satyacheck_live_sessions_refused_total", "Live sessions refused at capacity",
                       registry=REGISTRY)
ASSESSMENTS = Counter("satyacheck_assessments_total", "Live assessments sent, by display band and catch-up",
                      ["band", "catchup"], registry=REGISTRY)
WEBRTC_CALLS = Counter("satyacheck_webrtc_calls_total", "App-to-app calls whose screening agent started",
                       registry=REGISTRY)
COVERAGE_GAP_SECONDS = Counter("satyacheck_coverage_gap_seconds_total",
                               "Seconds of live audio the service could not screen", registry=REGISTRY)


def new_request_id(given: str | None) -> str:
    """The proxy's ID when it is well formed; otherwise a fresh one. Never trust it raw:
    it is echoed into logs and headers."""
    if given and _VALID_ID.match(given):
        return given
    return uuid.uuid4().hex[:16]


class RequestIdFilter(logging.Filter):
    """Adds `request_id` to every record, so a log format can print `%(request_id)s`."""

    def filter(self, record: logging.LogRecord) -> bool:
        record.request_id = request_id_var.get()
        return True


def install_logging() -> None:
    """Put the request ID on every log line. Idempotent."""
    root = logging.getLogger()
    for handler in root.handlers:
        if not any(isinstance(f, RequestIdFilter) for f in handler.filters):
            handler.addFilter(RequestIdFilter())
            handler.setFormatter(logging.Formatter("%(levelname)s [%(request_id)s] %(name)s: %(message)s"))


def _route_template(scope) -> str:
    route = scope.get("route")
    path = getattr(route, "path", None)
    return path if isinstance(path, str) else "unmatched"


class ObservabilityMiddleware:
    """Pure ASGI (not BaseHTTPMiddleware), so WebSockets and streaming responses pass
    through untouched. HTTP only: sockets get their own counters in the live path."""

    def __init__(self, app) -> None:
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = {k.decode("latin-1").lower(): v.decode("latin-1") for k, v in scope.get("headers", [])}
        rid = new_request_id(headers.get("x-request-id"))
        token = request_id_var.set(rid)
        started = time.perf_counter()
        status = [500]

        async def send_with_id(message):
            if message["type"] == "http.response.start":
                status[0] = message["status"]
                message.setdefault("headers", [])
                message["headers"] = list(message["headers"]) + [(b"x-request-id", rid.encode())]
            await send(message)

        try:
            await self.app(scope, receive, send_with_id)
        finally:
            route = _route_template(scope)
            if route != "/metrics":
                method = scope.get("method", "GET")
                HTTP_REQUESTS.labels(method, route, f"{status[0] // 100}xx").inc()
                HTTP_SECONDS.labels(method, route).observe(time.perf_counter() - started)
            request_id_var.reset(token)


def metrics_allowed(authorization: str | None) -> bool:
    """Open in dev without a token; production always needs one."""
    expected = config.METRICS_TOKEN
    if not expected:
        return config.SATYACHECK_ENV != "production"
    given = (authorization or "").removeprefix("Bearer ").strip()
    return hmac.compare_digest(given.encode(), expected.encode())


def exposition() -> tuple[bytes, str]:
    from server.capacity import admission

    LIVE_SESSIONS.set(admission.active)
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    install_logging()
    token = request_id_var.set(new_request_id(None))
    log.info("a log line carries the request id")
    request_id_var.reset(token)
    assert new_request_id("bad id\nX-Injected: 1") != "bad id\nX-Injected: 1"
    HTTP_REQUESTS.labels("GET", "/api/health", "2xx").inc()
    INFERENCE_SECONDS.labels("speaker").observe(0.4)
    body, content_type = exposition()
    print(content_type)
    print("\n".join(line for line in body.decode().splitlines() if line.startswith("satyacheck_http_requests_total")))
    print("[OK] observability smoke test")
