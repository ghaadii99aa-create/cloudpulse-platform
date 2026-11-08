"""Database access: seeding the simulated environment, keeping it current, and loading Dataset snapshots."""
from __future__ import annotations

import logging
import threading
import time
from datetime import UTC, datetime

import pandas as pd
from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from cloudpulse_analytics import DATA_SOURCE_LABEL, SimulationConfig, generate_billing, generate_metrics, generate_resources

from .config import Settings
from .database import lock_data_writes
from .models import Alert, CostRecord, MetricSample, Resource, User, utcnow
from .security import hash_password
from .services import alert_rules
from .services.dataset import Dataset

log = logging.getLogger("cloudpulse.repository")

METRIC_WINDOW_HOURS = 30 * 24
METRIC_RETENTION_DAYS = 45
_ACTIVE = ("open", "acknowledged")
_AUTO_RESOLVE = {"cpu", "memory", "availability", "capacity"}


def now_hour() -> pd.Timestamp:
    return pd.Timestamp(datetime.now(UTC).replace(tzinfo=None)).floor("h")


def simulation_end(settings: Settings, now: pd.Timestamp | None = None) -> pd.Timestamp:
    """Metrics end at the current hour (or SIMULATION_END for reproducible runs). Billing ends the day before:
    like real billing exports, a day's cost is only final once the day is over."""
    return pd.Timestamp(settings.simulation_end).floor("h") if settings.simulation_end else (now or now_hour())


# ---------- users ----------

def ensure_user(db: Session, email: str, password: str, role: str, full_name: str) -> User:
    user = db.scalar(select(User).where(User.email == email.lower()))
    if user is None:
        user = User(email=email.lower(), full_name=full_name, password_hash=hash_password(password), role=role)
        db.add(user)
        db.commit()
        log.info("created %s user %s", role, email)
    return user


def seed_users(db: Session, settings: Settings) -> None:
    if settings.admin_email and settings.admin_password:
        ensure_user(db, settings.admin_email, settings.admin_password, "admin", "Administrator")
    if settings.demo_user_email and settings.demo_user_password:
        ensure_user(db, settings.demo_user_email, settings.demo_user_password, settings.demo_user_role, "Demo User")


# ---------- simulated data ----------

def _metric_rows(frame: pd.DataFrame, ids: dict[str, int]) -> list[dict]:
    return [{"resource_id": ids[r.resource], "timestamp": r.timestamp.to_pydatetime(), "cpu_pct": float(r.cpu_pct),
             "memory_pct": float(r.memory_pct), "disk_pct": float(r.disk_pct), "network_mbps": float(r.network_mbps),
             "available": bool(r.available), "data_source": r.data_source} for r in frame.itertuples(index=False)]


def _cost_rows(frame: pd.DataFrame, ids: dict[str, int]) -> list[dict]:
    return [{"resource_id": ids[r.resource], "date": r.date.date(), "cost_usd": float(r.cost_usd), "data_source": r.data_source}
            for r in frame.itertuples(index=False)]


def _resource_ids(db: Session) -> dict[str, int]:
    return dict(db.execute(select(Resource.name, Resource.id)).all())


def seed_simulation(db: Session, settings: Settings, now: pd.Timestamp | None = None) -> bool:
    """Populate an empty database with the simulated environment. Returns False if data already exists."""
    if db.scalar(select(func.count()).select_from(Resource)):
        return False
    end = simulation_end(settings, now)
    for item in generate_resources().itertuples(index=False):
        db.add(Resource(name=item.resource, service=item.service, kind=item.kind, environment=item.environment,
                        hourly_usd=item.hourly_usd, attached=bool(item.attached), data_source=item.data_source))
    db.flush()
    ids = _resource_ids(db)
    billing = generate_billing(SimulationConfig(days=settings.simulation_days, end=str(end.normalize() - pd.Timedelta(days=1))))
    metrics = generate_metrics(SimulationConfig(end=str(end)), hours=METRIC_WINDOW_HOURS)
    db.execute(insert(CostRecord), _cost_rows(billing, ids))
    db.execute(insert(MetricSample), _metric_rows(metrics, ids))
    db.commit()
    log.info("seeded simulated environment: %d resources, %d cost rows, %d metric rows", len(ids), len(billing), len(metrics))
    return True


