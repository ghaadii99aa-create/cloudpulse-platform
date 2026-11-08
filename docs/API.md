# CloudPulse API reference

Interactive documentation is served by the API itself:

- Swagger UI: `/api/docs` (use **Authorize** with your email and password)
- ReDoc: `/api/redoc`
- OpenAPI schema: `/api/openapi.json`

All endpoints below are prefixed with `/api/v1`. Every data response includes a `data_source` field
(`SIMULATED`, `SIMULATED_LIVE`, `AWS`, `AZURE` or `LIVE_KUBERNETES`).

## Authentication and roles

```http
POST /api/v1/auth/login
Content-Type: application/json

{"email": "you@example.com", "password": "..."}
```

Returns `{"access_token", "token_type": "bearer", "expires_in", "user"}`. Send the token as
`Authorization: Bearer <token>`. Tokens are HS256 JWTs signed with `JWT_SECRET`; the user is reloaded on every
request, so deactivating a user or changing a role takes effect immediately. Five failed logins for one email within
five minutes return `429`.

| Role | Can |
|---|---|
| `viewer` | Read every dashboard, metric, forecast, alert, report and ask the advisor |
| `engineer` | Everything a viewer can, plus re-evaluate, acknowledge and resolve alerts |
| `admin` | Everything, plus manage users and reset the simulated environment |

## Endpoints

| Method | Path | Role | Purpose |
|---|---|---|---|
| POST | `/auth/login` | public | JSON login |
| POST | `/auth/token` | public | OAuth2 password form (Swagger) |
| GET | `/auth/me` | any | Current user |
| GET / POST | `/users` | admin | List / create users |
| PATCH | `/users/{id}` | admin | Change name, role, active flag |
| GET | `/dashboard/executive` | viewer | Health, spend, trends, forecast, savings, alerts in one call |
| GET | `/infrastructure/summary` | viewer | Health score, average utilization, 24h availability |
| GET | `/infrastructure/resources` | viewer | Every resource with latest metrics and status (`?environment=`, `?status=`) |
| GET | `/infrastructure/resources/{name}/metrics` | viewer | History (`?hours=1..1080`, `?resolution=hour\|day`) |
| GET | `/infrastructure/trends` | viewer | Fleet daily utilization and availability |
| GET | `/infrastructure/live` | viewer | Simulated live readings, new values every 15 s |
| GET | `/finops/summary` | viewer | 30-day spend, change, month-end estimate, savings |
| GET | `/finops/breakdown` | viewer | By `service`, `resource` or `environment` (`?days=`) |
| GET | `/finops/daily` | viewer | Daily cost per service or environment |
| GET | `/finops/anomalies` | viewer | Cost spikes against each resource's own baseline |
| GET | `/finops/recommendations` | viewer | Optimization actions with estimated monthly savings |
| GET | `/analytics/forecast/cost` | viewer | Spend forecast, 90% interval, backtest accuracy |
| GET | `/analytics/forecast/utilization` | viewer | CPU, memory or disk forecast for one resource |
| GET | `/analytics/anomalies/usage` | viewer | Isolation Forest usage anomalies |
| GET | `/analytics/capacity` | viewer | Resources projected to reach a threshold |
| GET | `/alerts` | viewer | History, filter by `status` (`active`, `open`, `acknowledged`, `resolved`), `severity`, `category` |
| GET | `/alerts/summary` | viewer | Active counts by severity and category |
| POST | `/alerts/evaluate` | engineer | Re-run rules now |
| POST | `/alerts/{id}/acknowledge` | engineer | Acknowledge |
| POST | `/alerts/{id}/resolve` | engineer | Resolve |
| GET | `/kubernetes/cluster` | viewer | Nodes, deployments, pods, cluster health |
| GET | `/topology` | viewer | Dependency graph with status and cost per node |
| GET | `/advisor/summary` | viewer | Advisor summary |
| POST | `/advisor/ask` | viewer | `{"question": "..."}` (3 to 1000 characters) |
| GET | `/reports/executive.pdf` | viewer | Executive PDF report |
| GET | `/system/info` | viewer | Version, data sources, advisor mode, integration status |
| POST | `/system/reset-simulation` | admin | Wipe and regenerate simulated data |

Outside the prefix: `GET /healthz` (liveness), `GET /readyz` (database reachable) and `GET /metrics` (Prometheus format;
requires `Authorization: Bearer <METRICS_TOKEN>` when that variable is set). The web container does not proxy these three.

## Errors

```json
{"error": {"code": "not_found", "message": "Unknown resource 'x'"}}
```

Validation failures return `422` with `code: "validation_error"` and a `details` list of `{field, message}`.
Codes: `bad_request` 400, `unauthorized` 401, `forbidden` 403, `not_found` 404, `conflict` 409,
`validation_error` 422, `rate_limited` 429, `internal_error` 500, `unavailable` 503.

## How the numbers are produced

| Output | Method |
|---|---|
| Health score | 100 x (healthy + 0.5 x warning) / monitored resources, latest hour |
| Resource status | Thresholds from env (`CPU_WARNING_PCT` etc.); failed health check in the latest hour is critical |
| Cost spikes | 29-day rolling median per resource; MAD-scaled score > 6 and excess > $5 |
| Usage anomalies | Isolation Forest on CPU, memory and network per resource, 1% contamination |
| Spend forecast | Huber regression with linear trend and weekday effects; empirical 90% interval; 14-day backtest |
| Month-end estimate | Month-to-date actuals + forecast for the remaining days |
| Capacity | Linear regression on daily mean utilization, days until the threshold |
| Recommendations | Idle non-production (mean CPU < 5%), oversized (p95 CPU < 40% and p95 memory < 60%), unattached volumes; savings from each resource's own spend |
| Alerts | One active alert per fingerprint; CPU, memory, availability and capacity alerts auto-resolve when the condition clears; a resolved cost incident is not reopened |
| Advisor | `ai` mode sends only the computed facts to Claude; `fallback` mode writes the answer with rules. The `mode` field says which |
