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
    "edge-lb": "edge", "nat-gateway": "edge",
    "web-prod-1": "web", "web-prod-2": "web", "staging-app-1": "web",
    "api-prod-1": "application", "api-prod-2": "application", "batch-worker-1": "application",
    "analytics-xl": "application", "legacy-ftp": "application",
    "k8s-node-1": "application", "k8s-node-2": "application", "k8s-node-3": "application",
    "orders-db": "data", "orders-db-replica": "data", "cache-prod": "data",
    "assets-bucket": "storage", "backups-bucket": "storage", "orphan-volume-07": "storage",
}

# source, target, relationship
_EDGES = [
    ("internet", "edge-lb", "HTTPS 443"),
    ("edge-lb", "web-prod-1", "HTTP"), ("edge-lb", "web-prod-2", "HTTP"), ("edge-lb", "k8s-cluster", "Ingress"),
    ("web-prod-1", "api-prod-1", "REST"), ("web-prod-1", "api-prod-2", "REST"),
    ("web-prod-2", "api-prod-1", "REST"), ("web-prod-2", "api-prod-2", "REST"),
    ("web-prod-1", "assets-bucket", "Static assets"), ("web-prod-2", "assets-bucket", "Static assets"),
    ("k8s-cluster", "k8s-node-1", "Schedules"), ("k8s-cluster", "k8s-node-2", "Schedules"), ("k8s-cluster", "k8s-node-3", "Schedules"),
    ("k8s-cluster", "orders-db", "SQL"), ("k8s-cluster", "cache-prod", "Redis"),
    ("api-prod-1", "orders-db", "SQL"), ("api-prod-2", "orders-db", "SQL"),
    ("api-prod-1", "cache-prod", "Redis"), ("api-prod-2", "cache-prod", "Redis"),
    ("orders-db", "orders-db-replica", "Replication"), ("orders-db", "backups-bucket", "Nightly backup"),
    ("batch-worker-1", "orders-db-replica", "Read queries"), ("batch-worker-1", "backups-bucket", "Exports"),
    ("analytics-xl", "orders-db-replica", "Read queries"),
    ("batch-worker-1", "nat-gateway", "Egress"), ("api-prod-1", "nat-gateway", "Egress"), ("api-prod-2", "nat-gateway", "Egress"),
    ("nat-gateway", "internet", "Outbound"),
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
