"""Deterministic generator for simulated infrastructure and billing data.

Every record is synthetic. Consumers must surface DATA_SOURCE_LABEL so simulated
figures are never mistaken for real cloud data. Hourly prices are illustrative
demo values, not provider list prices.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

DATA_SOURCE_LABEL = "SIMULATED"

# name, service, kind, environment, hourly_usd, cpu_base, mem_base, always_on
_FLEET = [
    ("web-prod-1", "Compute", "vm", "prod", 0.192, 58, 62, True),
    ("web-prod-2", "Compute", "vm", "prod", 0.192, 55, 60, True),
    ("api-prod-1", "Compute", "vm", "prod", 0.384, 64, 70, True),
    ("api-prod-2", "Compute", "vm", "prod", 0.384, 61, 68, True),
    ("batch-worker-1", "Compute", "vm", "prod", 0.768, 34, 41, True),
    ("analytics-xl", "Compute", "vm", "prod", 1.536, 6, 14, True),
    ("staging-app-1", "Compute", "vm", "staging", 0.192, 4, 11, True),
    ("legacy-ftp", "Compute", "vm", "dev", 0.096, 1, 7, True),
    ("orders-db", "Database", "database", "prod", 0.712, 47, 74, True),
    ("orders-db-replica", "Database", "database", "prod", 0.712, 12, 38, True),
    ("cache-prod", "Cache", "cache", "prod", 0.312, 28, 71, True),
    ("k8s-node-1", "Kubernetes", "node", "prod", 0.384, 66, 72, True),
    ("k8s-node-2", "Kubernetes", "node", "prod", 0.384, 63, 69, True),
    ("k8s-node-3", "Kubernetes", "node", "prod", 0.384, 59, 66, True),
    ("assets-bucket", "Storage", "storage", "prod", 0.145, 0, 0, True),
    ("backups-bucket", "Storage", "storage", "prod", 0.210, 0, 0, True),
    ("orphan-volume-07", "Storage", "volume", "dev", 0.064, 0, 0, False),
    ("edge-lb", "Network", "load_balancer", "prod", 0.089, 0, 0, True),
    ("nat-gateway", "Network", "gateway", "prod", 0.135, 0, 0, True),
]
_FLEET_COLUMNS = ["resource", "service", "kind", "environment", "hourly_usd", "cpu_base", "mem_base", "attached"]


@dataclass(frozen=True)
class SimulationConfig:
    days: int = 120
    seed: int = 42
    end: str = "2026-11-01"
    monthly_growth: float = 0.03
    # (days before end, resource, cost multiplier, duration in days)
    cost_incidents: tuple = field(default_factory=lambda: ((18, "batch-worker-1", 3.2, 2), (47, "nat-gateway", 4.5, 1)))


def generate_resources() -> pd.DataFrame:
    frame = pd.DataFrame(_FLEET, columns=_FLEET_COLUMNS)
    frame["data_source"] = DATA_SOURCE_LABEL
    return frame


def _days(config: SimulationConfig) -> pd.DatetimeIndex:
    return pd.date_range(end=pd.Timestamp(config.end), periods=config.days, freq="D")


def generate_billing(config: SimulationConfig | None = None) -> pd.DataFrame:
    """Daily cost per resource, with growth, weekly seasonality and planted incidents."""
    config = config or SimulationConfig()
    rng = np.random.default_rng(config.seed)
    days = _days(config)
    position = np.arange(config.days)
    rows = []
    for item in generate_resources().itertuples(index=False):
        growth = (1 + config.monthly_growth) ** (position / 30)
        weekly = 1 - 0.08 * (days.dayofweek >= 5) if item.environment == "prod" else np.ones(config.days)
        noise = rng.normal(1, 0.025, config.days)
        cost = item.hourly_usd * 24 * growth * weekly * noise
        for offset, resource, multiplier, duration in config.cost_incidents:
            if resource == item.resource:
                start = config.days - offset
                cost[start : start + duration] *= multiplier
        rows.append(pd.DataFrame({"date": days, "resource": item.resource, "service": item.service,
                                  "environment": item.environment, "cost_usd": np.round(cost, 4)}))
    billing = pd.concat(rows, ignore_index=True)
    billing["data_source"] = DATA_SOURCE_LABEL
    return billing


def generate_metrics(config: SimulationConfig | None = None, hours: int = 24 * 30) -> pd.DataFrame:
    """Hourly CPU, memory, disk and network metrics for resources that report them."""
    config = config or SimulationConfig()
    rng = np.random.default_rng(config.seed + 1)
    index = pd.date_range(end=pd.Timestamp(config.end), periods=hours, freq="h")
    hour = index.hour.to_numpy()
    rows = []
    for item in generate_resources().query("cpu_base > 0").itertuples(index=False):
        daily = np.sin((hour - 8) / 24 * 2 * np.pi)
        amplitude = item.cpu_base * 0.25
        trend = np.linspace(0, item.cpu_base * 0.12, hours)
        cpu = np.clip(item.cpu_base + amplitude * daily + trend + rng.normal(0, 2, hours), 0, 100)
        mem = np.clip(item.mem_base + 0.1 * amplitude * daily + trend * 0.8 + rng.normal(0, 1.2, hours), 0, 100)
        disk = np.clip(35 + (item.mem_base / 4) + np.linspace(0, 22 if item.kind == "database" else 5, hours), 0, 100)
        network = np.maximum(0, item.cpu_base * (1 + 0.5 * daily) * rng.lognormal(0, 0.15, hours))
        available = (rng.random(hours) > 0.0015).astype(int)
        rows.append(pd.DataFrame({"timestamp": index, "resource": item.resource, "cpu_pct": cpu.round(2),
                                  "memory_pct": mem.round(2), "disk_pct": disk.round(2),
                                  "network_mbps": network.round(2), "available": available}))
    metrics = pd.concat(rows, ignore_index=True)
    metrics["data_source"] = DATA_SOURCE_LABEL
    return metrics
