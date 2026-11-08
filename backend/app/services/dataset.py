"""An immutable snapshot of resources, billing and metrics, with analytics computed once per snapshot."""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import cached_property

import pandas as pd

from cloudpulse_analytics import (
    backtest_forecast,
    cost_breakdown,
    detect_cost_spikes,
    detect_usage_anomalies,
    forecast_monthly_cost,
    predict_capacity,
    recommend_optimizations,
)


@dataclass(frozen=True, eq=False)
class Dataset:
    resources: pd.DataFrame
    billing: pd.DataFrame
    metrics: pd.DataFrame
    version: tuple = field(default=())

    @classmethod
    def from_frames(cls, resources: pd.DataFrame, billing: pd.DataFrame, metrics: pd.DataFrame, version: tuple = ()) -> Dataset:
        billing = billing.copy()
        metrics = metrics.copy()
        billing["date"] = pd.to_datetime(billing["date"])
        metrics["timestamp"] = pd.to_datetime(metrics["timestamp"])
        metrics["available"] = metrics["available"].astype(int)
        return cls(resources.reset_index(drop=True), billing.sort_values(["date", "resource"], ignore_index=True),
                   metrics.sort_values(["timestamp", "resource"], ignore_index=True), version)

    @property
    def is_empty(self) -> bool:
        return self.billing.empty or self.metrics.empty

    @property
    def as_of(self) -> pd.Timestamp:
        return self.metrics["timestamp"].max()

    @property
    def billing_as_of(self) -> pd.Timestamp:
        return self.billing["date"].max()

    @property
    def data_sources(self) -> list[str]:
        return sorted(set(self.resources["data_source"]))

    @property
    def data_source(self) -> str:
        sources = self.data_sources
        return sources[0] if len(sources) == 1 else "MIXED"

    # Analytics are expensive (Isolation Forest per resource), so each runs once per snapshot.
    @cached_property
    def cost_spikes(self) -> pd.DataFrame:
        return detect_cost_spikes(self.billing)

    @cached_property
    def usage_anomalies(self) -> pd.DataFrame:
        return detect_usage_anomalies(self.metrics)

    @cached_property
    def capacity_risks(self) -> pd.DataFrame:
        return predict_capacity(self.metrics)

    @cached_property
    def recommendations(self) -> list[dict]:
        return recommend_optimizations(self.billing, self.metrics, self.resources)

    @cached_property
    def monthly_forecast(self) -> dict:
        return forecast_monthly_cost(self.billing)

    @cached_property
    def cost_backtest(self) -> dict:
        return backtest_forecast(self.billing.groupby("date")["cost_usd"].sum(), holdout=14)

    def breakdown(self, by: str = "service", days: int = 30) -> pd.DataFrame:
        return cost_breakdown(self.billing, by=by, days=days)
