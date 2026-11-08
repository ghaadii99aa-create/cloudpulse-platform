# Infrastructure

| Path | Contents |
|---|---|
| `k8s/base` | Namespace, API, web, PostgreSQL, Ingress, autoscaling, disruption budgets, NetworkPolicies |
| `k8s/overlays/local` | Base plus monitoring, using locally built images |
| `monitoring` | Prometheus configuration and alert rules, Grafana provisioning and dashboard |
| `terraform/aws` | VPC, EKS, RDS PostgreSQL and ECR |
| `scripts/verify-kind.sh` | Deploys to a throwaway kind cluster and checks real behavior |

## Kubernetes

Needs Docker, [kind](https://kind.sigs.k8s.io/), kubectl, Python 3 and curl. From the repository root:

```bash
infrastructure/scripts/verify-kind.sh
kubectl -n cloudpulse port-forward svc/web 8080:80
```

The script generates random secrets, so read the admin password you need from the cluster:

```bash
kubectl -n cloudpulse get secret cloudpulse-secrets -o jsonpath='{.data.ADMIN_PASSWORD}' | base64 -d
```

Delete the cluster with `kind delete cluster --name cloudpulse`.

For another cluster, push the two images to your registry, create an overlay that sets their names and the Ingress host,
and create the `cloudpulse-secrets` Secret using `k8s/secrets.example.yaml` as the list of keys. Never commit real values.

Design notes:

- Every pod runs under the `restricted` Pod Security profile: non-root, read-only root filesystem, no capabilities.
- API replicas share PostgreSQL. Advisory locks make startup seeding, simulation updates and alert sync safe to run from
  several replicas. Login and advisor rate limits are counted per replica.
- API pods wait briefly before shutting down, so requests already routed to a replacing replica still complete.
- The web tier proxies only `/api/`, and a NetworkPolicy limits `/metrics` to Prometheus.
- PostgreSQL runs in the cluster for the demo. The Terraform stack uses RDS instead.
- The manifests set no AWS or Azure credentials. The simulated environment needs none.

## Monitoring

Prometheus scrapes each API replica. Grafana opens with the **CloudPulse overview** dashboard. Platform gauges carry a
`data_source` label, and the first dashboard panel shows it, so simulated figures are not mistaken for real ones.

```bash
cd infrastructure/monitoring
promtool check rules rules/cloudpulse.yml
promtool test rules rules.test.yml
```

## Terraform (AWS)

**Applying this stack creates billable AWS resources**, including an EKS control plane, worker nodes, a NAT gateway and
an RDS instance. It has not been applied; check current AWS pricing before you do. CI checks it without an AWS account:

```bash
cd infrastructure/terraform/aws
terraform init -backend=false
terraform validate
terraform test    # plan tests with a mocked provider; creates nothing
```

To deploy, configure a remote state backend in `versions.tf`, copy `terraform.tfvars.example` to `terraform.tfvars`, then
run `terraform plan` and review it before `terraform apply`. RDS generates the database password and stores it in
Secrets Manager, so it never enters Terraform state.
