"""The /metrics endpoint: exposition, bounded labels, simulated-data labeling and optional token."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base  # noqa: E402
from app.main import create_app  # noqa: E402

from .conftest import make_settings  # noqa: E402


def _client(**overrides):
    return create_app(make_settings(**overrides))


@pytest.fixture(scope="module")
def client():
    app = _client()
    with TestClient(app) as test_client:
        yield test_client
    Base.metadata.drop_all(app.state.database.engine)


def test_platform_gauges_are_exposed_and_labeled_simulated(client):
    body = client.get("/metrics").text
    assert "cloudpulse_data_available 1.0" in body
    for name in ("fleet_health_score", "cost_last_30d_usd", "cost_month_end_estimate_usd", "cost_potential_savings_monthly_usd"):
        assert f'cloudpulse_{name}{{data_source="SIMULATED"}}' in body
    assert 'cloudpulse_active_alerts{data_source="SIMULATED",severity="critical"}' in body
    assert 'cloudpulse_resource_utilization_percent{data_source="SIMULATED",metric="cpu",resource="prod-web-01"}' in body


def test_requests_are_counted_by_route_template_not_raw_path(client):
    client.get("/api/v1/infrastructure/resources/does-not-exist/metrics")
    client.get("/a/random/path/that/does/not/exist")
    body = client.get("/metrics").text
    assert 'route="/api/v1/infrastructure/resources/{name}/metrics"' in body
    assert 'route="unmatched"' in body
    assert "does-not-exist" not in body
    assert "random/path" not in body


def test_probes_are_not_counted(client):
    client.get("/healthz")
    assert 'route="/healthz"' not in client.get("/metrics").text


def test_metrics_token_is_enforced_when_set():
    app = _client(metrics_token="scrape-secret")
    with TestClient(app) as test_client:
        assert test_client.get("/metrics").status_code == 401
        assert test_client.get("/metrics", headers={"Authorization": "Bearer wrong"}).status_code == 401
        assert test_client.get("/metrics", headers={"Authorization": "Bearer scrape-secret"}).status_code == 200
    Base.metadata.drop_all(app.state.database.engine)


def test_a_failed_dataset_is_reported_not_hidden():
    app = _client(seed_on_startup=False)
    with TestClient(app) as test_client:
        body = test_client.get("/metrics").text
    assert "cloudpulse_data_available 0.0" in body
    assert "cloudpulse_fleet_health_score" not in body
    Base.metadata.drop_all(app.state.database.engine)
