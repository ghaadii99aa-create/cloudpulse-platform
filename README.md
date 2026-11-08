# CloudPulse

**Intelligent cloud operations, observability and cost optimization platform.**

CloudPulse monitors infrastructure health, analyzes and forecasts cloud spend, detects anomalies and capacity
risks, raises alerts, and explains it all through an AI Cloud Advisor. It runs end to end without a paid cloud
account: a deterministic simulated environment stands in for AWS or Azure, and every response is labeled with its
`data_source` so simulated figures are never presented as real ones.

[![CI](https://github.com/ghaadii99aa-create/cloudpulse-platform/actions/workflows/ci.yml/badge.svg)](https://github.com/ghaadii99aa-create/cloudpulse-platform/actions/workflows/ci.yml)

## Project status

| Phase | Scope | Status |
|---|---|---|
| 1. Analytics core | Simulated fleet, billing and telemetry; forecasting, anomaly detection, capacity, FinOps rules | Done, 21 tests |
| 2. Backend API | FastAPI, PostgreSQL, JWT auth and roles, alerts, advisor, PDF reports, CI | Done, 56 tests on PostgreSQL and SQLite |
| 3. Frontend | React, TypeScript, Tailwind dashboard with dark and light themes | Next |
| 4. Platform | Kubernetes manifests, Terraform, Prometheus and Grafana | Planned |
| 5. Deployment | Hosted API, frontend and database with a public demo | Planned |

## Architecture

```mermaid
flowchart LR
    subgraph Clients
        UI[React dashboard<br/>phase 3]
        SW[Swagger UI /api/docs]
    end
    subgraph API[FastAPI service]
        AUTH[Auth + RBAC<br/>JWT, PBKDF2]
        ROUTES[REST routers<br/>/api/v1]
        STORE[Dataset store<br/>cached snapshot per data version]
        SVC[Services<br/>health, FinOps, alerts,<br/>Kubernetes, topology,<br/>advisor, PDF reports]
    end
    subgraph Analytics[cloudpulse_analytics]
        SIM[Simulator]
        ML[Forecast: Huber regression<br/>Anomalies: Isolation Forest, robust z<br/>Capacity: linear trend]
    end
    DB[(PostgreSQL)]
    CLAUDE[Anthropic API<br/>optional]
    CLOUD[AWS Cost Explorer / Azure Cost Management<br/>prepared, optional]

    UI --> ROUTES
    SW --> ROUTES
    ROUTES --> AUTH
    ROUTES --> STORE --> DB
    STORE --> SVC --> ML
    SIM -->|seed and hourly advance| DB
    SVC -. key set .-> CLAUDE
    CLOUD -. adapters .-> DB
```

The simulation clock advances with real time: once a minute the API appends any hours (metrics) and days (billing)
that have elapsed, so the demo always shows current data. Analytics run once per data version and are cached.

## Features in the API today

- **Infrastructure monitoring:** CPU, memory, disk, network and availability per resource; hourly or daily history;
  health status with reasons; a fleet health score with its formula in the response; simulated live readings.
- **FinOps:** 30-day spend and change, cost by service, resource or environment, daily cost series, month-end
  estimate, cost spike detection, and optimization recommendations with savings computed from each resource's own spend.
- **Predictive analytics:** spend forecast with a 90% prediction interval and a 14-day backtest, utilization
  forecasts, Isolation Forest usage anomalies, capacity exhaustion estimates.
- **Alerts:** CPU, memory, availability, cost and capacity rules with configurable thresholds; de-duplication by
  fingerprint, auto-resolve, acknowledge and resolve, full history.
- **Kubernetes:** simulated cluster (nodes from telemetry, deployments, pods, eviction under pressure) and an optional
  live mode through the official client that falls back visibly when no cluster is reachable.
- **Topology:** dependency graph of the environment with per-node status and cost.
- **AI Cloud Advisor:** with `ANTHROPIC_API_KEY`, Claude answers from the computed facts only; without it, a
  rule-based writer answers. Every response states `mode: "ai"` or `mode: "fallback"`.
- **Reports:** executive PDF with KPIs, cost charts, anomalies, forecast, performance table, recommendations, alerts.
- **Security:** PBKDF2-SHA256 (600k iterations), JWT, three roles, login rate limiting, timing-safe login,
  input validation, a consistent error envelope, secrets only from environment variables.

## Run it locally

Requirements: Docker, or Python 3.11+.

```bash
cp .env.example .env          # set JWT_SECRET, POSTGRES_PASSWORD, ADMIN_EMAIL, ADMIN_PASSWORD
docker compose up --build     # PostgreSQL + API on http://localhost:8000
```

Then open http://localhost:8000/api/docs and authorize with the admin account.

Without Docker:

```bash
python -m venv .venv && source .venv/bin/activate
pip install ./analytics -r backend/requirements-dev.txt
cd backend
ADMIN_EMAIL=you@example.com ADMIN_PASSWORD='choose-a-long-one-1' uvicorn app.main:app --reload
```

With no `DATABASE_URL` the API uses a local SQLite file, which is fine for development.

## Tests

```bash
cd analytics && python -m pytest        # 21 tests
cd backend && python -m pytest          # 56 tests (SQLite); set TEST_DATABASE_URL for PostgreSQL
```

GitHub Actions runs lint, the analytics suite, the backend suite against both PostgreSQL 16 and SQLite, then builds
the Docker image and smoke-tests it (login, dashboard, PDF download).

## Repository layout

```
analytics/        cloudpulse_analytics package and its tests
backend/          FastAPI service (app/), tests, Dockerfile
docs/API.md       endpoint reference, roles, error format, methods behind every number
.github/workflows CI pipeline
docker-compose.yml
```

## Configuration

All settings come from environment variables; see [.env.example](.env.example). Nothing secret has a default, and
`ENVIRONMENT=production` refuses to start without `JWT_SECRET`.

## Data honesty

Resource names, prices and usage are generated. Hourly prices are illustrative, not provider list prices. The
simulator plants two cost incidents and a growing database disk so the detectors have something real to find; the
tests check that the detectors find exactly those and raise no false alarms on clean data.
