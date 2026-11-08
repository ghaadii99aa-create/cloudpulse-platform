"""Cost breakdowns and savings recommendations computed from observed data."""
from __future__ import annotations

import pandas as pd

WINDOW_DAYS = 30
DAYS_PER_MONTH = 30


def _recent(billing: pd.DataFrame, days: int = WINDOW_DAYS) -> pd.DataFrame:
    return billing[billing["date"] > billing["date"].max() - pd.Timedelta(days=days)]


def cost_breakdown(billing: pd.DataFrame, by: str = "service", days: int = WINDOW_DAYS) -> pd.DataFrame:
    if by not in {"service", "resource", "environment"}:
        raise ValueError("by must be service, resource or environment")
    totals = _recent(billing, days).groupby(by, as_index=False)["cost_usd"].sum().sort_values("cost_usd", ascending=False, ignore_index=True)
    totals["share_pct"] = (totals["cost_usd"] / totals["cost_usd"].sum() * 100).round(1)
    totals["cost_usd"] = totals["cost_usd"].round(2)
    return totals


def recommend_optimizations(billing: pd.DataFrame, metrics: pd.DataFrame, resources: pd.DataFrame,
                            idle_cpu: float = 5.0, oversized_p95_cpu: float = 40.0) -> list[dict]:
    """Rule-based findings. Savings derive from each resource's own recent spend."""
    spend = _recent(billing).groupby("resource")["cost_usd"].mean() * DAYS_PER_MONTH
    usage = metrics.groupby("resource").agg(cpu_mean=("cpu_pct", "mean"), cpu_p95=("cpu_pct", lambda s: s.quantile(0.95)),
                                            mem_p95=("memory_pct", lambda s: s.quantile(0.95)))
    findings = []

    def add(item, action, category, ratio, reason):
        monthly = float(spend[item.resource])
        findings.append({"resource": item.resource, "category": category, "action": action, "reason": reason,
                         "monthly_cost_usd": round(monthly, 2), "estimated_monthly_savings_usd": round(monthly * ratio, 2),
                         "data_source": item.data_source})

    for item in resources.itertuples(index=False):
        if not item.attached:
            add(item, "Delete after snapshot", "orphaned", 1.0, "Volume is not attached to any instance.")
            continue
        if item.resource not in usage.index:
            continue
        stats = usage.loc[item.resource]
        detail = f"Mean CPU {stats.cpu_mean:.1f}%, p95 CPU {stats.cpu_p95:.1f}%, p95 memory {stats.mem_p95:.1f}%."
        if item.environment != "prod" and stats.cpu_mean < idle_cpu:
            add(item, "Stop or schedule off-hours shutdown", "idle", 0.7, f"Non-production and idle. {detail}")
        elif stats.cpu_p95 < oversized_p95_cpu and stats.mem_p95 < 60:
            add(item, "Downsize one instance tier", "rightsizing", 0.5, f"Peak usage fits half the capacity. {detail}")
    return sorted(findings, key=lambda f: f["estimated_monthly_savings_usd"], reverse=True)
