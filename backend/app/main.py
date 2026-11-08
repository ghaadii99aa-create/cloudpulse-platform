"""CloudPulse API: application factory, middleware and error handling."""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from starlette.exceptions import HTTPException as StarletteHTTPException

from . import __version__
from .config import Settings, get_settings
from .database import Database
from .metrics import install_metrics
from .repository import DatasetStore, reseed_if_fleet_changed, seed_simulation, seed_users
from .routers import alerts, auth, finops, insights, operations
from .security import SlidingWindowLimiter
from .webapp import install_webapp

log = logging.getLogger("cloudpulse")

DESCRIPTION = """
CloudPulse is a cloud operations, observability and FinOps API.

**Data source.** Unless a real integration is configured, every figure comes from a deterministic
simulated environment. Responses carry a `data_source` field (`SIMULATED`, `SIMULATED_LIVE`, `AWS`,
`AZURE`, `LIVE_KUBERNETES`) so simulated numbers are never mistaken for real ones.

**Auth.** Obtain a bearer token from `POST /api/v1/auth/login` (JSON) or the Authorize button
(OAuth2 password flow). Roles: `viewer` (read), `engineer` (+ alert actions), `admin` (+ users, reseed).

**Errors.** Non-validation errors return `{"error": {"code", "message"}}` with a matching HTTP status.
"""

TAGS = [
    {"name": "auth", "description": "Login, current user and user administration"},
    {"name": "dashboard", "description": "Executive overview"},
    {"name": "infrastructure", "description": "Resource health and metrics"},
    {"name": "finops", "description": "Spend analysis, anomalies and savings"},
    {"name": "analytics", "description": "Forecasts, usage anomalies and capacity"},
    {"name": "alerts", "description": "Alert history and lifecycle"},
    {"name": "kubernetes", "description": "Cluster health"},
    {"name": "topology", "description": "Infrastructure dependency map"},
    {"name": "advisor", "description": "AI Cloud Advisor with labeled fallback mode"},
    {"name": "reports", "description": "PDF reports"},
    {"name": "system", "description": "Health, version and integrations"},
]


def _error(status_code: int, code: str, message: str, headers: dict | None = None) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status_code, headers=headers)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        log.info("database backend: %s", app.state.database.engine.dialect.name)  # never log the URL, it holds the password
        with app.state.database.startup_lock():
            app.state.database.create_all()
            with app.state.database.session_factory() as db:
                seed_users(db, settings)
                if settings.seed_on_startup:
                    reseed_if_fleet_changed(db, settings)
                    seed_simulation(db, settings)
        yield
        app.state.database.engine.dispose()

    app = FastAPI(title="CloudPulse API", version=__version__, description=DESCRIPTION, openapi_tags=TAGS, lifespan=lifespan,
                  docs_url="/api/docs", redoc_url="/api/redoc", openapi_url="/api/openapi.json")
    app.state.settings = settings
    app.state.database = Database(settings.database_url)
    app.state.store = DatasetStore(settings)
    app.state.login_limiter = SlidingWindowLimiter(limit=5, window_seconds=300)
    app.state.advisor_limiter = SlidingWindowLimiter(limit=settings.advisor_requests_per_hour, window_seconds=3600)

    app.add_middleware(CORSMiddleware, allow_origins=list(settings.cors_origins), allow_credentials=False,
                       allow_methods=["GET", "POST", "PATCH"], allow_headers=["Authorization", "Content-Type"])

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        started = time.perf_counter()
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        log.info("%s %s %s %.0fms id=%s", request.method, request.url.path, response.status_code,
                 (time.perf_counter() - started) * 1000, request_id)
        return response

    @app.exception_handler(StarletteHTTPException)
    async def http_error(_: Request, exc: StarletteHTTPException):
        codes = {400: "bad_request", 401: "unauthorized", 403: "forbidden", 404: "not_found", 409: "conflict",
                 405: "method_not_allowed", 429: "rate_limited", 503: "unavailable"}
        return _error(exc.status_code, codes.get(exc.status_code, "error"), str(exc.detail), getattr(exc, "headers", None))

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        details = [{"field": ".".join(str(p) for p in e["loc"][1:]), "message": e["msg"]} for e in exc.errors()]
        return JSONResponse({"error": {"code": "validation_error", "message": "Request validation failed", "details": details}},
                            status_code=422)

    @app.exception_handler(ValueError)
    async def value_error(_: Request, exc: ValueError):
        return _error(400, "bad_request", str(exc))

    @app.exception_handler(Exception)
    async def unhandled(_: Request, exc: Exception):
        log.exception("unhandled error: %s", exc)
        return _error(500, "internal_error", "An unexpected error occurred")

    install_metrics(app)

    prefix = "/api/v1"
    for module in (auth, operations, finops, alerts, insights):
        app.include_router(module.router, prefix=prefix)

    @app.get("/healthz", tags=["system"], summary="Liveness probe")
    def healthz():
        return {"status": "ok", "version": __version__}

    @app.get("/readyz", tags=["system"], summary="Readiness probe (database reachable)")
    def readyz():
        try:
            with app.state.database.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
        except Exception:
            return _error(503, "unavailable", "database unreachable")
        return {"status": "ready"}

    if settings.web_dist:  # last, because its catch-all route must not shadow the API
        install_webapp(app, settings.web_dist)

    return app


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
app = create_app()
