#!/usr/bin/env bash
# Deploys CloudPulse to a throwaway kind cluster and checks that it really works. Needs docker, kind, kubectl, python3, curl.
# Run from the repository root:  infrastructure/scripts/verify-kind.sh
set -euo pipefail

CLUSTER=${CLUSTER:-cloudpulse}
NS=cloudpulse
OVERLAY=infrastructure/k8s/overlays/local
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }
PIDS=()
cleanup() {
  for pid in "${PIDS[@]:-}"; do [ -n "$pid" ] && kill "$pid" 2>/dev/null || true; done
}
trap cleanup EXIT

forward() { # service local remote
  kubectl -n "$NS" port-forward "svc/$1" "$2:$3" >/dev/null 2>&1 &
  PIDS+=($!)
  for _ in $(seq 1 30); do curl -s -o /dev/null "localhost:$2" && return 0; sleep 1; done
  fail "port-forward to $1"
}
json() { python3 -c "import json,sys; d=json.load(sys.stdin); print($1)"; }

docker build -q -f backend/Dockerfile -t cloudpulse-api:local .
docker build -q -t cloudpulse-web:local frontend

kind get clusters | grep -qx "$CLUSTER" || kind create cluster --name "$CLUSTER" --wait 120s
kind load docker-image --name "$CLUSTER" cloudpulse-api:local cloudpulse-web:local

kubectl apply -f infrastructure/k8s/base/namespace.yaml
ADMIN_EMAIL=admin@cloudpulse.test
ADMIN_PASSWORD="Kind$(openssl rand -hex 16)"
PG_PASSWORD="$(openssl rand -hex 24)"
GRAFANA_PASSWORD="$(openssl rand -hex 16)"
kubectl -n "$NS" create secret generic cloudpulse-secrets --dry-run=client -o yaml \
  --from-literal=JWT_SECRET="$(openssl rand -hex 32)" \
  --from-literal=POSTGRES_USER=cloudpulse --from-literal=POSTGRES_PASSWORD="$PG_PASSWORD" --from-literal=POSTGRES_DB=cloudpulse \
  --from-literal=DATABASE_URL="postgresql+psycopg://cloudpulse:$PG_PASSWORD@postgres:5432/cloudpulse" \
  --from-literal=ADMIN_EMAIL="$ADMIN_EMAIL" --from-literal=ADMIN_PASSWORD="$ADMIN_PASSWORD" \
  --from-literal=GRAFANA_ADMIN_PASSWORD="$GRAFANA_PASSWORD" | kubectl apply -f -

kubectl apply -k "$OVERLAY"
kubectl -n "$NS" rollout status statefulset/postgres --timeout=180s
for deployment in api web prometheus grafana; do kubectl -n "$NS" rollout status "deployment/$deployment" --timeout=360s; done
pass "all workloads rolled out under the restricted Pod Security profile"

forward web 18080 80
forward prometheus 19090 9090
forward grafana 13000 3000

[ "$(curl -s -o /dev/null -w '%{http_code}' localhost:18080/)" = 200 ] || fail "dashboard page"
curl -sI localhost:18080/ | grep -qi '^content-security-policy:' || fail "CSP header"
[ "$(curl -s -o /dev/null -w '%{http_code}' localhost:18080/infrastructure/orders-db)" = 200 ] || fail "SPA deep link"
pass "dashboard served with security headers and deep links"

if curl -s localhost:18080/metrics | grep -q cloudpulse_http; then fail "/metrics is exposed through the web tier"; fi
pass "/metrics is not reachable through the web tier"

login() {
  curl -fsS -X POST localhost:18080/api/v1/auth/login -H 'content-type: application/json' \
    -d "{\"email\":\"$ADMIN_EMAIL\",\"password\":\"$ADMIN_PASSWORD\"}" | json 'd["access_token"]'
}
TOKEN=$(login)
SOURCE=$(curl -fsS localhost:18080/api/v1/dashboard/executive -H "Authorization: Bearer $TOKEN" | json 'd["data_source"]')
[ "$SOURCE" = SIMULATED ] || fail "dashboard data source was $SOURCE"
curl -fsS -o /tmp/report.pdf localhost:18080/api/v1/reports/executive.pdf -H "Authorization: Bearer $TOKEN"
[ "$(head -c 4 /tmp/report.pdf)" = "%PDF" ] || fail "PDF report"
pass "login, dashboard and PDF work through the web tier"

