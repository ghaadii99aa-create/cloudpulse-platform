"""End-to-end API tests through FastAPI's TestClient against a real database
(SQLite by default, PostgreSQL in CI via TEST_DATABASE_URL)."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("sqlalchemy")

from dataclasses import replace  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base  # noqa: E402
from app.main import create_app  # noqa: E402

from .conftest import ADMIN, make_settings  # noqa: E402

API = "/api/v1"
ENGINEER = ("engineer@cloudpulse.test", "engineer-Passw0rd-1")
VIEWER = ("viewer@cloudpulse.test", "viewer-Passw0rd-1")


@pytest.fixture(scope="module")
def client():
    app = create_app(make_settings())
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(app.state.database.engine)


def login(client, email, password):
    response = client.post(f"{API}/auth/login", json={"email": email, "password": password})
    assert response.status_code == 200, response.text
    return {"Authorization": f"Bearer {response.json()['access_token']}"}


@pytest.fixture(scope="module")
def admin(client):
    return login(client, *ADMIN)


@pytest.fixture(scope="module")
def engineer(client, admin):
    created = client.post(f"{API}/users", headers=admin, json={"email": ENGINEER[0], "full_name": "Eng", "password": ENGINEER[1],
                                                               "role": "engineer"})
    assert created.status_code == 201, created.text
    return login(client, *ENGINEER)


@pytest.fixture(scope="module")
def viewer(client, admin):
    created = client.post(f"{API}/users", headers=admin, json={"email": VIEWER[0], "full_name": "View", "password": VIEWER[1]})
    assert created.status_code == 201 and created.json()["role"] == "viewer"
    return login(client, *VIEWER)


# ---------- system & auth ----------

def test_health_and_readiness(client):
    assert client.get("/healthz").json()["status"] == "ok"
    assert client.get("/readyz").json()["status"] == "ready"


def test_openapi_documents_every_module(client):
    paths = client.get("/api/openapi.json").json()["paths"]
    for path in ("/auth/login", "/dashboard/executive", "/infrastructure/resources", "/finops/recommendations",
                 "/analytics/forecast/cost", "/alerts", "/kubernetes/cluster", "/topology", "/advisor/ask", "/reports/executive.pdf"):
        assert f"{API}{path}" in paths


def test_protected_endpoints_require_token(client):
    response = client.get(f"{API}/infrastructure/summary")
    assert response.status_code == 401 and response.json()["error"]["code"] == "unauthorized"
    bad = client.get(f"{API}/infrastructure/summary", headers={"Authorization": "Bearer not-a-jwt"})
    assert bad.status_code == 401


def test_login_rejects_wrong_password_and_rate_limits(client):
    for _ in range(5):
        assert client.post(f"{API}/auth/login", json={"email": "ghost@x.io", "password": "nope"}).status_code == 401
    assert client.post(f"{API}/auth/login", json={"email": "ghost@x.io", "password": "nope"}).status_code == 429


def test_oauth2_form_login_and_me(client):
    response = client.post(f"{API}/auth/token", data={"username": ADMIN[0], "password": ADMIN[1]})
    assert response.status_code == 200
    me = client.get(f"{API}/auth/me", headers={"Authorization": f"Bearer {response.json()['access_token']}"}).json()
    assert me["email"] == ADMIN[0] and me["role"] == "admin" and "password_hash" not in me


def test_role_based_access(client, admin, engineer, viewer):
    assert client.get(f"{API}/users", headers=viewer).status_code == 403
    assert client.get(f"{API}/users", headers=engineer).status_code == 403
    assert len(client.get(f"{API}/users", headers=admin).json()) >= 3
    assert client.post(f"{API}/alerts/evaluate", headers=viewer).status_code == 403
    assert client.post(f"{API}/alerts/evaluate", headers=engineer).status_code == 200
    assert client.post(f"{API}/system/reset-simulation", headers=engineer).status_code == 403


def test_user_validation_and_conflicts(client, admin, engineer):
    weak = client.post(f"{API}/users", headers=admin, json={"email": "w@x.io", "full_name": "W", "password": "short"})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "validation_error"
    bad_email = client.post(f"{API}/users", headers=admin, json={"email": "nope", "full_name": "W", "password": "longenough123"})
    assert bad_email.status_code == 422
    dup = client.post(f"{API}/users", headers=admin, json={"email": ENGINEER[0], "full_name": "E", "password": "another-pass-123"})
    assert dup.status_code == 409


def test_deactivated_user_loses_access(client, admin):
    created = client.post(f"{API}/users", headers=admin, json={"email": "temp@cloudpulse.test", "full_name": "T",
                                                               "password": "temporary-pass-1"}).json()
    headers = login(client, "temp@cloudpulse.test", "temporary-pass-1")
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 200
    assert client.patch(f"{API}/users/{created['id']}", headers=admin, json={"is_active": False}).json()["is_active"] is False
    assert client.get(f"{API}/auth/me", headers=headers).status_code == 401


def test_admin_cannot_demote_self(client, admin):
    me = client.get(f"{API}/auth/me", headers=admin).json()
    assert client.patch(f"{API}/users/{me['id']}", headers=admin, json={"role": "viewer"}).status_code == 400


# ---------- data endpoints ----------

def test_infrastructure_endpoints(client, viewer):
    summary = client.get(f"{API}/infrastructure/summary", headers=viewer).json()
    assert summary["data_source"] == "SIMULATED" and summary["as_of"].startswith("2026-11-08T14:00")
    resources = client.get(f"{API}/infrastructure/resources", headers=viewer).json()["items"]
    assert len(resources) == 19
    prod = client.get(f"{API}/infrastructure/resources", params={"environment": "prod"}, headers=viewer).json()["items"]
    assert prod and all(r["environment"] == "prod" for r in prod)
    series = client.get(f"{API}/infrastructure/resources/prod-api-01/metrics", params={"hours": 24}, headers=viewer).json()
    assert len(series["points"]) == 24
    assert client.get(f"{API}/infrastructure/resources/missing/metrics", headers=viewer).status_code == 404
    assert client.get(f"{API}/infrastructure/resources/prod-api-01/metrics", params={"hours": 0}, headers=viewer).status_code == 422
    live = client.get(f"{API}/infrastructure/live", headers=viewer).json()
    assert live["data_source"] == "SIMULATED_LIVE" and live["readings"]
    assert client.get(f"{API}/infrastructure/trends", headers=viewer).json()["points"]


def test_finops_endpoints_reconcile(client, viewer):
    summary = client.get(f"{API}/finops/summary", headers=viewer).json()
    breakdown = client.get(f"{API}/finops/breakdown", params={"by": "resource"}, headers=viewer).json()
    assert breakdown["total_usd"] == pytest.approx(summary["last_30d_usd"], abs=0.5)
    recs = client.get(f"{API}/finops/recommendations", headers=viewer).json()
    assert recs["total_monthly_savings_usd"] == pytest.approx(summary["potential_monthly_savings_usd"], abs=0.01)
    anomalies = client.get(f"{API}/finops/anomalies", headers=viewer).json()["items"]
    assert {a["resource"] for a in anomalies} == {"prod-batch-01", "nat-gw-prod"}
    assert client.get(f"{API}/finops/breakdown", params={"by": "owner"}, headers=viewer).status_code == 422
    daily = client.get(f"{API}/finops/daily", params={"days": 30}, headers=viewer).json()
    assert len(daily["points"]) == 30


def test_analytics_endpoints(client, viewer):
    forecast = client.get(f"{API}/analytics/forecast/cost", params={"horizon": 14}, headers=viewer).json()
    assert len(forecast["forecast"]) == 14 and forecast["backtest"]["mape_pct"] < 8
    util = client.get(f"{API}/analytics/forecast/utilization", params={"resource": "rds-orders-primary", "metric": "disk_pct"}, headers=viewer)
    assert util.status_code == 200 and len(util.json()["forecast"]) == 14
    assert client.get(f"{API}/analytics/forecast/utilization", params={"resource": "ghost"}, headers=viewer).status_code == 404
    capacity = client.get(f"{API}/analytics/capacity", headers=viewer).json()["items"]
    assert capacity[0]["resource"] == "rds-orders-primary" and capacity[0]["metric"] == "disk_pct"
    assert client.get(f"{API}/analytics/anomalies/usage", params={"limit": 5}, headers=viewer).status_code == 200


def test_kubernetes_and_topology(client, viewer):
    cluster = client.get(f"{API}/kubernetes/cluster", headers=viewer).json()
    assert cluster["mode"] == "simulated" and cluster["summary"]["nodes_total"] == 3
    graph = client.get(f"{API}/topology", headers=viewer).json()
    ids = {n["id"] for n in graph["nodes"]}
    assert all(e["source"] in ids and e["target"] in ids for e in graph["edges"])


def test_executive_dashboard(client, viewer):
    dash = client.get(f"{API}/dashboard/executive", headers=viewer).json()
    for key in ("health", "costs", "utilization_trend", "cost_forecast", "cost_by_service", "top_recommendations", "active_alerts"):
        assert key in dash
    assert dash["active_alerts"]["total"] >= 1 and dash["data_source"] == "SIMULATED"


# ---------- alerts lifecycle ----------

def test_alerts_are_generated_and_deduplicated(client, engineer):
    first = client.get(f"{API}/alerts", params={"status": "active", "limit": 500}, headers=engineer).json()
    again = client.post(f"{API}/alerts/evaluate", headers=engineer).json()
    assert again["created"] == 0 and again["updated"] == first["total"]
    categories = {a["category"] for a in first["items"]}
    assert {"cost", "capacity"} <= categories
    summary = client.get(f"{API}/alerts/summary", headers=engineer).json()
    assert summary["active_total"] == first["total"]


def test_alert_acknowledge_and_resolve(client, engineer, viewer):
    alert = client.get(f"{API}/alerts", params={"status": "open", "category": "cost"}, headers=engineer).json()["items"][0]
    assert client.post(f"{API}/alerts/{alert['id']}/acknowledge", headers=viewer).status_code == 403
    acked = client.post(f"{API}/alerts/{alert['id']}/acknowledge", headers=engineer).json()
    assert acked["status"] == "acknowledged" and acked["acknowledged_by"] == ENGINEER[0]
    assert client.post(f"{API}/alerts/{alert['id']}/acknowledge", headers=engineer).status_code == 409
    resolved = client.post(f"{API}/alerts/{alert['id']}/resolve", headers=engineer).json()
    assert resolved["status"] == "resolved" and resolved["resolved_at"]
    # A resolved cost incident must not be re-created by the next evaluation.
    client.post(f"{API}/alerts/evaluate", headers=engineer)
    same = client.get(f"{API}/alerts", params={"category": "cost", "limit": 500}, headers=engineer).json()["items"]
    assert sum(a["fingerprint"] == alert["fingerprint"] for a in same) == 1
    assert client.post(f"{API}/alerts/999999/resolve", headers=engineer).status_code == 404


# ---------- advisor, reports, system ----------

def test_advisor_fallback(client, viewer):
    out = client.post(f"{API}/advisor/ask", json={"question": "How can we reduce cost?"}, headers=viewer).json()
    assert out["mode"] == "fallback" and "prod-etl-01" in out["answer"]
    assert client.post(f"{API}/advisor/ask", json={"question": "x"}, headers=viewer).status_code == 422
    assert client.get(f"{API}/advisor/summary", headers=viewer).json()["mode"] == "fallback"


def test_pdf_report_download(client, viewer):
    response = client.get(f"{API}/reports/executive.pdf", headers=viewer)
    assert response.status_code == 200 and response.headers["content-type"] == "application/pdf"
    assert response.content.startswith(b"%PDF") and "attachment" in response.headers["content-disposition"]


def test_system_info(client, viewer):
    info = client.get(f"{API}/system/info", headers=viewer).json()
    assert info["simulated"] is True and info["advisor_mode"] == "fallback"
    assert {i["provider"] for i in info["integrations"]} == {"simulated", "aws", "azure", "kubernetes"}


def test_unknown_route_uses_error_envelope(client):
    response = client.get(f"{API}/does-not-exist")
    assert response.status_code == 404 and response.json()["error"]["code"] == "not_found"


def test_reset_simulation_reseeds(client, admin):
    response = client.post(f"{API}/system/reset-simulation", headers=admin)
    assert response.status_code == 200 and response.json()["status"] == "reseeded"
    assert client.get(f"{API}/infrastructure/summary", headers=admin).json()["resource_count"] == 19


# ---------- simulation clock ----------

def test_simulation_advances_to_the_current_hour(tmp_path):
    import pandas as pd
    from sqlalchemy import func, select

    from app.database import Database
    from app.models import CostRecord, MetricSample
    from app.repository import advance_simulation, seed_simulation

    settings = replace(make_settings(database_url=f"sqlite:///{tmp_path / 'clock.db'}"), simulation_end=None)
    db_handle = Database(settings.database_url)
    db_handle.create_all()
    start = pd.Timestamp("2026-11-08 10:00")
    with db_handle.session_factory() as db:
        seed_simulation(db, settings, now=start)
        added = advance_simulation(db, settings, now=pd.Timestamp("2026-11-09 13:00"))
        assert added["metrics_added"] == 27 * 14 and added["costs_added"] == 19
        assert db.scalar(select(func.max(MetricSample.timestamp))) == pd.Timestamp("2026-11-09 13:00").to_pydatetime()
        assert str(db.scalar(select(func.max(CostRecord.date)))) == "2026-11-08"
        assert advance_simulation(db, settings, now=pd.Timestamp("2026-11-09 13:00")) == {"metrics_added": 0, "costs_added": 0}
