"""CloudPulse analytics: simulated data generation, forecasting and FinOps analysis."""
from .simulator import DATA_SOURCE_LABEL, SimulationConfig, generate_billing, generate_metrics, generate_resources
from .forecast import backtest_forecast, forecast_series, forecast_monthly_cost
from .anomaly import detect_cost_spikes, detect_usage_anomalies
from .capacity import predict_capacity
from .finops import cost_breakdown, recommend_optimizations

__all__ = [
    "DATA_SOURCE_LABEL", "SimulationConfig", "generate_billing", "generate_metrics", "generate_resources",
    "backtest_forecast", "forecast_series", "forecast_monthly_cost", "detect_cost_spikes",
    "detect_usage_anomalies", "predict_capacity", "cost_breakdown", "recommend_optimizations",
]
