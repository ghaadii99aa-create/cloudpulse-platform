"""Executive dashboard, AI advisor, PDF reports and system metadata."""
from __future__ import annotations

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import __version__
from ..config import Settings
from ..deps import get_dataset, get_db, get_settings, require_role
from ..models import Alert, User
from ..repository import active_alerts, alert_to_dict, data_meta, reset_simulation
from ..schemas import AdvisorRequest
from ..services import insights
from ..services.advisor import advise
from ..services.dataset import Dataset
from ..services.providers import provider_status
from ..services.reports import build_executive_report

router = APIRouter()


@router.get("/dashboard/executive", tags=["dashboard"], summary="Everything the executive dashboard shows, in one call")
def executive_dashboard(db: Session = Depends(get_db), ds: Dataset = Depends(get_dataset), settings: Settings = Depends(get_settings),
                        _: User = Depends(require_role("viewer"))):
    alerts = active_alerts(db)
    forecast = insights.cost_forecast(ds, horizon=30, history_days=60)
    return {
        "data_source": ds.data_source,
        "health": insights.fleet_summary(ds, settings),
        "costs": insights.cost_summary(ds),
        "utilization_trend": insights.utilization_trend(ds, 30),
        "cost_forecast": {k: forecast[k] for k in ("history", "forecast", "total", "backtest", "model")},
        "cost_by_service": insights.records(ds.breakdown("service")),
        "top_recommendations": ds.recommendations[:5],
        "capacity_risks": insights.records(ds.capacity_risks.head(5)),
        "active_alerts": {"total": len(alerts), "critical": sum(a["severity"] == "critical" for a in alerts),
                          "warning": sum(a["severity"] == "warning" for a in alerts), "items": alerts[:8]},
    }


@router.get("/advisor/summary", tags=["advisor"], summary="AI (or fallback) summary of infrastructure and spend")
def advisor_summary(request: Request, db: Session = Depends(get_db), ds: Dataset = Depends(get_dataset),
                    settings: Settings = Depends(get_settings), user: User = Depends(require_role("viewer"))):
    _check_advisor_quota(request, settings, user)
    return advise(ds, settings, active_alerts(db))


@router.post("/advisor/ask", tags=["advisor"], summary="Ask the advisor a question about this environment")
def advisor_ask(body: AdvisorRequest, request: Request, db: Session = Depends(get_db), ds: Dataset = Depends(get_dataset),
                settings: Settings = Depends(get_settings), user: User = Depends(require_role("viewer"))):
    _check_advisor_quota(request, settings, user)
    return advise(ds, settings, active_alerts(db), body.question.strip())


def _check_advisor_quota(request: Request, settings: Settings, user: User) -> None:
    if not settings.anthropic_api_key:
        return  # fallback mode costs nothing
    limiter = request.app.state.advisor_limiter
    key = f"user:{user.id}"
    if limiter.blocked(key):
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Advisor hourly limit reached for this user")
    limiter.hit(key)


@router.get("/reports/executive.pdf", tags=["reports"], summary="Download the executive PDF report",
            response_class=Response, responses={200: {"content": {"application/pdf": {}}}})
def executive_report(db: Session = Depends(get_db), ds: Dataset = Depends(get_dataset), settings: Settings = Depends(get_settings),
                     user: User = Depends(require_role("viewer"))):
    recent = [alert_to_dict(a) for a in db.scalars(select(Alert).order_by(Alert.last_seen.desc()).limit(50))]
    pdf = build_executive_report(ds, settings, recent, user.email)
    filename = f"cloudpulse-report-{datetime.now(UTC):%Y%m%d-%H%M}.pdf"
    return Response(pdf, media_type="application/pdf", headers={"Content-Disposition": f'attachment; filename="{filename}"'})


@router.get("/system/info", tags=["system"], summary="Version, data sources and integration status")
def system_info(db: Session = Depends(get_db), settings: Settings = Depends(get_settings), _: User = Depends(require_role("viewer"))):
    return {"version": __version__, "environment": settings.environment, **data_meta(db),
            "advisor_mode": "ai" if settings.anthropic_api_key else "fallback",
            "advisor_model": settings.anthropic_model if settings.anthropic_api_key else None,
            "integrations": provider_status(settings),
            "thresholds": {"cpu_warning_pct": settings.cpu_warning_pct, "cpu_critical_pct": settings.cpu_critical_pct,
                           "memory_warning_pct": settings.memory_warning_pct, "memory_critical_pct": settings.memory_critical_pct,
                           "capacity_threshold_pct": settings.capacity_threshold_pct}}


@router.post("/system/reset-simulation", tags=["system"], summary="Wipe and regenerate the simulated environment (admin)")
def reset(request: Request, db: Session = Depends(get_db), settings: Settings = Depends(get_settings),
          _: User = Depends(require_role("admin"))):
    reset_simulation(db, settings)
    request.app.state.store.invalidate()
    request.app.state.store.get(db)
    return {"status": "reseeded", **data_meta(db)}
