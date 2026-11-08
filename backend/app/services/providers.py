"""Cloud provider integrations.

The demo runs on the simulated provider. AWS and Azure adapters are prepared: they define how each
provider's billing API response maps onto CloudPulse's billing schema, so ingesting real data is a
matter of supplying credentials and scheduling the fetch. They are reported as `not_configured`
until their environment variables are set, and nothing in the demo depends on them.
"""
from __future__ import annotations

from datetime import date

import pandas as pd

from ..config import Settings

BILLING_COLUMNS = ["date", "resource", "service", "environment", "cost_usd", "data_source"]


def provider_status(settings: Settings) -> list[dict]:
    return [
        {"provider": "simulated", "status": "active", "data_source": "SIMULATED",
         "description": "Deterministic generated fleet, billing and telemetry used for the demo."},
        {"provider": "aws", "status": "configured" if settings.aws_cost_role_arn else "not_configured", "data_source": "AWS",
         "apis": ["Cost Explorer GetCostAndUsage", "CloudWatch GetMetricData"],
         "requires": ["AWS_COST_ROLE_ARN (read-only role with ce:GetCostAndUsage, cloudwatch:GetMetricData)"]},
        {"provider": "azure", "status": "configured" if settings.azure_subscription_id else "not_configured", "data_source": "AZURE",
         "apis": ["Cost Management Query (ActualCost)", "Azure Monitor Metrics"],
         "requires": ["AZURE_SUBSCRIPTION_ID", "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET (Cost Management Reader)"]},
        {"provider": "kubernetes", "status": "live" if settings.kubernetes_mode == "live" else "simulated",
         "data_source": "LIVE_KUBERNETES" if settings.kubernetes_mode == "live" else "SIMULATED",
         "requires": ["KUBERNETES_MODE=live", "kubeconfig or in-cluster service account", "pip install kubernetes"]},
    ]


def map_aws_cost_explorer(response: dict, environment_tag: str = "environment") -> pd.DataFrame:
    """Map a GetCostAndUsage response (DAILY, grouped by SERVICE and TAG$resource) to billing rows.

    Expected request: Granularity=DAILY, Metrics=["UnblendedCost"],
    GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}, {"Type": "TAG", "Key": "Name"}].
    """
    rows = []
    for period in response.get("ResultsByTime", []):
        day = date.fromisoformat(period["TimePeriod"]["Start"])
        for group in period.get("Groups", []):
            service, tag = (group["Keys"] + [""])[:2]
            name = tag.split("$", 1)[1] if "$" in tag else tag
            amount = float(group["Metrics"]["UnblendedCost"]["Amount"])
            rows.append({"date": day, "resource": name or f"untagged:{service}", "service": service,
                         "environment": "unknown", "cost_usd": round(amount, 4), "data_source": "AWS"})
    return pd.DataFrame(rows, columns=BILLING_COLUMNS)


def map_azure_cost_query(response: dict) -> pd.DataFrame:
    """Map a Cost Management query result grouped by ResourceId and ServiceName, daily granularity."""
    props = response.get("properties", {})
    columns = [c["name"] for c in props.get("columns", [])]
    rows = []
    for raw in props.get("rows", []):
        record = dict(zip(columns, raw))
        usage_date = str(record.get("UsageDate"))
        day = date(int(usage_date[:4]), int(usage_date[4:6]), int(usage_date[6:8]))
        resource_id = str(record.get("ResourceId", ""))
        rows.append({"date": day, "resource": resource_id.rstrip("/").split("/")[-1] or "unassigned",
                     "service": record.get("ServiceName", "unknown"), "environment": "unknown",
                     "cost_usd": round(float(record.get("Cost", record.get("PreTaxCost", 0.0))), 4), "data_source": "AZURE"})
    return pd.DataFrame(rows, columns=BILLING_COLUMNS)
