"""Executive PDF report built with ReportLab from the same computed views the API serves."""
from __future__ import annotations

import io
from datetime import UTC, datetime

from reportlab.graphics.charts.barcharts import HorizontalBarChart
from reportlab.graphics.charts.lineplots import LinePlot
from reportlab.graphics.shapes import Drawing, String
from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..config import Settings
from .dataset import Dataset
from .insights import cost_forecast, cost_summary, fleet_summary, resource_status

INK = colors.HexColor("#1F2933")
MUTED = colors.HexColor("#616E7C")
RULE = colors.HexColor("#D9DEE4")
ACCENT = colors.HexColor("#2F5D8A")
BAND = colors.HexColor("#E8EEF4")
STATUS_COLORS = {"critical": colors.HexColor("#B42318"), "warning": colors.HexColor("#B54708"),
                 "healthy": colors.HexColor("#2F6B3B"), "no_telemetry": MUTED}


def _styles():
    base = getSampleStyleSheet()
    return {
        "title": ParagraphStyle("t", parent=base["Title"], fontName="Helvetica-Bold", fontSize=20, textColor=INK, alignment=TA_LEFT, spaceAfter=2),
        "subtitle": ParagraphStyle("s", parent=base["Normal"], fontSize=9.5, textColor=MUTED, spaceAfter=10),
        "h2": ParagraphStyle("h2", parent=base["Heading2"], fontName="Helvetica-Bold", fontSize=13, textColor=INK, spaceBefore=12, spaceAfter=6),
        "body": ParagraphStyle("b", parent=base["Normal"], fontSize=9.5, leading=13.5, textColor=INK),
        "small": ParagraphStyle("sm", parent=base["Normal"], fontSize=8, leading=11, textColor=MUTED),
        "cell": ParagraphStyle("c", parent=base["Normal"], fontSize=8.2, leading=10.5, textColor=INK),
    }


def _table(rows, widths, numeric_cols=(), header=True):
    table = Table(rows, colWidths=widths, repeatRows=1 if header else 0)
    style = [("FONT", (0, 0), (-1, -1), "Helvetica", 8.2), ("TEXTCOLOR", (0, 0), (-1, -1), INK),
             ("LINEBELOW", (0, 0), (-1, -1), 0.4, RULE), ("VALIGN", (0, 0), (-1, -1), "TOP"),
             ("TOPPADDING", (0, 0), (-1, -1), 3.5), ("BOTTOMPADDING", (0, 0), (-1, -1), 3.5)]
    if header:
        style += [("FONT", (0, 0), (-1, 0), "Helvetica-Bold", 8), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                  ("LINEBELOW", (0, 0), (-1, 0), 0.8, INK)]
    for col in numeric_cols:
        style.append(("ALIGN", (col, 0), (col, -1), "RIGHT"))
    table.setStyle(TableStyle(style))
    return table


def _money(v) -> str:
    return "-" if v is None else f"${v:,.2f}"


def _cost_chart(forecast: dict, width: float) -> Drawing:
    history, future = forecast["history"], forecast["forecast"]
    drawing = Drawing(width, 150)
    plot = LinePlot()
    plot.x, plot.y, plot.width, plot.height = 40, 22, width - 55, 115
    hist = [(i, p["cost_usd"]) for i, p in enumerate(history)]
    offset = len(history)
    fc = [(offset + i, p["forecast"]) for i, p in enumerate(future)]
    lo = [(offset + i, p["lower"]) for i, p in enumerate(future)]
    hi = [(offset + i, p["upper"]) for i, p in enumerate(future)]
    plot.data = [hist, fc, lo, hi]
    for idx, (color, width_, dash) in enumerate([(INK, 1.3, None), (ACCENT, 1.5, None), (ACCENT, 0.6, (2, 2)), (ACCENT, 0.6, (2, 2))]):
        plot.lines[idx].strokeColor = color
        plot.lines[idx].strokeWidth = width_
        plot.lines[idx].symbol = None
        if dash:
            plot.lines[idx].strokeDashArray = dash
    values = [v for series in plot.data for _, v in series]
    plot.yValueAxis.valueMin = 0
    plot.yValueAxis.valueMax = max(values) * 1.1
    plot.yValueAxis.labels.fontSize = 7
    plot.yValueAxis.labels.fontName = "Helvetica"
    plot.yValueAxis.labelTextFormat = lambda v: f"${v:,.0f}"
    plot.yValueAxis.strokeColor = RULE
    plot.xValueAxis.visibleLabels = False
    plot.xValueAxis.strokeColor = RULE
    drawing.add(plot)
    drawing.add(String(40, 6, f"{history[0]['date']}  ->  {future[-1]['date']}   solid: actual daily spend, blue: forecast with 90% interval",
                       fontSize=7, fontName="Helvetica", fillColor=MUTED))
    return drawing