RESOURCES=$(kubectl -n "$NS" exec statefulset/postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from resources"')
[ "$RESOURCES" = 19 ] || fail "expected one seeded copy of 19 resources, found $RESOURCES"
pass "two API replicas seeded the database exactly once"

for _ in $(seq 1 40); do
  UP=$(curl -fsS 'localhost:19090/api/v1/query?query=sum(up%7Bjob%3D%22cloudpulse-api%22%7D)' | json 'd["data"]["result"][0]["value"][1] if d["data"]["result"] else 0')
  [ "$UP" = 2 ] && break; sleep 5
done
[ "$UP" = 2 ] || fail "Prometheus sees $UP API targets, expected 2"
pass "Prometheus scrapes both API replicas"
SERIES=$(curl -fsS 'localhost:19090/api/v1/query?query=cloudpulse_fleet_health_score' | json 'd["data"]["result"][0]["metric"]["data_source"]')
[ "$SERIES" = SIMULATED ] || fail "health score series labeled $SERIES"
RULES=$(curl -fsS localhost:19090/api/v1/rules | json 'sum(len(g["rules"]) for g in d["data"]["groups"])')
[ "$RULES" -ge 6 ] || fail "only $RULES alert rules loaded"
pass "platform gauges carry data_source, $RULES alert rules loaded"

[ "$(curl -fsS -u "admin:$GRAFANA_PASSWORD" localhost:13000/api/dashboards/uid/cloudpulse-overview | json 'd["dashboard"]["uid"]')" = cloudpulse-overview ] || fail "Grafana dashboard"
RESULT=$(curl -fsS -u "admin:$GRAFANA_PASSWORD" "localhost:13000/api/datasources/proxy/uid/prometheus/api/v1/query?query=up" | json 'len(d["data"]["result"])')
[ "$RESULT" -ge 2 ] || fail "Grafana cannot query Prometheus"
pass "Grafana provisioned the dashboard and queries Prometheus"

kubectl -n "$NS" delete "$(kubectl -n "$NS" get pod -l app.kubernetes.io/name=cloudpulse-api -o name | head -1)" --wait=false
FAILED=0
for _ in $(seq 1 20); do
  [ "$(curl -s -o /dev/null -w '%{http_code}' localhost:18080/api/v1/system/info -H "Authorization: Bearer $TOKEN")" = 200 ] || FAILED=$((FAILED+1))
  sleep 0.5
done
[ "$FAILED" -eq 0 ] || fail "$FAILED of 20 requests failed while a replica was replaced"
pass "the API kept answering while a replica was replaced"

kubectl -n "$NS" delete pod postgres-0
kubectl -n "$NS" rollout status statefulset/postgres --timeout=180s
for _ in $(seq 1 30); do
  COUNT=$(kubectl -n "$NS" exec statefulset/postgres -- sh -c 'psql -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Atc "select count(*) from users"' 2>/dev/null || echo 0)
  [ "$COUNT" -ge 1 ] && break; sleep 2
done
[ "$COUNT" -ge 1 ] || fail "database lost its data after a restart"
pass "database contents survive a pod restart"

kubectl -n "$NS" run netcheck --image=busybox:1.37 --restart=Never --rm -i --quiet \
  --overrides='{"spec":{"securityContext":{"runAsNonRoot":true,"runAsUser":1000,"seccompProfile":{"type":"RuntimeDefault"}},"containers":[{"name":"netcheck","image":"busybox:1.37","command":["sh","-c","if nc -z -w 5 postgres 5432; then echo open; else echo blocked; fi"],"securityContext":{"allowPrivilegeEscalation":false,"capabilities":{"drop":["ALL"]}}}]}}' \
  > /tmp/netcheck.txt || true
grep -q blocked /tmp/netcheck.txt || fail "an unrelated pod could reach PostgreSQL: $(cat /tmp/netcheck.txt)"
pass "NetworkPolicy blocks an unrelated pod from PostgreSQL"

echo "All checks passed."
