"""Kubernetes cluster view.

`simulated` mode derives node load from the simulated k8s-node-* telemetry and spreads it over a
fixed workload spec. `live` mode reads a real cluster through the official Python client when it
is installed and a kubeconfig or in-cluster service account is available; otherwise it falls back
to simulated mode and says why.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from ..config import Settings
from .dataset import Dataset
from .insights import resource_status

log = logging.getLogger("cloudpulse.kubernetes")

NODE_CPU_MILLICORES = 4000
NODE_MEMORY_MIB = 16384

# namespace, deployment, replicas, cpu request (m), memory request (MiB), priority (lower is evicted first)
WORKLOADS = [
    ("storefront", "web-frontend", 4, 250, 512, 2),
    ("storefront", "checkout-api", 3, 500, 1024, 3),
    ("platform", "orders-service", 3, 500, 1536, 3),
    ("platform", "payments-gateway", 2, 400, 1024, 3),
    ("platform", "inventory-worker", 2, 300, 768, 1),
    ("observability", "prometheus", 1, 500, 2048, 2),
    ("observability", "grafana", 1, 200, 512, 1),
    ("ingress", "ingress-nginx", 2, 200, 256, 3),
    ("kube-system", "coredns", 2, 100, 128, 4),
]


def _suffix(*parts: str, length: int = 5) -> str:
    return hashlib.sha1("/".join(parts).encode()).hexdigest()[:length]


def simulated_cluster(ds: Dataset, settings: Settings) -> dict:
    statuses = {s["name"]: s for s in resource_status(ds, settings) if s["kind"] == "node"}
    node_names = sorted(statuses)
    if not node_names:
        raise LookupError("dataset has no Kubernetes nodes")

    pods = []
    slot = 0
    for namespace, deployment, replicas, cpu_req, mem_req, priority in WORKLOADS:
        template = _suffix(namespace, deployment, length=9)
        for replica in range(replicas):
            node = node_names[slot % len(node_names)]
            slot += 1
            pods.append({"name": f"{deployment}-{template}-{_suffix(deployment, str(replica))}", "namespace": namespace,
                         "deployment": deployment, "node": node, "phase": "Running", "ready": True, "restarts": 0,
                         "cpu_request_m": cpu_req, "memory_request_mib": mem_req, "priority": priority})

    nodes = []
    for name in node_names:
        status = statuses[name]
        on_node = [p for p in pods if p["node"] == name]
        cpu_used = (status["cpu_pct"] or 0) / 100 * NODE_CPU_MILLICORES
        mem_used = (status["memory_pct"] or 0) / 100 * NODE_MEMORY_MIB
        total_cpu_req = sum(p["cpu_request_m"] for p in on_node) or 1
        total_mem_req = sum(p["memory_request_mib"] for p in on_node) or 1
        for pod in on_node:
            pod["cpu_usage_m"] = round(cpu_used * pod["cpu_request_m"] / total_cpu_req)
            pod["memory_usage_mib"] = round(mem_used * pod["memory_request_mib"] / total_mem_req)
        if status["status"] == "critical":
            # Under pressure the kubelet evicts the lowest-priority pod; it waits for capacity elsewhere.
            victim = min(on_node, key=lambda p: (p["priority"], p["name"]))
            victim.update(phase="Pending", ready=False, restarts=1, cpu_usage_m=0, memory_usage_mib=0,
                          reason="Evicted: node resource pressure")
        conditions = []
        if (status["memory_pct"] or 0) >= settings.memory_warning_pct:
            conditions.append("MemoryPressure")
        if (status["disk_pct"] or 0) >= settings.capacity_threshold_pct:
            conditions.append("DiskPressure")
        nodes.append({"name": name, "ready": bool(status["available"]), "status": status["status"], "conditions": conditions,
                      "cpu_pct": status["cpu_pct"], "memory_pct": status["memory_pct"],
                      "cpu_capacity_m": NODE_CPU_MILLICORES, "memory_capacity_mib": NODE_MEMORY_MIB,
                      "pod_count": len(on_node), "kubelet_version": "v1.31 (simulated)"})

    deployments = []
    for namespace, deployment, replicas, *_ in WORKLOADS:
        members = [p for p in pods if p["deployment"] == deployment]
        ready = sum(p["ready"] for p in members)
        deployments.append({"name": deployment, "namespace": namespace, "desired": replicas, "ready": ready,
                            "available": ready, "status": "healthy" if ready == replicas else "degraded" if ready else "down"})
    for pod in pods:
        pod.pop("priority")
    return _assemble("simulated", nodes, pods, deployments, ds.data_source)


def _assemble(mode: str, nodes: list[dict], pods: list[dict], deployments: list[dict], source: str, **extra) -> dict:
    measured = [n for n in nodes if n.get("cpu_pct") is not None]
    summary = {
        "nodes_total": len(nodes), "nodes_ready": sum(n["ready"] for n in nodes),
        "pods_total": len(pods), "pods_running": sum(p["phase"] == "Running" for p in pods),
        "pods_pending": sum(p["phase"] == "Pending" for p in pods),
        "deployments_total": len(deployments), "deployments_healthy": sum(d["status"] == "healthy" for d in deployments),
        "avg_cpu_pct": round(sum(n["cpu_pct"] for n in measured) / len(measured), 2) if measured else None,
        "avg_memory_pct": round(sum(n["memory_pct"] for n in measured) / len(measured), 2) if measured else None,
        "namespaces": sorted({p["namespace"] for p in pods}),
    }
    if summary["nodes_ready"] < summary["nodes_total"] or summary["deployments_healthy"] == 0:
        health = "critical"
    elif summary["pods_pending"] or summary["deployments_healthy"] < summary["deployments_total"] \
            or any(n["status"] in {"warning", "critical"} for n in nodes):
        health = "warning"
    else:
        health = "healthy"
    return {"mode": mode, "data_source": source, "cluster": {"name": extra.pop("cluster_name", "cloudpulse-demo"), "health": health},
            "summary": summary, "nodes": nodes, "deployments": deployments, "pods": pods, **extra}


# ----- live mode: map Kubernetes API objects (duck-typed so tests need no cluster) -----

def _quantity_to_millicores(value: str | None) -> int | None:
    if not value:
        return None
    if value.endswith("n"):
        return round(int(value[:-1]) / 1_000_000)
    if value.endswith("u"):
        return round(int(value[:-1]) / 1000)
    if value.endswith("m"):
        return int(value[:-1])
    return round(float(value) * 1000)


def _quantity_to_mib(value: str | None) -> int | None:
    if not value:
        return None
    units = {"Ki": 1 / 1024, "Mi": 1, "Gi": 1024, "Ti": 1024 * 1024, "K": 1000 / 1024 ** 2, "M": 1000 ** 2 / 1024 ** 2,
             "G": 1000 ** 3 / 1024 ** 2}
    for suffix, factor in units.items():
        if value.endswith(suffix):
            return round(float(value[: -len(suffix)]) * factor)
    return round(int(value) / 1024 ** 2)


def map_node(node: Any, usage: dict | None = None) -> dict:
    conditions = {c.type: c.status for c in (node.status.conditions or [])}
    cpu_cap = _quantity_to_millicores(node.status.capacity.get("cpu"))
    mem_cap = _quantity_to_mib(node.status.capacity.get("memory"))
    usage = usage or {}
    cpu_used = _quantity_to_millicores(usage.get("cpu"))
    mem_used = _quantity_to_mib(usage.get("memory"))
    pressure = [t for t in ("MemoryPressure", "DiskPressure", "PIDPressure") if conditions.get(t) == "True"]
    ready = conditions.get("Ready") == "True"
    return {"name": node.metadata.name, "ready": ready, "status": "critical" if not ready else "warning" if pressure else "healthy",
            "conditions": pressure, "cpu_pct": round(cpu_used / cpu_cap * 100, 2) if cpu_used is not None and cpu_cap else None,
            "memory_pct": round(mem_used / mem_cap * 100, 2) if mem_used is not None and mem_cap else None,
            "cpu_capacity_m": cpu_cap, "memory_capacity_mib": mem_cap, "pod_count": None,
            "kubelet_version": node.status.node_info.kubelet_version}


def map_pod(pod: Any) -> dict:
    statuses = pod.status.container_statuses or []
    return {"name": pod.metadata.name, "namespace": pod.metadata.namespace,
            "deployment": next((o.name for o in (pod.metadata.owner_references or [])), None),
            "node": pod.spec.node_name, "phase": pod.status.phase, "ready": bool(statuses) and all(s.ready for s in statuses),
            "restarts": sum(s.restart_count for s in statuses)}


def map_deployment(dep: Any) -> dict:
    desired = dep.spec.replicas or 0
    ready = dep.status.ready_replicas or 0
    return {"name": dep.metadata.name, "namespace": dep.metadata.namespace, "desired": desired, "ready": ready,
            "available": dep.status.available_replicas or 0,
            "status": "healthy" if ready >= desired else "degraded" if ready else "down"}


def live_cluster() -> dict:
    from kubernetes import client, config  # optional dependency, imported only in live mode

    try:
        config.load_incluster_config()
    except config.ConfigException:
        config.load_kube_config()
    core, apps = client.CoreV1Api(), client.AppsV1Api()
    usage: dict[str, dict] = {}
    try:
        metrics = client.CustomObjectsApi().list_cluster_custom_object("metrics.k8s.io", "v1beta1", "nodes")
        usage = {item["metadata"]["name"]: item["usage"] for item in metrics.get("items", [])}
    except Exception:  # metrics-server is optional
        log.info("metrics.k8s.io unavailable; node utilization omitted")
    nodes = [map_node(n, usage.get(n.metadata.name)) for n in core.list_node().items]
    pods = [map_pod(p) for p in core.list_pod_for_all_namespaces().items]
    for node in nodes:
        node["pod_count"] = sum(p["node"] == node["name"] for p in pods)
    deployments = [map_deployment(d) for d in apps.list_deployment_for_all_namespaces().items]
    return _assemble("live", nodes, pods, deployments, "LIVE_KUBERNETES", cluster_name="current-context")


def cluster_view(ds: Dataset, settings: Settings) -> dict:
    if settings.kubernetes_mode == "live":
        try:
            return live_cluster()
        except Exception as exc:  # fall back, but never silently
            log.warning("live Kubernetes unavailable: %s", exc)
            view = simulated_cluster(ds, settings)
            view["fallback_reason"] = f"Live mode requested but unavailable: {type(exc).__name__}"
            return view
    return simulated_cluster(ds, settings)
