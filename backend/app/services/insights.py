"""Infrastructure health, utilization and cost views derived from a Dataset. Pure functions, no I/O."""
from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from cloudpulse_analytics import forecast_series

from ..config import Settings
from .dataset import Dataset

HEALTH_SCORE_METHOD = "100 x (healthy + 0.5 x warning) / monitored resources, using the latest hour of telemetry"


def _r(value, digits: int = 2):
    return None if value is None or (isinstance(value, float) and np.isnan(value)) else round(float(value), digits)


def resource_status(ds: Dataset, settings: Settings) -> list[dict]:
    latest = ds.metrics[ds.metrics["timestamp"] == ds.as_of].set_index("resource")
    day = ds.metrics[ds.metrics["timestamp"] > ds.as_of - pd.Timedelta(hours=24)]
    availability = day.groupby("resource")["available"].mean() * 100
    month_cost = ds.billing[ds.billing["date"] > ds.billing_as_of - pd.Timedelta(days=30)].groupby("resource")["cost_usd"].sum()
    rows = []
    for item in ds.resources.itertuples(index=False):
        entry = {"name": item.resource, "service": item.service, "kind": item.kind, "environment": item.environment,
                 "provider": getattr(item, "provider", "simulated"), "region": getattr(item, "region", None),
                 "attached": bool(item.attached), "cost_30d_usd": _r(month_cost.get(item.resource, 0.0)),
                 "data_source": item.data_source}
        if item.resource not in latest.index:
            entry.update(status="no_telemetry", reasons=["Resource does not report host metrics"], cpu_pct=None,
                         memory_pct=None, disk_pct=None, network_mbps=None, available=None, availability_24h_pct=None)
            rows.append(entry)
            continue
        m = latest.loc[item.resource]
        reasons, status = [], "healthy"
        checks = [("CPU", m.cpu_pct, settings.cpu_warning_pct, settings.cpu_critical_pct),
                  ("Memory", m.memory_pct, settings.memory_warning_pct, settings.memory_critical_pct)]
        for label, value, warn, crit in checks:
            if value >= crit:
                status = "critical"
                reasons.append(f"{label} {value:.1f}% >= {crit:.0f}%")
            elif value >= warn:
                status = "warning" if status != "critical" else status
                reasons.append(f"{label} {value:.1f}% >= {warn:.0f}%")
        if m.disk_pct >= settings.capacity_threshold_pct:
            status = "warning" if status == "healthy" else status
            reasons.append(f"Disk {m.disk_pct:.1f}% >= {settings.capacity_threshold_pct:.0f}%")
        if not m.available:
            status = "critical"
            reasons.append("Health check failed in the latest hour")
        elif availability.get(item.resource, 100) < 100:
            status = "warning" if status == "healthy" else status
            reasons.append(f"Availability {availability[item.resource]:.1f}% over 24h")
        entry.update(status=status, reasons=reasons, cpu_pct=_r(m.cpu_pct), memory_pct=_r(m.memory_pct),
                     disk_pct=_r(m.disk_pct), network_mbps=_r(m.network_mbps), available=bool(m.available),
                     availability_24h_pct=_r(availability.get(item.resource), 2))
        rows.append(entry)
    return rows


def fleet_summary(ds: Dataset, settings: Settings) -> dict:
    statuses = resource_status(ds, settings)
    monitored = [s for s in statuses if s["status"] != "no_telemetry"]
    counts = {k: sum(1 for s in statuses if s["status"] == k) for k in ("healthy", "warning", "critical", "no_telemetry")}
    score = 100 * (counts["healthy"] + 0.5 * counts["warning"]) / len(monitored) if monitored else None
    day = ds.metrics[ds.metrics["timestamp"] > ds.as_of - pd.Timedelta(hours=24)]
    return {
        "as_of": ds.as_of.isoformat(), "data_source": ds.data_source,
        "resource_count": len(statuses), "monitored_count": len(monitored), "status_counts": counts,
        "health_score": _r(score, 1), "health_score_method": HEALTH_SCORE_METHOD,
        "avg_cpu_pct": _r(np.mean([s["cpu_pct"] for s in monitored]) if monitored else None),
        "avg_memory_pct": _r(np.mean([s["memory_pct"] for s in monitored]) if monitored else None),
        "avg_disk_pct": _r(np.mean([s["disk_pct"] for s in monitored]) if monitored else None),
        "total_network_mbps": _r(sum(s["network_mbps"] for s in monitored)),
        "availability_24h_pct": _r(day["available"].mean() * 100 if not day.empty else None, 3),
    }


