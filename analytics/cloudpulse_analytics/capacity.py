"""Estimate when a utilization metric will cross a capacity threshold."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import LinearRegression

_METRICS = ("cpu_pct", "memory_pct", "disk_pct")


def predict_capacity(metrics: pd.DataFrame, threshold: float = 85.0, within_days: int = 90) -> pd.DataFrame:
    """List resources projected to reach `threshold` within `within_days`, soonest first."""
    if not 0 < threshold <= 100:
        raise ValueError("threshold must be in (0, 100]")
    risks = []
    for resource, group in metrics.groupby("resource"):
        daily = group.set_index("timestamp")[list(_METRICS)].resample("D").mean().dropna()
        if len(daily) < 7:
            continue
        x = np.arange(len(daily)).reshape(-1, 1)
        for metric in _METRICS:
            fit = LinearRegression().fit(x, daily[metric].to_numpy())
            slope = float(fit.coef_[0])
            current = float(fit.predict([[len(daily) - 1]])[0])
            if current >= threshold:
                days = 0.0
            elif slope <= 0.01:
                continue
            else:
                days = (threshold - current) / slope
            if days <= within_days:
                risks.append({"resource": resource, "metric": metric, "current_pct": round(current, 1),
                              "daily_change_pct": round(slope, 3), "days_to_threshold": round(days, 1)})
    columns = ["resource", "metric", "current_pct", "daily_change_pct", "days_to_threshold"]
    return pd.DataFrame(risks, columns=columns).sort_values("days_to_threshold", ignore_index=True)
