"""FinOps and predictive analytics endpoints."""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from cloudpulse_analytics import predict_capacity

from ..deps import get_dataset, require_role
from ..services import insights
from ..services.dataset import Dataset

router = APIRouter(dependencies=[Depends(require_role("viewer"))])


@router.get("/finops/summary", tags=["finops"], summary="Spend, month-end estimate, forecast and savings")
def finops_summary(ds: Dataset = Depends(get_dataset)):
    return insights.cost_summary(ds)


@router.get("/finops/breakdown", tags=["finops"], summary="Cost broken down by service, resource or environment")
def finops_breakdown(ds: Dataset = Depends(get_dataset), by: Literal["service", "resource", "environment"] = "service",
                     days: int = Query(30, ge=1, le=365)):
    table = ds.breakdown(by=by, days=days)
    return {"by": by, "days": days, "data_source": ds.data_source, "total_usd": round(float(table["cost_usd"].sum()), 2),
            "items": insights.records(table)}


@router.get("/finops/daily", tags=["finops"], summary="Daily cost per service or environment")
def finops_daily(ds: Dataset = Depends(get_dataset), by: Literal["service", "environment"] = "service",
                 days: int = Query(90, ge=7, le=365)):
    return insights.daily_costs(ds, days, by)


@router.get("/finops/anomalies", tags=["finops"], summary="Unusual spending increases (robust z-score per resource)")
def finops_anomalies(ds: Dataset = Depends(get_dataset)):
    return {"data_source": ds.data_source, "method": "29-day rolling median baseline, MAD-scaled score > 6 and excess > $5",
            "items": insights.records(ds.cost_spikes)}


@router.get("/finops/recommendations", tags=["finops"], summary="Cost optimization opportunities with estimated savings")
def finops_recommendations(ds: Dataset = Depends(get_dataset)):
    items = ds.recommendations
    return {"data_source": ds.data_source, "total_monthly_savings_usd": round(sum(i["estimated_monthly_savings_usd"] for i in items), 2),
            "items": items}


@router.get("/analytics/forecast/cost", tags=["analytics"], summary="Daily spend forecast with prediction interval and backtest")
def forecast_cost(ds: Dataset = Depends(get_dataset), horizon: int = Query(30, ge=1, le=90),
                  history_days: int = Query(60, ge=7, le=365)):
    return insights.cost_forecast(ds, horizon, history_days)


@router.get("/analytics/forecast/utilization", tags=["analytics"], summary="Forecast a resource's daily utilization")
def forecast_utilization(resource: str = Query(..., max_length=120), ds: Dataset = Depends(get_dataset),
                         metric: Literal["cpu_pct", "memory_pct", "disk_pct"] = "cpu_pct", horizon: int = Query(14, ge=1, le=60)):
    try:
        return insights.utilization_forecast(ds, resource, metric, horizon)
    except LookupError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from None


@router.get("/analytics/anomalies/usage", tags=["analytics"], summary="Unusual CPU/memory/network patterns (Isolation Forest)")
def usage_anomalies(ds: Dataset = Depends(get_dataset), resource: str | None = Query(None, max_length=120),
                    limit: int = Query(100, ge=1, le=1000)):
    frame = ds.usage_anomalies
    if resource:
        frame = frame[frame["resource"] == resource]
    frame = frame.sort_values("timestamp", ascending=False).head(limit)
    return {"data_source": ds.data_source, "method": "Isolation Forest per resource, contamination 1%", "items": insights.records(frame)}


@router.get("/analytics/capacity", tags=["analytics"], summary="Resources projected to hit a utilization threshold")
def capacity(ds: Dataset = Depends(get_dataset), threshold: float = Query(85.0, gt=0, le=100), within_days: int = Query(90, ge=1, le=365)):
    frame = ds.capacity_risks if (threshold, within_days) == (85.0, 90) else predict_capacity(ds.metrics, threshold, within_days)
    return {"data_source": ds.data_source, "threshold_pct": threshold, "within_days": within_days,
            "method": "Linear regression on daily mean utilization", "items": insights.records(frame)}