def resource_series(ds: Dataset, name: str, hours: int = 168, resolution: str = "hour") -> list[dict]:
    frame = ds.metrics[(ds.metrics["resource"] == name) & (ds.metrics["timestamp"] > ds.as_of - pd.Timedelta(hours=hours))]
    columns = ["cpu_pct", "memory_pct", "disk_pct", "network_mbps", "available"]
    frame = frame.set_index("timestamp")[columns]
    if resolution == "day":
        frame = frame.resample("D").mean().dropna()
    return [{"timestamp": ts.isoformat(), **{c: _r(row[c], 3 if c == "available" else 2) for c in columns}}
            for ts, row in frame.iterrows()]


def utilization_trend(ds: Dataset, days: int = 30) -> list[dict]:
    recent = ds.metrics[ds.metrics["timestamp"] > ds.as_of - pd.Timedelta(days=days)].set_index("timestamp")
    daily = recent[["cpu_pct", "memory_pct", "disk_pct"]].resample("D").mean()
    daily["network_mbps"] = recent["network_mbps"].resample("D").sum() / 24
    daily["availability_pct"] = recent["available"].resample("D").mean() * 100
    return [{"date": ts.date().isoformat(), **{c: _r(v) for c, v in row.items()}} for ts, row in daily.dropna().iterrows()]


