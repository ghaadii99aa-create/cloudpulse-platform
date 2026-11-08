"""Trend + weekday seasonality forecasting with empirical prediction intervals."""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.linear_model import HuberRegressor
from sklearn.preprocessing import StandardScaler

MIN_HISTORY_DAYS = 28


def _features(position: np.ndarray, dayofweek: np.ndarray) -> np.ndarray:
    weekdays = np.eye(7)[dayofweek][:, 1:]
    return np.column_stack([position, weekdays])


def _validated(series: pd.Series) -> pd.Series:
    if not isinstance(series.index, pd.DatetimeIndex):
        raise ValueError("series must have a DatetimeIndex")
    clean = series.dropna().sort_index()
    if len(clean) < MIN_HISTORY_DAYS:
        raise ValueError(f"need at least {MIN_HISTORY_DAYS} observations, got {len(clean)}")
    return clean.astype(float)


def forecast_series(series: pd.Series, horizon: int = 30, interval: float = 0.9) -> pd.DataFrame:
    """Forecast a daily series. Huber loss keeps one-off spikes from bending the trend."""
    if horizon < 1:
        raise ValueError("horizon must be positive")
    if not 0 < interval < 1:
        raise ValueError("interval must be between 0 and 1")
    clean = _validated(series)
    position = (clean.index - clean.index[0]).days.to_numpy()
    scaler = StandardScaler().fit(position.reshape(-1, 1))
    scaled = scaler.transform(position.reshape(-1, 1)).ravel()
    model = HuberRegressor(max_iter=2000, alpha=1e-4).fit(_features(scaled, clean.index.dayofweek.to_numpy()), clean.to_numpy())
    residuals = clean.to_numpy() - model.predict(_features(scaled, clean.index.dayofweek.to_numpy()))
    lower_q, upper_q = np.quantile(residuals, [(1 - interval) / 2, 1 - (1 - interval) / 2])

    future = pd.date_range(clean.index[-1] + pd.Timedelta(days=1), periods=horizon, freq="D")
    future_position = (future - clean.index[0]).days.to_numpy()
    future_scaled = scaler.transform(future_position.reshape(-1, 1)).ravel()
    predicted = model.predict(_features(future_scaled, future.dayofweek.to_numpy()))
    return pd.DataFrame({"forecast": np.maximum(predicted, 0), "lower": np.maximum(predicted + lower_q, 0),
                         "upper": np.maximum(predicted + upper_q, 0)}, index=future)


def backtest_forecast(series: pd.Series, holdout: int = 14) -> dict:
    """Measure accuracy on the most recent `holdout` days, unseen by the model."""
    clean = _validated(series)
    if len(clean) - holdout < MIN_HISTORY_DAYS:
        raise ValueError("not enough history for this holdout")
    predicted = forecast_series(clean.iloc[:-holdout], horizon=holdout)
    actual = clean.iloc[-holdout:].to_numpy()
    errors = np.abs(actual - predicted["forecast"].to_numpy())
    inside = (actual >= predicted["lower"].to_numpy()) & (actual <= predicted["upper"].to_numpy())
    return {"holdout_days": holdout, "mape_pct": round(float(np.mean(errors / np.maximum(actual, 1e-9)) * 100), 2),
            "interval_coverage_pct": round(float(inside.mean() * 100), 1)}


def forecast_monthly_cost(billing: pd.DataFrame, horizon: int = 30) -> dict:
    daily = billing.groupby("date")["cost_usd"].sum()
    result = forecast_series(daily, horizon=horizon)
    return {"horizon_days": horizon, "projected_usd": round(float(result["forecast"].sum()), 2),
            "low_usd": round(float(result["lower"].sum()), 2), "high_usd": round(float(result["upper"].sum()), 2),
            "previous_period_usd": round(float(daily.tail(horizon).sum()), 2),
            "data_source": str(billing["data_source"].iloc[0])}
