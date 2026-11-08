import numpy as np
import pandas as pd
import pytest

from cloudpulse_analytics import (DATA_SOURCE_LABEL, SimulationConfig, backtest_forecast, cost_breakdown, detect_cost_spikes,
                                  detect_usage_anomalies, forecast_monthly_cost, forecast_series, generate_billing,
                                  generate_metrics, generate_resources, predict_capacity, recommend_optimizations)


@pytest.fixture(scope="module")
def billing():
    return generate_billing()


@pytest.fixture(scope="module")
def metrics():
    return generate_metrics()


def daily(values):
    return pd.Series(values, index=pd.date_range("2026-01-01", periods=len(values), freq="D"), dtype=float)


def test_simulated_data_is_labeled_everywhere(billing, metrics):
    for frame in (billing, metrics, generate_resources()):
        assert set(frame["data_source"]) == {DATA_SOURCE_LABEL}


def test_generation_is_deterministic(billing):
    pd.testing.assert_frame_equal(billing, generate_billing())


def test_seed_changes_output(billing):
    assert not billing["cost_usd"].equals(generate_billing(SimulationConfig(seed=1))["cost_usd"])


def test_metric_ranges(metrics):
    for column in ("cpu_pct", "memory_pct", "disk_pct"):
        assert metrics[column].between(0, 100).all()


def test_forecast_recovers_known_trend():
    result = forecast_series(daily(100 + 2.0 * np.arange(90)), horizon=10)
    expected = 100 + 2.0 * np.arange(90, 100)
    assert np.abs(result["forecast"].to_numpy() - expected).max() < 1.0


def test_forecast_recovers_weekly_pattern():
    index = pd.date_range("2026-01-05", periods=84, freq="D")
    series = pd.Series(100.0 - 30 * (index.dayofweek >= 5), index=index)
    result = forecast_series(series, horizon=7)
    weekend = result[result.index.dayofweek >= 5]["forecast"]
    weekday = result[result.index.dayofweek < 5]["forecast"]
    assert weekday.mean() - weekend.mean() == pytest.approx(30, abs=1)


def test_forecast_resists_outliers():
    values = 100 + np.arange(90, dtype=float)
    values[40:42] = 900
    result = forecast_series(daily(values), horizon=5)
    assert np.abs(result["forecast"].to_numpy() - (100 + np.arange(90, 95))).max() < 3


def test_interval_ordering(billing):
    result = forecast_series(billing.groupby("date")["cost_usd"].sum(), horizon=30)
    assert (result["lower"] <= result["forecast"]).all() and (result["forecast"] <= result["upper"]).all()


@pytest.mark.parametrize("args", [dict(horizon=0), dict(interval=1.5)])
def test_forecast_rejects_bad_arguments(args):
    with pytest.raises(ValueError):
        forecast_series(daily(np.ones(40)), **args)


def test_forecast_rejects_short_history():
    with pytest.raises(ValueError, match="at least"):
        forecast_series(daily(np.ones(5)))


def test_backtest_is_accurate_on_clean_window(billing):
    series = billing.groupby("date")["cost_usd"].sum()
    assert backtest_forecast(series, holdout=14)["mape_pct"] < 8


def test_monthly_projection_is_bounded_and_labeled(billing):
    result = forecast_monthly_cost(billing)
    assert result["low_usd"] <= result["projected_usd"] <= result["high_usd"]
    assert result["data_source"] == DATA_SOURCE_LABEL


def test_planted_cost_incidents_are_found_without_false_alarms(billing):
    spikes = detect_cost_spikes(billing)
    end = pd.Timestamp("2026-11-01")
    start_batch = end - pd.Timedelta(days=119) + pd.Timedelta(days=120 - 18)
    start_nat = end - pd.Timedelta(days=119) + pd.Timedelta(days=120 - 47)
    expected = {("batch-worker-1", start_batch), ("batch-worker-1", start_batch + pd.Timedelta(days=1)), ("nat-gateway", start_nat)}
    assert set(zip(spikes["resource"], spikes["date"])) == expected


def test_no_spikes_without_incidents():
    assert detect_cost_spikes(generate_billing(SimulationConfig(cost_incidents=()))).empty


def test_usage_anomaly_finds_injected_event(metrics):
    frame = metrics[metrics["resource"] == "web-prod-1"].copy()
    target = frame.index[300]
    frame.loc[target, ["cpu_pct", "memory_pct", "network_mbps"]] = [99.0, 99.0, 900.0]
    found = detect_usage_anomalies(frame)
    assert frame.loc[target, "timestamp"] in set(found["timestamp"])


def test_capacity_estimate_matches_known_slope():
    index = pd.date_range("2026-01-01", periods=30 * 24, freq="h")
    position = np.arange(len(index)) / 24
    frame = pd.DataFrame({"timestamp": index, "resource": "db", "cpu_pct": 10.0, "memory_pct": 20.0, "disk_pct": 50 + position})
    risk = predict_capacity(frame, threshold=85).iloc[0]
    assert risk["metric"] == "disk_pct"
    assert risk["days_to_threshold"] == pytest.approx(85 - (50 + 29.5), abs=0.8)


def test_breakdown_shares_and_total(billing):
    table = cost_breakdown(billing)
    recent = billing[billing["date"] > billing["date"].max() - pd.Timedelta(days=30)]
    assert table["cost_usd"].sum() == pytest.approx(recent["cost_usd"].sum(), abs=0.5)
    assert table["share_pct"].sum() == pytest.approx(100, abs=0.5)


def test_breakdown_rejects_unknown_dimension(billing):
    with pytest.raises(ValueError):
        cost_breakdown(billing, by="owner")


def test_recommendations_target_waste_only(billing, metrics):
    findings = recommend_optimizations(billing, metrics, generate_resources())
    by_resource = {f["resource"]: f for f in findings}
    assert by_resource["orphan-volume-07"]["category"] == "orphaned"
    assert by_resource["legacy-ftp"]["category"] == "idle"
    assert by_resource["analytics-xl"]["category"] == "rightsizing"
    assert "api-prod-1" not in by_resource and "orders-db" not in by_resource


def test_savings_never_exceed_resource_cost(billing, metrics):
    for finding in recommend_optimizations(billing, metrics, generate_resources()):
        assert 0 < finding["estimated_monthly_savings_usd"] <= finding["monthly_cost_usd"]
