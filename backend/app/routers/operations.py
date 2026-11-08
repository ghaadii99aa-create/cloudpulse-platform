"""Infrastructure monitoring, Kubernetes and topology endpoints."""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..config import Settings
from ..deps import get_dataset, get_settings, require_role
from ..services import insights
from ..services.dataset import Dataset
from ..services.kubernetes import cluster_view
from ..services.topology import build_topology

router = APIRouter(dependencies=[Depends(require_role("viewer"))])


@router.get("/infrastructure/summary", tags=["infrastructure"], summary="Fleet health score, utilization and availability")
def infrastructure_summary(ds: Dataset = Depends(get_dataset), settings: Settings = Depends(get_settings)):
    return insights.fleet_summary(ds, settings)


@router.get("/infrastructure/resources", tags=["infrastructure"], summary="Every resource with its latest metrics and health status")
def list_resources(ds: Dataset = Depends(get_dataset), settings: Settings = Depends(get_settings),
                   environment: str | None = Query(None, max_length=20), status_filter: str | None = Query(None, alias="status")):
    rows = insights.resource_status(ds, settings)
    if environment:
        rows = [r for r in rows if r["environment"] == environment]
    if status_filter:
        rows = [r for r in rows if r["status"] == status_filter]
    return {"as_of": ds.as_of.isoformat(), "data_source": ds.data_source, "items": rows}


@router.get("/infrastructure/resources/{name}/metrics", tags=["infrastructure"], summary="Historical metrics for one resource")
def resource_metrics(name: str, ds: Dataset = Depends(get_dataset), hours: int = Query(168, ge=1, le=24 * 45),
                     resolution: Literal["hour", "day"] = "hour"):
    if name not in set(ds.resources["resource"]):
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Unknown resource {name!r}")
    points = insights.resource_series(ds, name, hours, resolution)
    return {"resource": name, "resolution": resolution, "hours": hours, "data_source": ds.data_source, "points": points}


@router.get("/infrastructure/trends", tags=["infrastructure"], summary="Fleet-wide daily utilization and availability")
def infrastructure_trends(ds: Dataset = Depends(get_dataset), days: int = Query(30, ge=1, le=45)):
    return {"data_source": ds.data_source, "points": insights.utilization_trend(ds, days)}


@router.get("/infrastructure/live", tags=["infrastructure"], summary="Simulated live readings (refresh every 15 seconds)")
def infrastructure_live(ds: Dataset = Depends(get_dataset)):
    return insights.live_snapshot(ds, datetime.now(UTC).replace(tzinfo=None))


@router.get("/kubernetes/cluster", tags=["kubernetes"], summary="Cluster health, nodes, deployments and pods")
def kubernetes_cluster(ds: Dataset = Depends(get_dataset), settings: Settings = Depends(get_settings)):
    return cluster_view(ds, settings)


@router.get("/topology", tags=["topology"], summary="Service dependency graph annotated with health and cost")
def topology(ds: Dataset = Depends(get_dataset), settings: Settings = Depends(get_settings)):
    return build_topology(ds, settings)
