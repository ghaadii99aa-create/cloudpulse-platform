"""AI Cloud Advisor.

Both modes reason over the same computed facts. With ANTHROPIC_API_KEY set, a Claude model writes
the answer from those facts; without it (or if the call fails) a deterministic rule-based writer
answers instead. Every response states which mode produced it.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Callable
from datetime import UTC, datetime

import pandas as pd

from ..config import Settings
from .dataset import Dataset
from .insights import cost_summary, fleet_summary, resource_status

log = logging.getLogger("cloudpulse.advisor")

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
FALLBACK_NOTICE = "Rule-based fallback: no AI model was called. Set ANTHROPIC_API_KEY to enable AI answers."
SYSTEM_PROMPT = (
    "You are CloudPulse Advisor, a senior cloud and FinOps engineer. Answer using ONLY the JSON facts provided. "
    "Never invent resources, numbers or prices. If the facts do not cover the question, say so. "
    "When you mention savings, use the estimated_monthly_savings_usd values given. The data_source field tells you "
    "whether the data is simulated; mention it once if it is. Be concise: short paragraphs or bullet points, "
    "Markdown allowed, no more than about 250 words."
)
TOPICS = {
    "cost": ("cost", "spend", "bill", "save", "saving", "budget", "expensive", "finops", "money"),
    "performance": ("cpu", "memory", "performance", "slow", "load", "utilization", "latency", "health"),
    "capacity": ("capacity", "disk", "forecast", "predict", "future", "grow", "scale"),
    "reliability": ("availability", "uptime", "down", "outage", "alert", "incident"),
    "kubernetes": ("kubernetes", "k8s", "pod", "node", "cluster", "deployment"),
}


def build_facts(ds: Dataset, settings: Settings, open_alerts: list[dict]) -> dict:
    fleet = fleet_summary(ds, settings)
    costs = cost_summary(ds)
    stressed = [s for s in resource_status(ds, settings) if s["status"] in {"warning", "critical"}]
    spikes = ds.cost_spikes
    recent_spikes = spikes[spikes["date"] > ds.billing_as_of - pd.Timedelta(days=30)] if not spikes.empty else spikes
    return {
        "data_source": ds.data_source, "as_of": fleet["as_of"],
        "fleet": {k: fleet[k] for k in ("resource_count", "monitored_count", "status_counts", "health_score",
                                         "avg_cpu_pct", "avg_memory_pct", "availability_24h_pct")},
        "stressed_resources": [{k: s[k] for k in ("name", "status", "reasons", "cpu_pct", "memory_pct")} for s in stressed],
        "costs": {k: costs[k] for k in ("last_30d_usd", "previous_30d_usd", "change_pct", "month_end_estimate_usd",
                                        "potential_monthly_savings_usd", "top_service")},
        "forecast_next_30d": costs["next_30d_forecast"],
        "cost_by_service_30d": ds.breakdown("service").to_dict(orient="records"),
        "recent_cost_spikes": [{"date": r.date.date().isoformat(), "resource": r.resource, "cost_usd": r.cost_usd,
                                "expected_usd": r.expected_usd} for r in recent_spikes.itertuples(index=False)],
        "recommendations": [{k: r[k] for k in ("resource", "category", "action", "reason", "monthly_cost_usd",
                                               "estimated_monthly_savings_usd")} for r in ds.recommendations],
        "capacity_risks": ds.capacity_risks.head(6).to_dict(orient="records"),
        "open_alerts": [{k: a[k] for k in ("severity", "category", "title")} for a in open_alerts[:10]],
    }


def classify(question: str) -> list[str]:
    text = question.lower()
    topics = [name for name, words in TOPICS.items() if any(w in text for w in words)]
    return topics or ["summary"]


def _money(value: float) -> str:
    return f"${value:,.2f}"


def fallback_answer(facts: dict, question: str | None) -> str:
    topics = classify(question) if question else ["summary"]
    fleet, costs = facts["fleet"], facts["costs"]
    parts: list[str] = []
    label = " (simulated data)" if facts["data_source"].startswith("SIMULATED") else ""

    if "summary" in topics:
        counts = fleet["status_counts"]
        parts.append(
            f"**Infrastructure summary{label}, as of {facts['as_of'][:16].replace('T', ' ')}.** "
            f"{fleet['monitored_count']} of {fleet['resource_count']} resources report telemetry: {counts['healthy']} healthy, "
            f"{counts['warning']} warning, {counts['critical']} critical (health score {fleet['health_score']}). "
            f"Average CPU {fleet['avg_cpu_pct']}%, memory {fleet['avg_memory_pct']}%, 24h availability {fleet['availability_24h_pct']}%.")
        change = costs["change_pct"]
        parts.append(f"Spend over the last 30 days was {_money(costs['last_30d_usd'])}"
                     + (f" ({change:+.1f}% vs the prior 30 days)" if change is not None else "")
                     + f"; this month is on track for about {_money(costs['month_end_estimate_usd'])}. "
                     f"Identified savings: {_money(costs['potential_monthly_savings_usd'])}/month.")
    if "cost" in topics or "summary" in topics:
        recs = facts["recommendations"][:5]
        if recs:
            lines = [f"- **{r['resource']}** ({r['category']}): {r['action']}. {r['reason']} "
                     f"Saves ~{_money(r['estimated_monthly_savings_usd'])}/month of {_money(r['monthly_cost_usd'])}." for r in recs]
            parts.append("**Top optimization opportunities**\n" + "\n".join(lines))
        if "cost" in topics:
            top = costs["top_service"]
            parts.append(f"{top['service']} is the largest cost driver at {_money(top['cost_usd'])} ({top['share_pct']}% of 30-day spend).")
            for spike in facts["recent_cost_spikes"]:
                parts.append(f"Cost spike: {spike['resource']} spent {_money(spike['cost_usd'])} on {spike['date']} "
                             f"against an expected {_money(spike['expected_usd'])}. Check for runaway jobs or traffic changes.")
    if "performance" in topics:
        stressed = facts["stressed_resources"]
        if stressed:
            parts.append("**Resources under pressure**\n" + "\n".join(
                f"- {s['name']} ({s['status']}): {'; '.join(s['reasons'])}" for s in stressed))
            parts.append("Consider horizontal scaling or a larger instance tier for sustained CPU above 85%, and review memory "
                         "limits where memory pressure persists.")
        else:
            parts.append("No monitored resource is above its CPU or memory thresholds right now.")
    if "capacity" in topics:
        risks = facts["capacity_risks"]
        if risks:
            parts.append("**Capacity outlook** (linear trend on daily averages)\n" + "\n".join(
                f"- {r['resource']} {r['metric'].replace('_pct', '')}: {r['current_pct']}% now, reaches 85% in ~{r['days_to_threshold']} days"
                for r in risks))
        fc = facts["forecast_next_30d"]
        parts.append(f"Next 30 days spend forecast: {_money(fc['projected_usd'])} (90% interval {_money(fc['low_usd'])} - {_money(fc['high_usd'])}).")
    if "reliability" in topics:
        alerts = facts["open_alerts"]
        parts.append(f"24h availability is {fleet['availability_24h_pct']}%. " + (
            f"There are {len(alerts)} open alerts: " + "; ".join(f"[{a['severity']}] {a['title']}" for a in alerts[:6]) + "."
            if alerts else "There are no open alerts."))
    if "kubernetes" in topics:
        nodes = [s for s in facts["stressed_resources"] if s["name"].startswith("k8s-node")]
        parts.append("Kubernetes nodes under pressure: " + ", ".join(f"{n['name']} ({'; '.join(n['reasons'])})" for n in nodes)
                     + ". Add a node or set resource limits so low-priority pods are not evicted." if nodes
                     else "All Kubernetes nodes are within CPU and memory thresholds.")
    return "\n\n".join(parts)


HttpPost = Callable[..., object]


def ask_claude(facts: dict, question: str, settings: Settings, post: HttpPost | None = None) -> str:
    if post is None:
        import httpx
        post = httpx.post
    payload = {"model": settings.anthropic_model, "max_tokens": 900, "system": SYSTEM_PROMPT,
               "messages": [{"role": "user", "content": f"Facts (JSON):\n{json.dumps(facts, default=str)}\n\nQuestion: {question}"}]}
    response = post(ANTHROPIC_URL, json=payload, timeout=45.0, headers={
        "x-api-key": settings.anthropic_api_key, "anthropic-version": "2023-06-01", "content-type": "application/json"})
    response.raise_for_status()
    body = response.json()
    text = "".join(block.get("text", "") for block in body.get("content", []) if block.get("type") == "text").strip()
    if not text:
        raise ValueError("empty response from model")
    return text


def advise(ds: Dataset, settings: Settings, open_alerts: list[dict], question: str | None = None,
           post: HttpPost | None = None) -> dict:
    facts = build_facts(ds, settings, open_alerts)
    prompt = question or "Give an executive summary of infrastructure health, spending and the most valuable optimizations."
    result = {"question": question, "topics": classify(question) if question else ["summary"], "data_source": ds.data_source,
              "generated_at": datetime.now(UTC).replace(microsecond=0).isoformat(),
              "estimated_monthly_savings_usd": facts["costs"]["potential_monthly_savings_usd"],
              "recommendations": facts["recommendations"]}
    if settings.anthropic_api_key:
        try:
            answer = ask_claude(facts, prompt, settings, post)
            return {**result, "mode": "ai", "model": settings.anthropic_model, "answer": answer,
                    "notice": "AI-generated from CloudPulse's computed facts. Verify before acting."}
        except Exception as exc:
            log.warning("advisor AI call failed, using fallback: %s", type(exc).__name__)
            return {**result, "mode": "fallback", "model": None, "answer": fallback_answer(facts, question),
                    "notice": f"AI call failed ({type(exc).__name__}); showing rule-based fallback."}
    return {**result, "mode": "fallback", "model": None, "answer": fallback_answer(facts, question), "notice": FALLBACK_NOTICE}