def reseed_if_fleet_changed(db: Session, settings: Settings) -> bool:
    """A new simulator fleet can't be appended to old rows, so replace them. Never touches real provider data."""
    rows = db.execute(select(Resource.name, Resource.provider)).all()
    if not rows or any(provider != "simulated" for _, provider in rows):
        return False
    if {name for name, _ in rows} == set(generate_resources()["resource"]):
        return False
    log.info("simulated fleet definition changed: regenerating simulated data")
    reset_simulation(db, settings)
    return True


def advance_simulation(db: Session, settings: Settings, now: pd.Timestamp | None = None) -> dict:
    """Append simulated hours and days that have elapsed since the last write, so the demo stays current."""
    if settings.simulation_end:
        return {"metrics_added": 0, "costs_added": 0}
    end = now or now_hour()
    lock_data_writes(db)
    ids = {name: rid for name, rid in db.execute(select(Resource.name, Resource.id).where(Resource.provider == "simulated")).all()}
    if not ids:
        return {"metrics_added": 0, "costs_added": 0}
    latest_ts = db.scalar(select(func.max(MetricSample.timestamp)))
    latest_day = db.scalar(select(func.max(CostRecord.date)))
    added = {"metrics_added": 0, "costs_added": 0}
    if latest_ts is not None and pd.Timestamp(latest_ts) < end:
        metrics = generate_metrics(SimulationConfig(end=str(end)), hours=METRIC_WINDOW_HOURS)
        fresh = metrics[(metrics["timestamp"] > pd.Timestamp(latest_ts)) & metrics["resource"].isin(ids)]
        if not fresh.empty:
            db.execute(insert(MetricSample), _metric_rows(fresh, ids))
            added["metrics_added"] = len(fresh)
        db.execute(delete(MetricSample).where(MetricSample.timestamp < (end - pd.Timedelta(days=METRIC_RETENTION_DAYS)).to_pydatetime()))
    billing_end = end.normalize() - pd.Timedelta(days=1)
    if latest_day is not None and pd.Timestamp(latest_day) < billing_end:
        billing = generate_billing(SimulationConfig(days=settings.simulation_days, end=str(billing_end)))
        fresh = billing[(billing["date"] > pd.Timestamp(latest_day)) & billing["resource"].isin(ids)]
        if not fresh.empty:
            db.execute(insert(CostRecord), _cost_rows(fresh, ids))
            added["costs_added"] = len(fresh)
    db.commit()
    if any(added.values()):
        log.info("advanced simulation: %s", added)
    return added


# ---------- dataset snapshots ----------

class DatasetStore:
    """Caches the Dataset per data version; advances the simulation at most once a minute."""

    def __init__(self, settings: Settings, advance_interval_s: float = 60.0):
        self.settings = settings
        self.advance_interval_s = advance_interval_s
        self._lock = threading.Lock()
        self._dataset: Dataset | None = None
        self._last_advance = 0.0
        self._alerts_version: tuple | None = None

    def _version(self, db: Session) -> tuple:
        m = db.execute(select(func.count(MetricSample.id), func.max(MetricSample.timestamp))).one()
        c = db.execute(select(func.count(CostRecord.id), func.max(CostRecord.date))).one()
        r = db.scalar(select(func.count(Resource.id)))
        return (tuple(m), tuple(c), r)

    def _load(self, db: Session, version: tuple) -> Dataset:
        resources = pd.DataFrame(db.execute(select(
            Resource.name.label("resource"), Resource.service, Resource.kind, Resource.environment, Resource.provider,
            Resource.region, Resource.hourly_usd, Resource.attached, Resource.data_source).order_by(Resource.id)).mappings().all())
        billing = pd.DataFrame(db.execute(select(
            CostRecord.date, Resource.name.label("resource"), Resource.service, Resource.environment, CostRecord.cost_usd,
            CostRecord.data_source).join(Resource)).mappings().all())
        metrics = pd.DataFrame(db.execute(select(
            MetricSample.timestamp, Resource.name.label("resource"), MetricSample.cpu_pct, MetricSample.memory_pct,
            MetricSample.disk_pct, MetricSample.network_mbps, MetricSample.available, MetricSample.data_source)
            .join(Resource)).mappings().all())
        return Dataset.from_frames(resources, billing, metrics, version)

    def get(self, db: Session) -> Dataset:
        with self._lock:
            if time.monotonic() - self._last_advance >= self.advance_interval_s:
                advance_simulation(db, self.settings)
                self._last_advance = time.monotonic()
            version = self._version(db)
            if self._dataset is None or self._dataset.version != version:
                if version[0][0] == 0 or version[1][0] == 0:
                    raise LookupError("no infrastructure data loaded yet")
                self._dataset = self._load(db, version)
            if self._alerts_version != version:
                sync_alerts(db, self._dataset, self.settings)
                self._alerts_version = version
            return self._dataset

    def invalidate(self) -> None:
        with self._lock:
            self._dataset, self._alerts_version, self._last_advance = None, None, 0.0