def _breakdown_chart(rows: list[dict], width: float) -> Drawing:
    drawing = Drawing(width, 18 * len(rows) + 20)
    chart = HorizontalBarChart()
    chart.x, chart.y, chart.width, chart.height = 80, 10, width - 130, 18 * len(rows)
    chart.data = [[r["cost_usd"] for r in reversed(rows)]]
    chart.categoryAxis.categoryNames = [r["service"] for r in reversed(rows)]
    chart.categoryAxis.labels.fontSize = 8
    chart.categoryAxis.labels.fontName = "Helvetica"
    chart.valueAxis.labels.fontName = "Helvetica"
    chart.barLabels.fontName = "Helvetica"
    chart.categoryAxis.strokeColor = RULE
    chart.valueAxis.valueMin = 0
    chart.valueAxis.labels.fontSize = 7
    chart.valueAxis.labelTextFormat = lambda v: f"${v:,.0f}"
    chart.valueAxis.strokeColor = RULE
    chart.bars[0].fillColor = ACCENT
    chart.bars[0].strokeColor = None
    chart.barLabelFormat = lambda v: f"${v:,.0f}"
    chart.barLabels.fontSize = 7
    chart.barLabels.boxAnchor = "w"
    chart.barLabels.dx = 3
    drawing.add(chart)
    return drawing


