import { useState } from 'react';
import { DataView, ForecastRibbon } from '../components/charts';
import { Empty, Figures, Meter, PageHeader, Panel, Query, Segmented, Select, Table } from '../components/ui';
import { dateTime, day, METRIC_LABEL, pct, usd } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { Capacity, CostForecast, Resources, UsageAnomalies, UtilForecast } from '../lib/types';

export default function Forecasts() {
  const [horizon, setHorizon] = useState(30);
  const [metric, setMetric] = useState('cpu_pct');
  const [picked, setPicked] = useState<string | null>(null);
  const cost = useApi<CostForecast>(`/analytics/forecast/cost?horizon=${horizon}&history_days=60`);
  const resources = useApi<Resources>('/infrastructure/resources');
  const monitored = resources.data?.items.filter((r) => r.cpu_pct !== null) ?? [];
  const resource = picked ?? monitored[0]?.name;
  const util = useApi<UtilForecast>(`/analytics/forecast/utilization?resource=${encodeURIComponent(resource ?? '')}&metric=${metric}&horizon=14`, { enabled: !!resource });
  const capacity = useApi<Capacity>('/analytics/capacity');
  const usage = useApi<UsageAnomalies>('/analytics/anomalies/usage?limit=20');

  return (
    <div className="space-y-5">
      <PageHeader heading="Forecasts" intro="Projected spend and utilization, with the error of each model shown beside it." source={cost.data?.data_source}>
        <Segmented label="Forecast horizon" value={horizon} onChange={setHorizon} options={[{ value: 14, label: '14 days' }, { value: 30, label: '30 days' }, { value: 90, label: '90 days' }]} />
      </PageHeader>
      <Query q={cost}>
        {(c) => (
          <Panel heading="Spend forecast" note={`${c.model}. ${c.interval}.`}>
            <div className="mb-4">
              <Figures items={[
                { label: `Projected, next ${c.horizon_days} days`, value: usd(c.total.forecast), detail: `${usd(c.total.lower)} to ${usd(c.total.upper)}` },
                { label: 'Backtest error (MAPE)', value: `${c.backtest.mape_pct}%`, detail: `Last ${c.backtest.holdout_days} days held out` },
                { label: 'Interval coverage', value: pct(c.backtest.interval_coverage_pct), detail: 'Target is 90%' },
              ]} />
            </div>
            <ForecastRibbon history={c.history.map((p) => ({ date: p.date, value: p.cost_usd }))} forecast={c.forecast} height={320} />
            <DataView label="Forecast" columns={['Date', 'Forecast', 'Low', 'High']} rows={c.forecast.map((p) => [day(p.date), usd(p.forecast, 2), usd(p.lower, 2), usd(p.upper, 2)])} />
          </Panel>
        )}
      </Query>
      <div className="grid gap-5 xl:grid-cols-2">
        <Panel heading="Utilization forecast" note="Daily mean, next 14 days" action={
          <div className="flex flex-wrap gap-3">
            <Select label="Resource" value={resource ?? ''} onChange={setPicked} options={monitored.map((r) => ({ value: r.name, label: r.name }))} />
            <Select label="Metric" value={metric} onChange={setMetric} options={Object.entries(METRIC_LABEL).map(([value, label]) => ({ value, label }))} />
          </div>
        }>
          <Query q={util}>
            {(u) => <ForecastRibbon history={u.history} forecast={u.forecast} height={410} actualLabel={`Actual ${METRIC_LABEL[u.metric]}`} format={(v) => `${v.toFixed(0)}%`} />}
          </Query>
        </Panel>
        <Panel heading="Capacity outlook" note={capacity.data ? `Metrics projected to reach ${capacity.data.threshold_pct}% within ${capacity.data.within_days} days. ${capacity.data.method}.` : undefined}>
          <Query q={capacity}>
            {(c) => c.items.length === 0 ? <Empty>No resource is projected to reach the threshold.</Empty> : (
              <Table label="Capacity outlook">
                <thead><tr><th>Resource</th><th className="min-w-28">Now</th><th className="text-right!">Per day</th><th className="text-right!">Days left</th></tr></thead>
                <tbody>
                  {c.items.map((i) => (
                    <tr key={i.resource + i.metric} className="num">
                      <td><span className="font-medium">{i.resource}</span> <span className="text-muted">{METRIC_LABEL[i.metric] ?? i.metric}</span></td>
                      <td><Meter label={METRIC_LABEL[i.metric] ?? i.metric} value={i.current_pct} warn={c.threshold_pct} crit={95} /></td>
                      <td className="text-right whitespace-nowrap">+{i.daily_change_pct.toFixed(2)} pts</td>
                      <td className="text-right font-medium">{i.days_to_threshold.toFixed(0)}</td>
                    </tr>
                  ))}
                </tbody>
              </Table>
            )}
          </Query>
        </Panel>
      </div>
      <Panel heading="Unusual usage patterns" note={usage.data ? `${usage.data.method}. Most recent 20.` : undefined}>
        <Query q={usage}>
          {(u) => u.items.length === 0 ? <Empty>No unusual usage detected.</Empty> : (
            <Table label="Unusual usage patterns">
              <thead><tr><th>When</th><th>Resource</th><th className="text-right!">CPU</th><th className="text-right!">Memory</th><th className="text-right!">Network</th></tr></thead>
              <tbody>
                {u.items.map((i) => (
                  <tr key={i.timestamp + i.resource} className="num">
                    <td className="whitespace-nowrap">{dateTime(i.timestamp)}</td><td className="font-medium">{i.resource}</td>
                    <td className="text-right">{pct(i.cpu_pct)}</td><td className="text-right">{pct(i.memory_pct)}</td><td className="text-right whitespace-nowrap">{i.network_mbps.toFixed(0)} Mbps</td>
                  </tr>
                ))}
              </tbody>
            </Table>
          )}
        </Query>
      </Panel>
    </div>
  );
}
