"""Service dependency graph of the simulated environment, annotated with live health and cost."""
from __future__ import annotations

from ..config import Settings
from .dataset import Dataset
from .insights import resource_status

TIERS = ["edge", "web", "application", "data", "storage"]

# Logical nodes that are not billed resources.
_VIRTUAL = [
    {"id": "internet", "label": "Internet", "kind": "external", "tier": "edge"},
    {"id": "k8s-cluster", "label": "Kubernetes cluster", "kind": "cluster", "tier": "application"},
]

_TIER_BY_RESOURCE = {
    "alb-public-prod": "edge", "nat-gw-prod": "edge",
    "prod-web-01": "web", "prod-web-02": "web", "staging-app-01": "web",
    "prod-api-01": "application", "prod-api-02": "application", "prod-batch-01": "application",
    "prod-etl-01": "application", "dev-sftp-legacy": "application",
    "k8s-prod-node-01": "application", "k8s-prod-node-02": "application", "k8s-prod-node-03": "application",
    "rds-orders-primary": "data", "rds-orders-replica": "data", "redis-sessions-prod": "data",
    "s3-assets-prod": "storage", "s3-backups-prod": "storage", "ebs-vol-0a7f3c91": "storage",
}

# source, target, relationship
_EDGES = [
    ("internet", "alb-public-prod", "HTTPS 443"),
    ("alb-public-prod", "prod-web-01", "HTTP"), ("alb-public-prod", "prod-web-02", "HTTP"), ("alb-public-prod", "k8s-cluster", "Ingress"),
    ("prod-web-01", "prod-api-01", "REST"), ("prod-web-01", "prod-api-02", "REST"),
    ("prod-web-02", "prod-api-01", "REST"), ("prod-web-02", "prod-api-02", "REST"),
    ("prod-web-01", "s3-assets-prod", "Static assets"), ("prod-web-02", "s3-assets-prod", "Static assets"),
    ("k8s-cluster", "k8s-prod-node-01", "Schedules"), ("k8s-cluster", "k8s-prod-node-02", "Schedules"),
    ("k8s-cluster", "k8s-prod-node-03", "Schedules"),
    ("k8s-cluster", "rds-orders-primary", "SQL"), ("k8s-cluster", "redis-sessions-prod", "Redis"),
    ("prod-api-01", "rds-orders-primary", "SQL"), ("prod-api-02", "rds-orders-primary", "SQL"),
    ("prod-api-01", "redis-sessions-prod", "Redis"), ("prod-api-02", "redis-sessions-prod", "Redis"),
    ("rds-orders-primary", "rds-orders-replica", "Replication"), ("rds-orders-primary", "s3-backups-prod", "Nightly backup"),
    ("prod-batch-01", "rds-orders-replica", "Read queries"), ("prod-batch-01", "s3-backups-prod", "Exports"),
    ("prod-etl-01", "rds-orders-replica", "Read queries"),
    ("prod-batch-01", "nat-gw-prod", "Egress"), ("prod-api-01", "nat-gw-prod", "Egress"), ("prod-api-02", "nat-gw-prod", "Egress"),
    ("nat-gw-prod", "internet", "Outbound"),
]


def build_topology(ds: Dataset, settings: Settings) -> dict:
    statuses = {s["name"]: s for s in resource_status(ds, settings)}
    nodes = []
    for name, status in statuses.items():
        nodes.append({"id": name, "label": name, "kind": status["kind"], "service": status["service"],
                      "environment": status["environment"], "tier": _TIER_BY_RESOURCE.get(name, "application"),
                      "status": "orphaned" if not status["attached"] else status["status"],
                      "cpu_pct": status["cpu_pct"], "memory_pct": status["memory_pct"],
                      "cost_30d_usd": status["cost_30d_usd"], "data_source": status["data_source"]})
    node_statuses = [statuses[n]["status"] for n in statuses if statuses[n]["kind"] == "node"]
    cluster_status = "critical" if "critical" in node_statuses else "warning" if "warning" in node_statuses else "healthy"
    for virtual in _VIRTUAL:
        nodes.append({**virtual, "status": cluster_status if virtual["id"] == "k8s-cluster" else "external",
                      "service": None, "environment": "prod", "cpu_pct": None, "memory_pct": None, "cost_30d_usd": None,
                      "data_source": ds.data_source})
    ids = {n["id"] for n in nodes}
    edges = [{"id": f"{s}->{t}", "source": s, "target": t, "label": label} for s, t, label in _EDGES if s in ids and t in ids]
    connected = {e["source"] for e in edges} | {e["target"] for e in edges}
    for node in nodes:
        node["isolated"] = node["id"] not in connected
    return {"tiers": TIERS, "nodes": nodes, "edges": edges, "data_source": ds.data_source,
            "note": "Dependencies describe the simulated reference environment."}
