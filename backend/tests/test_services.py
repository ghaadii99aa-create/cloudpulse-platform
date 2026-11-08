"""Service-layer tests. These need only pandas, scikit-learn, reportlab and PyJWT (no web framework or database)."""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime
from types import SimpleNamespace as NS

import pandas as pd
import pytest

from app.config import normalize_database_url
from app.security import SlidingWindowLimiter, create_access_token, decode_access_token, hash_password, verify_password
from app.services import advisor, alert_rules, insights, kubernetes, providers, reports, topology

# ---------- config & security ----------

@pytest.mark.parametrize("raw, expected", [
    ("postgres://u:p@h:5432/db", "postgresql+psycopg://u:p@h:5432/db"),
    ("postgresql://u:p@h/db", "postgresql+psycopg://u:p@h/db"),
    ("sqlite:///./x.db", "sqlite:///./x.db"),
])
def test_database_url_normalization(raw, expected):
    assert normalize_database_url(raw) == expected


def test_password_hash_roundtrip_and_salt():
    first, second = hash_password("s3cret-value", iterations=1000), hash_password("s3cret-value", iterations=1000)
    assert first != second
    assert verify_password("s3cret-value", first) and not verify_password("wrong", first)
    assert not verify_password("s3cret-value", "not-a-hash")


def test_jwt_roundtrip_and_tamper_detection():
    import jwt
    token, expires = create_access_token(7, "engineer", "k" * 40, 5)
    assert expires == 300 and decode_access_token(token, "k" * 40)["sub"] == "7"
    with pytest.raises(jwt.PyJWTError):
        decode_access_token(token, "other-secret" * 4)
    expired, _ = create_access_token(7, "engineer", "k" * 40, -1)
    with pytest.raises(jwt.ExpiredSignatureError):
        decode_access_token(expired, "k" * 40)


def test_sliding_window_limiter():
    limiter = SlidingWindowLimiter(limit=2, window_seconds=60)
    limiter.hit("a"), limiter.hit("a")
    assert limiter.blocked("a") and not limiter.blocked("b")
    limiter.reset("a")
    assert not limiter.blocked("a")


# ---------- infrastructure ----------

def test_fleet_summary_is_consistent(dataset, settings):
    summary = insights.fleet_summary(dataset, settings)
    counts = summary["status_counts"]
    assert sum(counts.values()) == summary["resource_count"] == 19
    assert summary["monitored_count"] == summary["resource_count"] - counts["no_telemetry"]
    expected = 100 * (counts["healthy"] + 0.5 * counts["warning"]) / summary["monitored_count"]
    assert summary["health_score"] == pytest.approx(expected, abs=0.05)
    assert summary["data_source"] == "SIMULATED"


def test_status_follows_thresholds(dataset, settings):
    for row in insights.resource_status(dataset, settings):
        if row["status"] == "no_telemetry":
            assert row["cpu_pct"] is None
            continue
        breach = row["cpu_pct"] >= settings.cpu_warning_pct or row["memory_pct"] >= settings.memory_warning_pct
        assert (row["status"] != "healthy") == (breach or row["disk_pct"] >= settings.capacity_threshold_pct
                                                or row["availability_24h_pct"] < 100)


def test_lower_thresholds_raise_more_warnings(dataset, settings):
    strict = replace(settings, cpu_warning_pct=50.0)
    assert insights.fleet_summary(dataset, strict)["status_counts"]["healthy"] < \
        insights.fleet_summary(dataset, settings)["status_counts"]["healthy"]


def test_resource_series_resolution(dataset):
    hourly = insights.resource_series(dataset, "web-prod-1", hours=48)
    daily = insights.resource_series(dataset, "web-prod-1", hours=24 * 7, resolution="day")
    assert len(hourly) == 48 and 7 <= len(daily) <= 8


def test_live_snapshot_is_labeled_and_bounded(dataset):
    snap = insights.live_snapshot(dataset, datetime(2026, 11, 8, 14, 0, 5))
    assert snap["data_source"] == "SIMULATED_LIVE" and len(snap["readings"]) == 14
    assert all(0 <= r["cpu_pct"] <= 100 for r in snap["readings"])
    again = insights.live_snapshot(dataset, datetime(2026, 11, 8, 14, 0, 10))
    assert again["readings"] == snap["readings"]  # same 15-second window


# ---------- finops ----------

def test_cost_summary_reconciles_with_billing(dataset):
    summary = insights.cost_summary(dataset)
    end = dataset.billing["date"].max()
    last_30 = dataset.billing[dataset.billing["date"] > end - pd.Timedelta(days=30)]["cost_usd"].sum()
    assert summary["last_30d_usd"] == pytest.approx(last_30, abs=0.01)
    assert summary["month_end_estimate_usd"] >= summary["month_to_date_usd"]
    assert summary["potential_monthly_savings_usd"] == pytest.approx(
        sum(r["estimated_monthly_savings_usd"] for r in dataset.recommendations), abs=0.01)


