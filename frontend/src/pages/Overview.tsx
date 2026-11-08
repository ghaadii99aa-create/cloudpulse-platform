import { Link } from 'react-router-dom';
import { DataView, ForecastRibbon, Lines, RankedBars } from '../components/charts';
import { DataBadge, Empty, Panel, Query, Status } from '../components/ui';
import { dateTime, day, METRIC_LABEL, monthName, pct, signedPct, usd } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { Executive } from '../lib/types';

export function headline(d: Executive): string {
  const { healthy, warning, critical } = d.health.status_counts;
  const fleet = critical > 0
    ? `${critical} of ${d.health.monitored_count} monitored resources ${critical === 1 ? 'is' : 'are'} critical`
    : warning > 0
      ? `${healthy} of ${d.health.monitored_count} monitored resources are healthy and ${warning} need${warning === 1 ? 's' : ''} attention`
      : `All ${d.health.monitored_count} monitored resources are healthy`;
  return `${fleet}. ${monthName(d.costs.month)} is on track to cost ${usd(d.costs.month_end_estimate_usd)}.`;
}

function Fact({ label, value, detail, to }: { label: string; value: string; detail: string; to: string }) {
  return (
    <Link to={to} className="group block min-w-0 rounded-md py-1">
      <p className="text-sm text-muted">{label}</p>
      <p className="num font-display text-3xl font-semibold group-hover:text-accent">{value}</p>
      <p className="text-sm text-muted">{detail}</p>
    </Link>
  );
}

export default function Overview() {
  const q = useApi<Executive>('/dashboard/executive', { refetchInterval: 60_000 });
  return (
    <Query q={q}>
      {(d) => (
        <div className="space-y-5">
          <header className="pb-1">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-muted">
              <DataBadge source={d.data_source} />
              <span>Metrics as of {dateTime(d.health.as_of)}</span>
            </div>
            <h1 className="mt-3 max-w-4xl font-display text-3xl font-semibold leading-[1.12] tracking-tight sm:text-[2.75rem]">{headline(d)}</h1>
            <div className="mt-6 grid grid-cols-2 gap-x-6 gap-y-4 lg:grid-cols-4">
              <Fact to="/infrastructure" label="Fleet health" value={`${d.health.health_score.toFixed(1)}`} detail={`${pct(d.health.availability_24h_pct)} available over 24 h`} />
              <Fact to="/costs" label="Spend, last 30 days" value={usd(d.costs.last_30d_usd)} detail={`${signedPct(d.costs.change_pct)} vs prior 30 days`} />
              <Fact to="/costs" label="Savings found" value={`${usd(d.costs.potential_monthly_savings_usd)}/mo`} detail={`${d.top_recommendations.length} top actions below`} />
              <Fact to="/alerts" label="Active alerts" value={String(d.active_alerts.total)} detail={`${d.active_alerts.critical} critical, ${d.active_alerts.warning} warning`} />
            </div>
          </header>

          <Panel heading="Daily spend and 30-day forecast" note={`Projected next 30 days: ${usd(d.cost_forecast.total.forecast)} (${usd(d.cost_forecast.total.lower)} to ${usd(d.cost_forecast.total.upper)}). Backtest error ${d.cost_forecast.backtest.mape_pct}% over ${d.cost_forecast.backtest.holdout_days} days.`}>
            <ForecastRibbon history={d.cost_forecast.history.map((p) => ({ date: p.date, value: p.cost_usd }))} forecast={d.cost_forecast.forecast} />
            <DataView label="Daily spend and forecast" columns={['Date', 'Actual', 'Forecast', 'Low', 'High']} rows={[
              ...d.cost_forecast.history.map((p) => [day(p.date), usd(p.cost_usd, 2), '', '', '']),
              ...d.cost_forecast.forecast.map((p) => [day(p.date), '', usd(p.forecast, 2), usd(p.lower, 2), usd(p.upper, 2)]),
            ]} />
          </Panel>

          <div className="grid gap-5 xl:grid-cols-5">
            <Panel className="xl:col-span-3" heading="Fleet utilization, last 30 days" note="Daily mean across monitored resources">
              <Lines data={d.utilization_trend} x="date" domain={[0, 100]} height={350} series={[
                { key: 'cpu_pct', label: 'CPU', color: 'var(--s-1)' },
                { key: 'memory_pct', label: 'Memory', color: 'var(--s-2)' },
                { key: 'disk_pct', label: 'Disk', color: 'var(--s-3)' },
              ]} />
            </Panel>
            <Panel className="xl:col-span-2" heading="Needs attention" action={<Link to="/alerts" className="text-sm text-accent hover:underline">All alerts</Link>}>
              {d.active_alerts.items.length === 0 ? <Empty>No active alerts.</Empty> : (
                <ul className="divide-y divide-line">
                  {d.active_alerts.items.slice(0, 4).map((a) => (
                    <li key={a.id} className="py-2.5 first:pt-0">
                      <Status status={a.severity} />
                      <p className="font-medium">{a.title}</p>
                      <p className="text-sm text-muted">{a.message}</p>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>

          <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-3">
            <Panel heading="Spend by service" note="Last 30 days">
              <RankedBars items={d.cost_by_service.map((s) => ({ name: s.service, value: s.cost_usd, display: `${usd(s.cost_usd)} (${s.share_pct.toFixed(0)}%)` }))} />
            </Panel>
            <Panel heading="Top savings" action={<Link to="/costs" className="text-sm text-accent hover:underline">All savings</Link>}>
              <ul className="divide-y divide-line">
                {d.top_recommendations.map((r) => (
                  <li key={r.resource} className="flex items-baseline justify-between gap-3 py-2 first:pt-0">
                    <div className="min-w-0"><p className="font-medium">{r.resource}</p><p className="text-sm text-muted">{r.action}</p></div>
                    <p className="num shrink-0 font-medium">{usd(r.estimated_monthly_savings_usd)}/mo</p>
                  </li>
                ))}
              </ul>
            </Panel>
            <Panel heading="Capacity risks" note="Time until each metric reaches its threshold" className="lg:col-span-2 xl:col-span-1">
              {d.capacity_risks.length === 0 ? <Empty>No resource is projected to reach its threshold.</Empty> : (
                <ul className="divide-y divide-line">
                  {d.capacity_risks.map((r) => (
                    <li key={r.resource + r.metric} className="flex items-baseline justify-between gap-3 py-2 first:pt-0">
                      <div className="min-w-0"><p className="font-medium">{r.resource}</p><p className="text-sm text-muted">{METRIC_LABEL[r.metric] ?? r.metric} at {pct(r.current_pct)}</p></div>
                      <p className="num shrink-0 font-medium">{r.days_to_threshold.toFixed(0)} days</p>
                    </li>
                  ))}
                </ul>
              )}
            </Panel>
          </div>
        </div>
      )}
    </Query>
  );
}