def build_executive_report(ds: Dataset, settings: Settings, alerts: list[dict], generated_by: str) -> bytes:
    s = _styles()
    buffer = io.BytesIO()
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    simulated = ds.data_source.startswith("SIMULATED")

    def frame(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(MUTED)
        canvas.drawString(18 * mm, 10 * mm, f"CloudPulse executive report  |  data source: {ds.data_source}  |  generated {generated}")
        canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
        canvas.restoreState()

    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=18 * mm,
                            title="CloudPulse Executive Report", author="CloudPulse")
    width = A4[0] - 36 * mm
    fleet, costs, forecast = fleet_summary(ds, settings), cost_summary(ds), cost_forecast(ds)
    story = [Paragraph("CloudPulse Executive Report", s["title"]),
             Paragraph(f"Infrastructure, cost and forecast review as of {fleet['as_of'][:16].replace('T', ' ')}. "
                       f"Generated {generated} for {generated_by}.", s["subtitle"])]
    if simulated:
        notice = Table([[Paragraph("<b>Simulated data.</b> Every figure in this report is computed from CloudPulse's generated demo "
                                   "environment, not from a real cloud account. Prices are illustrative.", s["cell"])]], colWidths=[width])
        notice.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), BAND), ("BOX", (0, 0), (-1, -1), 0.5, RULE),
                                    ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6)]))
        story += [notice, Spacer(1, 8)]

    counts = fleet["status_counts"]
    kpis = [["Health score", "Availability (24h)", "Spend, last 30 days", "Month-end estimate", "Savings identified"],
            [f"{fleet['health_score']}", f"{fleet['availability_24h_pct']}%", _money(costs["last_30d_usd"]),
             _money(costs["month_end_estimate_usd"]), f"{_money(costs['potential_monthly_savings_usd'])}/mo"]]
    kpi = Table(kpis, colWidths=[width / 5] * 5)
    kpi.setStyle(TableStyle([("FONT", (0, 0), (-1, 0), "Helvetica", 7.5), ("TEXTCOLOR", (0, 0), (-1, 0), MUTED),
                             ("FONT", (0, 1), (-1, 1), "Helvetica-Bold", 13), ("TEXTCOLOR", (0, 1), (-1, 1), INK),
                             ("LINEABOVE", (0, 0), (-1, 0), 1, INK), ("TOPPADDING", (0, 0), (-1, -1), 4)]))
    change = costs["change_pct"]
    story += [Paragraph("Executive summary", s["h2"]), kpi, Spacer(1, 6), Paragraph(
        f"{fleet['monitored_count']} of {fleet['resource_count']} resources report telemetry: {counts['healthy']} healthy, "
        f"{counts['warning']} warning and {counts['critical']} critical. Spend over the last 30 days was "
        f"{_money(costs['last_30d_usd'])}" + (f", {change:+.1f}% against the previous 30 days" if change is not None else "")
        + f". {costs['top_service']['service']} is the largest cost driver at {costs['top_service']['share_pct']}% of spend. "
        f"{sum(a['status'] == 'open' for a in alerts)} alerts are open.", s["body"])]

    breakdown = ds.breakdown("service").to_dict(orient="records")
    story += [Paragraph("Cost analysis", s["h2"]), _breakdown_chart(breakdown, width), Spacer(1, 4)]
    top_resources = ds.breakdown("resource").head(8)
    rows = [["Resource", "30-day cost", "Share"]] + [[r.resource, _money(r.cost_usd), f"{r.share_pct}%"] for r in top_resources.itertuples()]
    story += [Paragraph("Top resources by 30-day cost", s["small"]), _table(rows, [width * 0.5, width * 0.3, width * 0.2], (1, 2))]
    spikes = ds.cost_spikes
    if not spikes.empty:
        rows = [["Date", "Resource", "Actual", "Expected", "Excess"]] + [
            [r.date.date().isoformat(), r.resource, _money(r.cost_usd), _money(r.expected_usd), _money(r.excess_usd)]
            for r in spikes.itertuples()]
        story += [Spacer(1, 6), Paragraph("Detected cost anomalies (robust z-score against each resource's own baseline)", s["small"]),
                  _table(rows, [width * 0.18, width * 0.3, width * 0.17, width * 0.17, width * 0.18], (2, 3, 4))]

    total = forecast["total"]
    story += [KeepTogether([Paragraph("Spend forecast", s["h2"]), _cost_chart(forecast, width), Paragraph(
        f"Next {forecast['horizon_days']} days: {_money(total['forecast'])} (90% interval {_money(total['lower'])} to "
        f"{_money(total['upper'])}). Model: {forecast['model']}. Backtest on the last {forecast['backtest']['holdout_days']} unseen days: "
        f"MAPE {forecast['backtest']['mape_pct']}%, interval coverage {forecast['backtest']['interval_coverage_pct']}%.", s["body"])])]

    statuses = [r for r in resource_status(ds, settings) if r["status"] != "no_telemetry"]
    rows = [["Resource", "Env", "Status", "CPU", "Memory", "Disk", "Avail. 24h"]]
    for r in sorted(statuses, key=lambda r: ({"critical": 0, "warning": 1}.get(r["status"], 2), r["name"])):
        rows.append([r["name"], r["environment"], r["status"], f"{r['cpu_pct']:.1f}%", f"{r['memory_pct']:.1f}%",
                     f"{r['disk_pct']:.1f}%", f"{r['availability_24h_pct']:.1f}%"])
    perf = _table(rows, [width * 0.26, width * 0.1, width * 0.14, width * 0.12, width * 0.12, width * 0.12, width * 0.14], (3, 4, 5, 6))
    for i, r in enumerate(rows[1:], start=1):
        perf.setStyle(TableStyle([("TEXTCOLOR", (2, i), (2, i), STATUS_COLORS.get(r[2], INK)), ("FONT", (2, i), (2, i), "Helvetica-Bold", 8.2)]))
    story += [Paragraph("Infrastructure performance", s["h2"]), perf]
    risks = ds.capacity_risks.head(6)
    if not risks.empty:
        rows = [["Resource", "Metric", "Now", "Trend/day", "Days to 85%"]] + [
            [r.resource, r.metric.replace("_pct", ""), f"{r.current_pct}%", f"+{r.daily_change_pct}", f"{r.days_to_threshold}"]
            for r in risks.itertuples()]
        story += [Spacer(1, 6), Paragraph("Capacity outlook (linear trend on daily averages)", s["small"]),
                  _table(rows, [width * 0.3, width * 0.15, width * 0.15, width * 0.2, width * 0.2], (2, 3, 4))]

    recs = ds.recommendations
    rows = [["Resource", "Action", "Why", "Saves / month"]] + [
        [r["resource"], Paragraph(r["action"], s["cell"]), Paragraph(r["reason"], s["cell"]), _money(r["estimated_monthly_savings_usd"])]
        for r in recs]
    story += [Paragraph("Recommendations", s["h2"]),
              _table(rows, [width * 0.2, width * 0.24, width * 0.4, width * 0.16], (3,)),
              Paragraph(f"Total identified savings: <b>{_money(costs['potential_monthly_savings_usd'])}</b> per month, computed from each "
                        "resource's own recent spend.", s["body"])]

    open_alerts = [a for a in alerts if a["status"] != "resolved"][:15]
    if open_alerts:
        rows = [["Severity", "Category", "Alert"]] + [[a["severity"], a["category"], Paragraph(a["title"], s["cell"])] for a in open_alerts]
        story += [Paragraph("Active alerts", s["h2"]), _table(rows, [width * 0.15, width * 0.15, width * 0.7])]

    story += [Spacer(1, 10), Paragraph(
        "Method notes: health score = " + fleet["health_score_method"] + ". Cost anomalies use a 29-day rolling median and MAD. "
        "Recommendations are rule-based on observed utilization (idle non-production, oversized p95, unattached volumes).", s["small"])]
    doc.build(story, onFirstPage=frame, onLaterPages=frame)
    return buffer.getvalue()
