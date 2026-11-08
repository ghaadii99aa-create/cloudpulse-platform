"""Runtime settings, read from environment variables only. No secret has a default value."""
from __future__ import annotations

import logging
import os
import secrets
from dataclasses import dataclass, field
from functools import lru_cache

log = logging.getLogger("cloudpulse.config")


def _bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    return default if raw is None else raw.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    return default if raw in (None, "") else int(raw)


def _float(name: str, default: float) -> float:
    raw = os.getenv(name)
    return default if raw in (None, "") else float(raw)


def normalize_database_url(url: str) -> str:
    """Hosted Postgres providers hand out postgres:// URLs; SQLAlchemy needs an explicit driver."""
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://"):]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://"):]
    return url


@dataclass(frozen=True)
class Settings:
    environment: str = "development"
    database_url: str = "sqlite:///./cloudpulse.db"
    jwt_secret: str = ""
    jwt_expire_minutes: int = 60
    cors_origins: tuple[str, ...] = ("http://localhost:5173",)

    admin_email: str | None = None
    admin_password: str | None = None
    demo_user_email: str | None = None
    demo_user_password: str | None = None
    demo_user_role: str = "viewer"

    seed_on_startup: bool = True
    simulation_days: int = 120
    simulation_end: str | None = None

    cpu_warning_pct: float = 85.0
    cpu_critical_pct: float = 95.0
    memory_warning_pct: float = 85.0
    memory_critical_pct: float = 95.0
    capacity_threshold_pct: float = 85.0
    capacity_alert_days: int = 14

    anthropic_api_key: str | None = field(default=None, repr=False)
    anthropic_model: str = "claude-sonnet-5-5"
    advisor_requests_per_hour: int = 20

    kubernetes_mode: str = "simulated"
    aws_cost_role_arn: str | None = None
    azure_subscription_id: str | None = None

    @property
    def is_production(self) -> bool:
        return self.environment == "production"


@lru_cache
def get_settings() -> Settings:
    environment = os.getenv("ENVIRONMENT", "development")
    jwt_secret = os.getenv("JWT_SECRET", "")
    if not jwt_secret:
        if environment == "production":
            raise RuntimeError("JWT_SECRET must be set in production")
        jwt_secret = secrets.token_urlsafe(48)
        log.warning("JWT_SECRET not set: using a random per-process key (tokens reset on restart)")
    origins = tuple(o.strip() for o in os.getenv("CORS_ORIGINS", "http://localhost:5173").split(",") if o.strip())
    return Settings(
        environment=environment,
        database_url=normalize_database_url(os.getenv("DATABASE_URL", "sqlite:///./cloudpulse.db")),
        jwt_secret=jwt_secret,
        jwt_expire_minutes=_int("JWT_EXPIRE_MINUTES", 60),
        cors_origins=origins,
        admin_email=os.getenv("ADMIN_EMAIL") or None,
        admin_password=os.getenv("ADMIN_PASSWORD") or None,
        demo_user_email=os.getenv("DEMO_USER_EMAIL") or None,
        demo_user_password=os.getenv("DEMO_USER_PASSWORD") or None,
        demo_user_role=os.getenv("DEMO_USER_ROLE", "viewer"),
        seed_on_startup=_bool("SEED_ON_STARTUP", True),
        simulation_days=_int("SIMULATION_DAYS", 120),
        simulation_end=os.getenv("SIMULATION_END") or None,
        cpu_warning_pct=_float("CPU_WARNING_PCT", 85.0),
        cpu_critical_pct=_float("CPU_CRITICAL_PCT", 95.0),
        memory_warning_pct=_float("MEMORY_WARNING_PCT", 85.0),
        memory_critical_pct=_float("MEMORY_CRITICAL_PCT", 95.0),
        capacity_threshold_pct=_float("CAPACITY_THRESHOLD_PCT", 85.0),
        capacity_alert_days=_int("CAPACITY_ALERT_DAYS", 14),
        anthropic_api_key=os.getenv("ANTHROPIC_API_KEY") or None,
        anthropic_model=os.getenv("ANTHROPIC_MODEL", "claude-sonnet-5-5"),
        advisor_requests_per_hour=_int("ADVISOR_REQUESTS_PER_HOUR", 20),
        kubernetes_mode=os.getenv("KUBERNETES_MODE", "simulated"),
        aws_cost_role_arn=os.getenv("AWS_COST_ROLE_ARN") or None,
        azure_subscription_id=os.getenv("AZURE_SUBSCRIPTION_ID") or None,
    )