# ---------- alerts ----------

def sync_alerts(db: Session, ds: Dataset, settings: Settings) -> dict:
    candidates = {c["fingerprint"]: c for c in alert_rules.evaluate(ds, settings)}
    lock_data_writes(db)
    active = {a.fingerprint: a for a in db.scalars(select(Alert).where(Alert.status.in_(_ACTIVE)))}
    resolved_fps = set(db.scalars(select(Alert.fingerprint).where(Alert.status == "resolved",
                                                                   Alert.fingerprint.in_(list(candidates) or [""]))))
    now = utcnow()
    summary = {"created": 0, "updated": 0, "resolved": 0}
    for fp, cand in candidates.items():
        alert = active.get(fp)
        if alert is not None:
            for key in ("severity", "title", "message", "value", "threshold", "observed_at"):
                setattr(alert, key, cand[key])
            alert.last_seen = now
            summary["updated"] += 1
        elif cand["category"] == "cost" and fp in resolved_fps:
            continue  # a resolved cost incident refers to a past day; do not reopen it
        else:
            db.add(Alert(**cand, status="open", first_seen=now, last_seen=now))
            summary["created"] += 1
    for fp, alert in active.items():
        if fp not in candidates and alert.category in _AUTO_RESOLVE:
            alert.status, alert.resolved_at = "resolved", now
            alert.message += " Auto-resolved: condition cleared."
            summary["resolved"] += 1
    db.commit()
    return summary


def alert_to_dict(alert: Alert) -> dict:
    return {c: getattr(alert, c) for c in ("id", "fingerprint", "category", "severity", "status", "resource", "title", "message",
                                           "value", "threshold", "observed_at", "first_seen", "last_seen", "acknowledged_by",
                                           "acknowledged_at", "resolved_at", "data_source")}


def active_alerts(db: Session) -> list[dict]:
    order = {"critical": 0, "warning": 1, "info": 2}
    alerts = [alert_to_dict(a) for a in db.scalars(select(Alert).where(Alert.status.in_(_ACTIVE)))]
    return sorted(alerts, key=lambda a: (order.get(a["severity"], 3), -a["observed_at"].timestamp()))


def data_meta(db: Session) -> dict:
    sources = sorted(set(db.scalars(select(Resource.data_source))))
    return {"data_sources": sources, "simulated": DATA_SOURCE_LABEL in sources,
            "last_metric_at": db.scalar(select(func.max(MetricSample.timestamp))),
            "last_cost_date": db.scalar(select(func.max(CostRecord.date)))}


def reset_simulation(db: Session, settings: Settings) -> None:
    """Admin action: wipe simulated data and alerts, then reseed."""
    db.execute(delete(Alert))
    db.execute(delete(MetricSample))
    db.execute(delete(CostRecord))
    db.execute(delete(Resource))
    db.commit()
    seed_simulation(db, settings)

