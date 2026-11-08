from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..config import Settings
from ..deps import get_dataset, get_db, get_settings, require_role
from ..models import Alert, User, utcnow
from ..repository import alert_to_dict, sync_alerts
from ..schemas import AlertOut, AlertPage
from ..services.dataset import Dataset

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertPage, summary="Alert history with filters")
def list_alerts(db: Session = Depends(get_db), _ds: Dataset = Depends(get_dataset), _: User = Depends(require_role("viewer")),
                status_filter: Literal["open", "acknowledged", "resolved", "active"] | None = Query(None, alias="status"),
                severity: Literal["info", "warning", "critical"] | None = None,
                category: Literal["cpu", "memory", "availability", "cost", "capacity"] | None = None,
                limit: int = Query(50, ge=1, le=500), offset: int = Query(0, ge=0)):
    query = select(Alert)
    if status_filter == "active":
        query = query.where(Alert.status.in_(("open", "acknowledged")))
    elif status_filter:
        query = query.where(Alert.status == status_filter)
    if severity:
        query = query.where(Alert.severity == severity)
    if category:
        query = query.where(Alert.category == category)
    total = db.scalar(select(func.count()).select_from(query.subquery()))
    rows = db.scalars(query.order_by(Alert.last_seen.desc(), Alert.id.desc()).limit(limit).offset(offset)).all()
    return {"total": total, "items": [alert_to_dict(a) for a in rows]}


@router.get("/summary", summary="Active alert counts by severity and category")
def alert_summary(db: Session = Depends(get_db), _ds: Dataset = Depends(get_dataset), _: User = Depends(require_role("viewer"))):
    active = db.execute(select(Alert.severity, Alert.category, func.count()).where(Alert.status.in_(("open", "acknowledged")))
                        .group_by(Alert.severity, Alert.category)).all()
    by_severity: dict[str, int] = {}
    by_category: dict[str, int] = {}
    for severity, category, count in active:
        by_severity[severity] = by_severity.get(severity, 0) + count
        by_category[category] = by_category.get(category, 0) + count
    return {"active_total": sum(by_severity.values()), "by_severity": by_severity, "by_category": by_category,
            "resolved_total": db.scalar(select(func.count()).where(Alert.status == "resolved"))}


@router.post("/evaluate", summary="Re-run alert rules now (engineer)")
def evaluate(db: Session = Depends(get_db), ds: Dataset = Depends(get_dataset), settings: Settings = Depends(get_settings),
             _: User = Depends(require_role("engineer"))):
    return sync_alerts(db, ds, settings)


def _transition(db: Session, alert_id: int, target: str, user: User) -> dict:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Alert not found")
    if alert.status == "resolved":
        raise HTTPException(status.HTTP_409_CONFLICT, "Alert is already resolved")
    if target == "acknowledged":
        if alert.status == "acknowledged":
            raise HTTPException(status.HTTP_409_CONFLICT, "Alert is already acknowledged")
        alert.status, alert.acknowledged_by, alert.acknowledged_at = "acknowledged", user.email, utcnow()
    else:
        alert.status, alert.resolved_at = "resolved", utcnow()
        alert.acknowledged_by = alert.acknowledged_by or user.email
    db.commit()
    return alert_to_dict(alert)


@router.post("/{alert_id}/acknowledge", response_model=AlertOut, summary="Acknowledge an alert (engineer)")
def acknowledge(alert_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_role("engineer"))):
    return _transition(db, alert_id, "acknowledged", user)


@router.post("/{alert_id}/resolve", response_model=AlertOut, summary="Resolve an alert (engineer)")
def resolve(alert_id: int, db: Session = Depends(get_db), user: User = Depends(require_role("engineer"))):
    return _transition(db, alert_id, "resolved", user)