def live_snapshot(ds: Dataset, now: datetime) -> dict:
    """A simulated 'current' reading: last week's same-hour baseline plus seeded noise, labeled as such."""
    seed = int(now.timestamp() // 15)  # new reading every 15 seconds, reproducible within the window
    rng = np.random.default_rng(seed)
    week = ds.metrics[ds.metrics["timestamp"] > ds.as_of - pd.Timedelta(days=7)]
    same_hour = week[week["timestamp"].dt.hour == now.hour]
    base = same_hour.groupby("resource")[["cpu_pct", "memory_pct", "disk_pct", "network_mbps"]].mean()
    readings = []
    for resource, row in base.iterrows():
        jitter = rng.normal(1, [0.06, 0.015, 0.002, 0.12])
        values = np.clip(row.to_numpy() * jitter, 0, [100, 100, 100, np.inf])
        readings.append({"resource": resource, "cpu_pct": _r(values[0]), "memory_pct": _r(values[1]),
                         "disk_pct": _r(values[2]), "network_mbps": _r(values[3])})
    return {"timestamp": now.replace(microsecond=0).isoformat(), "data_source": "SIMULATED_LIVE",
            "method": "Baseline = same hour over the last 7 simulated days; noise reseeded every 15 seconds",
            "readings": readings}


def cost_summary(ds: Dataset) -> dict:
    end = ds.billing_as_of
    daily = ds.billing.groupby("date")["cost_usd"].sum()
    last_30 = float(daily[daily.index > end - pd.Timedelta(days=30)].sum())
    prev_30 = float(daily[(daily.index <= end - pd.Timedelta(days=30)) & (daily.index > end - pd.Timedelta(days=60))].sum())
    month_start = end.replace(day=1)
    month_to_date = float(daily[daily.index >= month_start].sum())
    days_in_month = month_start.days_in_month
    remaining = days_in_month - end.day
    month_end_estimate = month_to_date
    if remaining > 0:
        month_end_estimate += float(forecast_series(daily, horizon=remaining)["forecast"].sum())
    savings = sum(r["estimated_monthly_savings_usd"] for r in ds.recommendations)
    top = ds.breakdown("service").iloc[0]
    return {
        "as_of": end.date().isoformat(), "data_source": ds.data_source, "currency": "USD",
        "last_30d_usd": round(last_30, 2), "previous_30d_usd": round(prev_30, 2),
        "change_pct": round((last_30 - prev_30) / prev_30 * 100, 2) if prev_30 else None,
        "daily_average_usd": round(last_30 / 30, 2),
        "month": month_start.strftime("%Y-%m"), "month_to_date_usd": round(month_to_date, 2),
        "month_end_estimate_usd": round(month_end_estimate, 2),
        "next_30d_forecast": ds.monthly_forecast,
        "potential_monthly_savings_usd": round(savings, 2),
        "top_service": {"service": top["service"], "cost_usd": float(top["cost_usd"]), "share_pct": float(top["share_pct"])},
        "cost_spike_count_30d": int((ds.cost_spikes["date"] > end - pd.Timedelta(days=30)).sum()) if not ds.cost_spikes.empty else 0,
    }


def daily_costs(ds: Dataset, days: int = 90, by: str = "service") -> dict:
    if by not in {"service", "environment"}:
        raise ValueError("by must be service or environment")
    recent = ds.billing[ds.billing["date"] > ds.billing_as_of - pd.Timedelta(days=days)]
    pivot = recent.pivot_table(index="date", columns=by, values="cost_usd", aggfunc="sum", fill_value=0).round(2)
    return {"by": by, "series": list(pivot.columns), "data_source": ds.data_source,
            "points": [{"date": ts.date().isoformat(), "total": round(float(row.sum()), 2), **{k: float(v) for k, v in row.items()}}
                       for ts, row in pivot.iterrows()]}


def cost_forecast(ds: Dataset, horizon: int = 30, history_days: int = 60) -> dict:
    daily = ds.billing.groupby("date")["cost_usd"].sum()
    result = forecast_series(daily, horizon=horizon)
    return {
        "data_source": ds.data_source, "horizon_days": horizon, "model": "Huber regression: linear trend + weekday effects",
        "interval": "90% empirical prediction interval", "backtest": ds.cost_backtest,
        "history": [{"date": ts.date().isoformat(), "cost_usd": round(float(v), 2)} for ts, v in daily.tail(history_days).items()],
        "forecast": [{"date": ts.date().isoformat(), "forecast": round(float(r.forecast), 2), "lower": round(float(r.lower), 2),
                      "upper": round(float(r.upper), 2)} for ts, r in result.iterrows()],
        "total": {"forecast": round(float(result["forecast"].sum()), 2), "lower": round(float(result["lower"].sum()), 2),
                  "upper": round(float(result["upper"].sum()), 2)},
    }


def utilization_forecast(ds: Dataset, resource: str, metric: str = "cpu_pct", horizon: int = 14) -> dict:
    if metric not in {"cpu_pct", "memory_pct", "disk_pct"}:
        raise ValueError("metric must be cpu_pct, memory_pct or disk_pct")
    frame = ds.metrics[ds.metrics["resource"] == resource]
    if frame.empty:
        raise LookupError(f"no metrics for resource {resource!r}")
    daily = frame.set_index("timestamp")[metric].resample("D").mean().dropna()
    result = forecast_series(daily, horizon=horizon)
    return {
        "resource": resource, "metric": metric, "horizon_days": horizon, "data_source": ds.data_source,
        "history": [{"date": ts.date().isoformat(), "value": round(float(v), 2)} for ts, v in daily.items()],
        "forecast": [{"date": ts.date().isoformat(), "forecast": round(min(float(r.forecast), 100), 2),
                      "lower": round(min(float(r.lower), 100), 2), "upper": round(min(float(r.upper), 100), 2)}
                     for ts, r in result.iterrows()],
    }


def records(frame: pd.DataFrame) -> list[dict]:
    """DataFrame -> JSON-safe dicts (timestamps to ISO strings, numpy scalars to Python)."""
    out = []
    for row in frame.to_dict(orient="records"):
        out.append({k: (v.isoformat() if isinstance(v, pd.Timestamp) else v.item() if hasattr(v, "item") else v)
                    for k, v in row.items()})
    return out