def test_daily_costs_totals(dataset):
    out = insights.daily_costs(dataset, days=14)
    assert len(out["points"]) == 14
    for point in out["points"]:
        assert point["total"] == pytest.approx(sum(point[s] for s in out["series"]), abs=0.05)
    with pytest.raises(ValueError):
        insights.daily_costs(dataset, by="owner")


def test_cost_forecast_shape(dataset):
    out = insights.cost_forecast(dataset, horizon=10)
    assert len(out["forecast"]) == 10
    assert all(p["lower"] <= p["forecast"] <= p["upper"] for p in out["forecast"])
    assert out["backtest"]["mape_pct"] < 8


def test_utilization_forecast_validation(dataset):
    assert len(insights.utilization_forecast(dataset, "orders-db", "disk_pct", 7)["forecast"]) == 7
    with pytest.raises(LookupError):
        insights.utilization_forecast(dataset, "nope")
    with pytest.raises(ValueError):
        insights.utilization_forecast(dataset, "orders-db", "network_mbps")


# ---------- alerts ----------

def test_alert_rules_find_planted_and_threshold_conditions(dataset, settings):
    found = {a["fingerprint"]: a for a in alert_rules.evaluate(dataset, settings)}
    assert len(found) == len(alert_rules.evaluate(dataset, settings))  # fingerprints unique
    cost = [a for a in found.values() if a["category"] == "cost"]
    assert {a["resource"] for a in cost} == {"batch-worker-1"}  # nat-gateway spike is older than 30 days
    assert "capacity:orders-db:disk_pct" in found
    for alert in found.values():
        if alert["category"] in {"cpu", "memory"}:
            assert alert["value"] >= alert["threshold"]


def test_availability_alert_when_health_check_fails(dataset, settings):
    metrics = dataset.metrics.copy()
    last = metrics.index[(metrics["resource"] == "web-prod-2") & (metrics["timestamp"] == metrics["timestamp"].max())]
    metrics.loc[last, "available"] = 0
    broken = type(dataset).from_frames(dataset.resources, dataset.billing, metrics)
    alert = next(a for a in alert_rules.evaluate(broken, settings) if a["fingerprint"] == "availability:web-prod-2")
    assert alert["severity"] == "critical"
    status = {r["name"]: r for r in insights.resource_status(broken, settings)}
    assert status["web-prod-2"]["status"] == "critical"


# ---------- kubernetes & topology ----------

def test_simulated_cluster_accounts_for_every_replica(dataset, settings):
    view = kubernetes.cluster_view(dataset, settings)
    assert view["mode"] == "simulated" and view["data_source"] == "SIMULATED"
    assert view["summary"]["pods_total"] == sum(w[2] for w in kubernetes.WORKLOADS)
    assert view["summary"]["nodes_total"] == 3
    assert len({p["name"] for p in view["pods"]}) == len(view["pods"])


def test_critical_node_evicts_lowest_priority_pod(dataset, settings):
    strict = replace(settings, cpu_critical_pct=60.0, cpu_warning_pct=55.0)
    view = kubernetes.simulated_cluster(dataset, strict)
    pending = [p for p in view["pods"] if p["phase"] == "Pending"]
    assert pending and view["cluster"]["health"] in {"warning", "critical"}
    assert any(d["status"] == "degraded" for d in view["deployments"])


def test_live_mode_falls_back_visibly(dataset, settings):
    view = kubernetes.cluster_view(dataset, replace(settings, kubernetes_mode="live"))
    assert view["mode"] == "simulated" and "fallback_reason" in view


def test_kubernetes_object_mapping():
    node = NS(metadata=NS(name="n1"), status=NS(
        conditions=[NS(type="Ready", status="True"), NS(type="MemoryPressure", status="True")],
        capacity={"cpu": "4", "memory": "16Gi"}, node_info=NS(kubelet_version="v1.31.2")))
    mapped = kubernetes.map_node(node, {"cpu": "2000m", "memory": "8Gi"})
    assert mapped["cpu_pct"] == 50.0 and mapped["memory_pct"] == 50.0
    assert mapped["status"] == "warning" and mapped["conditions"] == ["MemoryPressure"]
    pod = NS(metadata=NS(name="p", namespace="ns", owner_references=[NS(name="rs-1")]), spec=NS(node_name="n1"),
             status=NS(phase="Running", container_statuses=[NS(ready=True, restart_count=2)]))
    assert kubernetes.map_pod(pod)["restarts"] == 2
    dep = NS(metadata=NS(name="d", namespace="ns"), spec=NS(replicas=3), status=NS(ready_replicas=1, available_replicas=1))
    assert kubernetes.map_deployment(dep)["status"] == "degraded"


