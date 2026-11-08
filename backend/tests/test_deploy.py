"""Single-service hosting and the read-only demo sign-in."""
from __future__ import annotations

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from app.database import Base  # noqa: E402
from app.main import create_app  # noqa: E402

from .conftest import make_settings  # noqa: E402

DEMO = dict(demo_user_email="demo@cloudpulse.test", demo_user_password="demo-Passw0rd-long", demo_user_role="viewer")
API = "/api/v1"


@pytest.fixture
def make_client():
    apps = []

    def build(**overrides):
        app = create_app(make_settings(**overrides))
        apps.append(app)
        return TestClient(app)

    yield build
    for app in apps:
        Base.metadata.drop_all(app.state.database.engine)


@pytest.fixture
def dist(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text('<div id="root"></div>')
    (tmp_path / "favicon.svg").write_text("<svg/>")
    (tmp_path / "assets" / "app-abc.js").write_text("run()")
    (tmp_path.parent / "secret.txt").write_text("private")
    return tmp_path


def test_demo_is_off_by_default(make_client):
    with make_client(**DEMO) as client:
        assert client.get(f"{API}/auth/options").json() == {"demo_login": False}
        assert client.post(f"{API}/auth/demo").status_code == 404


def test_demo_signs_in_as_a_viewer_that_cannot_change_anything(make_client):
    with make_client(**DEMO, demo_login_enabled=True) as client:
        assert client.get(f"{API}/auth/options").json() == {"demo_login": True}
        session = client.post(f"{API}/auth/demo").json()
        assert session["user"]["role"] == "viewer"
        headers = {"Authorization": f"Bearer {session['access_token']}"}
        assert client.get(f"{API}/dashboard/executive", headers=headers).status_code == 200
        assert client.post(f"{API}/alerts/evaluate", headers=headers).status_code == 403
        assert client.post(f"{API}/system/reset-simulation", headers=headers).status_code == 403
        assert client.get(f"{API}/users", headers=headers).status_code == 403


def test_demo_refuses_an_account_with_more_than_read_access(make_client):
    with make_client(**{**DEMO, "demo_user_role": "engineer"}, demo_login_enabled=True) as client:
        assert client.post(f"{API}/auth/demo").status_code == 404


def test_dashboard_routes_serve_the_app_with_security_headers(make_client, dist):
    with make_client(web_dist=str(dist)) as client:
        for path in ("/", "/costs", "/infrastructure/orders-db"):
            response = client.get(path)
            assert response.status_code == 200 and 'id="root"' in response.text
            assert "frame-ancestors 'none'" in response.headers["content-security-policy"]
        assert client.head("/costs").status_code == 200
        assert client.get("/favicon.svg").text == "<svg/>"
        assert "immutable" in client.get("/assets/app-abc.js").headers["cache-control"]


def test_catch_all_does_not_shadow_the_api_or_escape_the_directory(make_client, dist):
    with make_client(web_dist=str(dist)) as client:
        missing = client.get(f"{API}/does-not-exist")
        assert missing.status_code == 404 and missing.json()["error"]["code"] == "not_found"
        assert client.get("/healthz").json()["status"] == "ok"
        assert "cloudpulse_data_available" in client.get("/metrics").text
        assert "private" not in client.get("/%2e%2e/secret.txt").text
        assert "private" not in client.get("/..%2fsecret.txt").text
