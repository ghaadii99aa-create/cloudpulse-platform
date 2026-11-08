"""Turn the current dataset into alert candidates. Each candidate has a stable fingerprint so
re-evaluation updates an existing alert instead of creating duplicates."""
from __future__ import annotations

import pandas as pd

from ..config import Settings
from .dataset import Dataset


def _candidate(fingerprint, category, severity, resource, title, message, value, threshold, observed_at, source):
    return {"fingerprint": fingerprint, "category": category, "severity": severity, "resource": resource, "title": title,
            "message": message, "value": None if value is None else round(float(value), 2),
            "threshold": None if threshold is None else float(threshold),
            "observed_at": pd.Timestamp(observed_at).to_pydatetime(), "data_source": source}


def evaluate(ds: Dataset, settings: Settings, cost_lookback_days: int = 30) -> list[dict]:
    found: list[dict] = []
    source = ds.data_source
    latest = ds.metrics[ds.metrics["timestamp"] == ds.as_of]

    for row in latest.itertuples(index=False):
        for metric, label, warn, crit in (("cpu_pct", "CPU", settings.cpu_warning_pct, settings.cpu_critical_pct),
                                          ("memory_pct", "Memory", settings.memory_warning_pct, settings.memory_critical_pct)):
            value = getattr(row, metric)
            if value >= warn:
                severity = "critical" if value >= crit else "warning"
                limit = crit if severity == "critical" else warn
                found.append(_candidate(f"{metric}:{row.resource}", "cpu" if metric == "cpu_pct" else "memory", severity,
                                        row.resource, f"High {label if metric == 'cpu_pct' else label.lower()} usage on {row.resource}",
                                        f"{label} utilization is {value:.1f}% (threshold {limit:.0f}%).", value, limit,
                                        row.timestamp, source))

    day = ds.metrics[ds.metrics["timestamp"] > ds.as_of - pd.Timedelta(hours=24)]
    for resource, group in day.groupby("resource"):
        down = int((group["available"] == 0).sum())
        if down == 0:
            continue
        currently_down = int(group.sort_values("timestamp")["available"].iloc[-1]) == 0
        availability = group["available"].mean() * 100
        found.append(_candidate(f"availability:{resource}", "availability", "critical" if currently_down else "warning",
                                resource, f"Availability degraded on {resource}",
                                f"{down} failed hourly health check(s) in the last 24h; availability {availability:.2f}%."
                                + (" Currently failing." if currently_down else ""), availability, 100.0,
                                group["timestamp"].max(), source))

    spikes = ds.cost_spikes
    if not spikes.empty:
        recent = spikes[spikes["date"] > ds.billing_as_of - pd.Timedelta(days=cost_lookback_days)]
        for spike in recent.itertuples(index=False):
            severity = "critical" if spike.cost_usd >= 3 * spike.expected_usd else "warning"
            found.append(_candidate(f"cost:{spike.resource}:{spike.date.date().isoformat()}", "cost", severity, spike.resource,
                                    f"Unexpected cost increase on {spike.resource}",
                                    f"Spent ${spike.cost_usd:,.2f} on {spike.date.date()} vs ${spike.expected_usd:,.2f} expected "
                                    f"(+${spike.excess_usd:,.2f}, robust z-score {spike.score}).",
                                    spike.cost_usd, spike.expected_usd, spike.date, source))

    risks = ds.capacity_risks
    if not risks.empty:
        soon = risks[risks["days_to_threshold"] <= settings.capacity_alert_days]
        for risk in soon.itertuples(index=False):
            label = {"cpu_pct": "CPU", "memory_pct": "Memory", "disk_pct": "Disk"}[risk.metric]
            found.append(_candidate(f"capacity:{risk.resource}:{risk.metric}", "capacity",
                                    "critical" if risk.days_to_threshold <= 3 else "warning", risk.resource,
                                    f"{label} capacity risk on {risk.resource}",
                                    f"Projected to reach {settings.capacity_threshold_pct:.0f}% in {risk.days_to_threshold:.1f} days "
                                    f"(now {risk.current_pct:.1f}%, +{risk.daily_change_pct:.2f} pts/day).",
                                    risk.current_pct, settings.capacity_threshold_pct, ds.as_of, source))
    return found