def test_topology_edges_reference_existing_nodes(dataset, settings):
    graph = topology.build_topology(dataset, settings)
    ids = {n["id"] for n in graph["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in graph["edges"])
    orphan = next(n for n in graph["nodes"] if n["id"] == "orphan-volume-07")
    assert orphan["status"] == "orphaned" and orphan["isolated"]


# ---------- advisor ----------

@pytest.mark.parametrize("question, topic", [("How do I reduce our bill?", "cost"), ("Is CPU too high?", "performance"),
                                              ("disk capacity outlook", "capacity"), ("any outage?", "reliability"),
                                              ("k8s pods", "kubernetes"), ("hello", "summary")])
def test_question_classification(question, topic):
    assert topic in advisor.classify(question)


def test_fallback_is_labeled_and_grounded(dataset, settings):
    out = advisor.advise(dataset, settings, [], "Where can we save money?")
    assert out["mode"] == "fallback" and out["model"] is None and "fallback" in out["notice"].lower()
    top = dataset.recommendations[0]
    assert top["resource"] in out["answer"] and f"${top['estimated_monthly_savings_usd']:,.2f}" in out["answer"]


class _FakeResponse:
    def __init__(self, body, status=200):
        self.body, self.status = body, status

    def raise_for_status(self):
        if self.status >= 400:
            raise RuntimeError(f"HTTP {self.status}")

    def json(self):
        return self.body


def test_ai_mode_sends_facts_and_returns_model_text(dataset, settings):
    captured = {}

    def post(url, json, timeout, headers):
        captured.update(url=url, payload=json, headers=headers)
        return _FakeResponse({"content": [{"type": "text", "text": "Downsize analytics-xl."}]})

    configured = replace(settings, anthropic_api_key="sk-test")
    out = advisor.advise(dataset, configured, [], "What should we fix?", post=post)
    assert out["mode"] == "ai" and out["answer"] == "Downsize analytics-xl." and out["model"] == configured.anthropic_model
    assert captured["headers"]["x-api-key"] == "sk-test"
    assert "analytics-xl" in captured["payload"]["messages"][0]["content"]


def test_ai_failure_falls_back_with_notice(dataset, settings):
    out = advisor.advise(dataset, replace(settings, anthropic_api_key="sk-test"), [], "costs?",
                         post=lambda *a, **k: _FakeResponse({}, status=500))
    assert out["mode"] == "fallback" and "failed" in out["notice"]


# ---------- providers & reports ----------

def test_aws_and_azure_mappings():
    aws = providers.map_aws_cost_explorer({"ResultsByTime": [{"TimePeriod": {"Start": "2026-11-01"}, "Groups": [
        {"Keys": ["Amazon EC2", "Name$web-1"], "Metrics": {"UnblendedCost": {"Amount": "12.5"}}},
        {"Keys": ["Amazon S3", "Name$"], "Metrics": {"UnblendedCost": {"Amount": "0.75"}}}]}]})
    assert list(aws["resource"]) == ["web-1", "untagged:Amazon S3"] and aws["cost_usd"].sum() == pytest.approx(13.25)
    azure = providers.map_azure_cost_query({"properties": {
        "columns": [{"name": "Cost"}, {"name": "UsageDate"}, {"name": "ResourceId"}, {"name": "ServiceName"}],
        "rows": [[3.2, 20261101, "/subscriptions/s/resourceGroups/rg/providers/Microsoft.Compute/virtualMachines/vm-1", "VMs"]]}})
    assert azure.iloc[0]["resource"] == "vm-1" and str(azure.iloc[0]["date"]) == "2026-11-01"


def test_provider_status_reflects_configuration(settings):
    status = {p["provider"]: p["status"] for p in providers.provider_status(settings)}
    assert status == {"simulated": "active", "aws": "not_configured", "azure": "not_configured", "kubernetes": "simulated"}
    assert {p["provider"]: p["status"] for p in providers.provider_status(replace(settings, aws_cost_role_arn="arn:x"))}["aws"] == "configured"


def test_pdf_report_is_valid_and_labeled(dataset, settings):
    alerts = [dict(a, status="open") for a in alert_rules.evaluate(dataset, settings)]
    pdf = reports.build_executive_report(dataset, settings, alerts, "tester@example.com")
    assert pdf.startswith(b"%PDF") and len(pdf) > 5000
    pypdf = pytest.importorskip("pypdf")
    import io
    text = "".join(page.extract_text() for page in pypdf.PdfReader(io.BytesIO(pdf)).pages)
    assert "Simulated data" in text and "Recommendations" in text and "analytics-xl" in text
