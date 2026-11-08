"""Cost spike detection (robust z-score) and usage anomalies (Isolation Forest)."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import IsolationForest

_MAD_TO_SIGMA = 1.4826


def detect_cost_spikes(billing: pd.DataFrame, threshold: float = 6.0, min_excess_usd: float = 5.0) -> pd.DataFrame:
    """Flag resource-days far above that resource's own weekday-adjusted baseline."""
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    found = []
    for resource, group in billing.groupby("resource"):
        ordered = group.sort_values("date")
        cost = ordered.set_index("date")["cost_usd"]
        baseline = cost.rolling(29, center=True, min_periods=10).median()
        residual = (cost - baseline).dropna()
        spread = _MAD_TO_SIGMA * np.median(np.abs(residual - residual.median()))
        if spread <= 0:
            continue
        score = residual / spread
        for date in score[(score > threshold) & (residual > min_excess_usd)].index:
            found.append({"date": date, "resource": resource, "service": ordered["service"].iloc[0],
                          "cost_usd": round(float(cost[date]), 2), "expected_usd": round(float(baseline[date]), 2),
                          "excess_usd": round(float(residual[date]), 2), "score": round(float(score[date]), 1)})
    columns = ["date", "resource", "service", "cost_usd", "expected_usd", "excess_usd", "score"]
    return pd.DataFrame(found, columns=columns).sort_values("date", ignore_index=True)


def detect_usage_anomalies(metrics: pd.DataFrame, contamination: float = 0.01, seed: int = 7) -> pd.DataFrame:
    """Return the hours whose joint CPU, memory and network pattern is unusual per resource."""
    if not 0 < contamination < 0.5:
        raise ValueError("contamination must be between 0 and 0.5")
    features = ["cpu_pct", "memory_pct", "network_mbps"]
    flagged = []
    for _, group in metrics.groupby("resource"):
        if len(group) < 48:
            continue
        model = IsolationForest(contamination=contamination, random_state=seed, n_estimators=100)
        labels = model.fit_predict(group[features].to_numpy())
        flagged.append(group.loc[labels == -1, ["timestamp", "resource", *features]])
    if not flagged:
        return pd.DataFrame(columns=["timestamp", "resource", *features])
    return pd.concat(flagged, ignore_index=True).sort_values("timestamp", ignore_index=True)
