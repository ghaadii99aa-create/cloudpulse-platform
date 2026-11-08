"""Prometheus metrics: request telemetry for the API itself, and the platform's computed figures as gauges."""
from __future__ import annotations

import logging
import secrets
import time

from fastapi import FastAPI, HTTPException, Request, Response, status
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, Counter, Histogram, generate_latest
from prometheus_client.core import GaugeMetricFamily
from sqlalchemy import func, select

from .models import Alert
from .services import insights

log = logging.getLogger("cloudpulse.metrics")
_API_PREFIX = "/api/v1"
_SKIPPED = {"/metrics", "/healthz", "/readyz"}
_ACTIVE = ("open", "acknowledged")
_UTILIZATION = {"cpu": "cpu_pct", "memory": "memory_pct", "disk": "disk_pct"}


def _route_label(path: str, template: str | None) -> str:
    """Route templates may or may not include the router prefix, depending on the FastAPI version; always report it."""
    if template is None:
        return "unmatched"
    return f"{_API_PREFIX}{template}" if path.startswith(_API_PREFIX) and not template.startswith(_API_PREFIX) else template


class PlatformCollector:
    """Computes gauges at scrape time. Every series carries data_source, so simulated figures stay labeled in Grafana."""

    def __init__(self, app: FastAPI):
        self.app = app

    def collect(self):
        available = GaugeMetricFamily("cloudpulse_data_available", "1 when the platform's dataset could be loaded for this scrape")
        try:
            with self.app.state.database.session_factory() as db:
                ds = self.app.state.store.get(db)
                rows = insights.resource_status(ds, self.app.state.settings)
                fleet = insights.fleet_summary(ds, self.app.state.settings)
                costs = insights.cost_summary(ds)
                alerts = dict(db.execute(select(Alert.severity, func.count()).where(Alert.status.in_(_ACTIVE)).group_by(Alert.severity)).all())
        except Exception as exc:  # a scrape must still report the failure rather than lose all metrics
            log.warning("platform metrics unavailable: %s", exc)
            available.add_metric([], 0)
            yield available
            return
        available.add_metric([], 1)
        yield available

        source = ds.data_source

        def gauge(name: str, doc: str, value: float) -> GaugeMetricFamily:
            family = GaugeMetricFamily(name, doc, labels=["data_source"])
            family.add_metric([source], float(value))
            return family

        yield gauge("cloudpulse_fleet_health_score", "Fleet health score, 0 to 100", fleet["health_score"])
        yield gauge("cloudpulse_fleet_availability_24h_percent", "Fleet availability over the last 24 hours", fleet["availability_24h_pct"])
        yield gauge("cloudpulse_cost_last_30d_usd", "Spend over the last 30 days", costs["last_30d_usd"])
        yield gauge("cloudpulse_cost_month_end_estimate_usd", "Estimated spend for the current month", costs["month_end_estimate_usd"])
        yield gauge("cloudpulse_cost_potential_savings_monthly_usd", "Identified monthly savings", costs["potential_monthly_savings_usd"])

        statuses = GaugeMetricFamily("cloudpulse_resources", "Resources by health status", labels=["status", "data_source"])
        for name, count in fleet["status_counts"].items():
            statuses.add_metric([name, source], count)
        yield statuses

        active = GaugeMetricFamily("cloudpulse_active_alerts", "Active alerts by severity", labels=["severity", "data_source"])
        for severity in ("critical", "warning", "info"):
            active.add_metric([severity, source], alerts.get(severity, 0))
        yield active

        utilization = GaugeMetricFamily("cloudpulse_resource_utilization_percent", "Latest utilization per resource",
                                        labels=["resource", "metric", "data_source"])
        for row in rows:
            for metric, key in _UTILIZATION.items():
                if row[key] is not None:
                    utilization.add_metric([row["name"], metric, source], row[key])
        yield utilization


def install_metrics(app: FastAPI) -> None:
    registry = CollectorRegistry()
    requests = Counter("cloudpulse_http_requests_total", "HTTP requests", ["method", "route", "status"], registry=registry)
    latency = Histogram("cloudpulse_http_request_duration_seconds", "HTTP request duration", ["method", "route"], registry=registry,
                        buckets=(0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10))
    registry.register(PlatformCollector(app))
    app.state.metrics_registry = registry

    @app.middleware("http")
    async def record_request(request: Request, call_next):
        if request.url.path in _SKIPPED:
            return await call_next(request)
        started = time.perf_counter()
        response = await call_next(request)
        route = request.scope.get("route")
        # The route template, never the raw path, so unknown URLs cannot create unbounded label values.
        label = _route_label(request.url.path, getattr(route, "path", None))
        requests.labels(request.method, label, str(response.status_code)).inc()
        latency.labels(request.method, label).observe(time.perf_counter() - started)
        return response

    @app.get("/metrics", tags=["system"], summary="Prometheus metrics", include_in_schema=False)
    def metrics(request: Request):
        token = app.state.settings.metrics_token
        if token:
            supplied = request.headers.get("Authorization", "")
            if not secrets.compare_digest(supplied.encode(), f"Bearer {token}".encode()):
                raise HTTPException(status.HTTP_401_UNAUTHORIZED, "A valid metrics token is required", headers={"WWW-Authenticate": "Bearer"})
        return Response(generate_latest(registry), media_type=CONTENT_TYPE_LATEST)
