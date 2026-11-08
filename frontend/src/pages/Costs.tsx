import { useState } from 'react';
import { DataView, RankedBars, StackedDaily } from '../components/charts';
import { Empty, Figures, PageHeader, Panel, Query, Segmented, Table } from '../components/ui';
import { day, signedPct, title, usd } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { Breakdown, CostAnomalies, CostSummary, Daily, Recommendations } from '../lib/types';

export default function Costs() {
  const [days, setDays] = useState(30);
  const [dailyBy, setDailyBy] = useState<'service' | 'environment'>('service');
  const [by, setBy] = useState<'service' | 'resource' | 'environment'>('service');
  const summary = useApi<CostSummary>('/finops/summary');
  const daily = useApi<Daily>(`/finops/daily?by=${dailyBy}&days=${days}`);
  const breakdown = useApi<Breakdown>(`/finops/breakdown?by=${by}&days=${days}`);
  const anomalies = useApi<CostAnomalies>('/finops/anomalies');
  const recs = useApi<Recommendations>('/finops/recommendations');

  return (
    <div className="space-y-5">
      <PageHeader heading="Costs" intro="Where the money goes, what changed, and what to cut." source={summary.data?.data_source}>
        <Segmented label="Period" value={days} onChange={setDays} options={[{ value: 30, label: '30 days' }, { value: 60, label: '60 days' }, { value: 90, label: '90 days' }]} />
      </PageHeader>
      <Query q={summary}>
        {(s) => (
          <Panel>
            <Figures items={[
              { label: 'Last 30 days', value: usd(s.last_30d_usd), detail: `${signedPct(s.change_pct)} vs prior 30 days` },
              { label: 'Month to date', value: usd(s.month_to_date_usd), detail: `Through ${day(s.as_of)}` },
              { label: 'Month-end estimate', value: usd(s.month_end_estimate_usd), detail: 'Actuals plus forecast' },
              { label: 'Daily average', value: usd(s.daily_average_usd) },
              { label: 'Possible savings', value: `${usd(s.potential_monthly_savings_usd)}/mo`, detail: `${(s.potential_monthly_savings_usd / s.last_30d_usd * 100).toFixed(0)}% of 30-day spend` },
            ]} />
          </Panel>
        )}
      </Query>
      <div className="grid gap-5 xl:grid-cols-3">
        <Panel className="xl:col-span-2" heading="Daily spend" action={<Segmented label="Split daily spend by" value={dailyBy} onChange={setDailyBy} options={[{ value: 'service', label: 'Service' }, { value: 'environment', label: 'Environment' }]} />}>
          <Query q={daily}>
            {(d) => (
              <>
                <StackedDaily points={d.points} series={d.series} />
                <DataView label="Daily spend" columns={['Date', ...d.series, 'Total']} rows={d.points.map((p) => [day(p.date), ...d.series.map((s) => usd(Number(p[s] ?? 0), 2)), usd(p.total, 2)])} />
              </>
            )}
          </Query>
        </Panel>
        <Panel heading="Breakdown" action={<Segmented label="Break down by" value={by} onChange={setBy} options={[{ value: 'service', label: 'Service' }, { value: 'resource', label: 'Resource' }, { value: 'environment', label: 'Env' }]} />}>
          <Query q={breakdown}>
            {(b) => (
              <div className="max-h-[370px] overflow-y-auto pr-1">
                <RankedBars items={b.items.map((i) => ({ name: String(i[b.by]), value: i.cost_usd, display: `${usd(i.cost_usd)} (${i.share_pct.toFixed(1)}%)` }))} />
              </div>
            )}
          </Query>
        </Panel>
      </div>
      <Panel heading="Savings opportunities" note={recs.data ? `${usd(recs.data.total_monthly_savings_usd)} per month, computed from each resource's own spend and usage` : undefined}>
        <Query q={recs}>
          {(r) => r.items.length === 0 ? <Empty>No savings found in the current data.</Empty> : (
            <ul className="divide-y divide-line">
              {r.items.map((item) => (
                <li key={item.resource} className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 py-3 first:pt-0">
                  <div className="min-w-0 max-w-3xl flex-1 basis-72">
                    <p className="font-medium">{item.resource}: {item.action}</p>
                    <p className="text-sm text-muted">{title(item.category)}. {item.reason}</p>
                  </div>
                  <p className="num"><span className="font-semibold">{usd(item.estimated_monthly_savings_usd)}/mo</span> <span className="text-sm text-muted">of {usd(item.monthly_cost_usd)}</span></p>
                </li>
              ))}
            </ul>
          )}
        </Query>
      </Panel>
      <Panel heading="Unusual spending" note={anomalies.data?.method}>
        <Query q={anomalies}>
          {(a) => a.items.length === 0 ? <Empty>No unusual spending detected.</Empty> : (
            <Table label="Unusual spending">
              <thead><tr><th>Date</th><th>Resource</th><th>Service</th><th className="text-right!">Actual</th><th className="text-right!">Expected</th><th className="text-right!">Excess</th><th className="text-right!">Score</th></tr></thead>
              <tbody>
                {a.items.map((i) => (
                  <tr key={i.date + i.resource} className="num">
                    <td className="whitespace-nowrap">{day(i.date)}</td><td className="font-medium">{i.resource}</td><td>{i.service}</td>
                    <td className="text-right">{usd(i.cost_usd, 2)}</td><td className="text-right">{usd(i.expected_usd, 2)}</td><td className="text-right">+{usd(i.excess_usd, 2)}</td><td className="text-right">{i.score.toFixed(1)}</td>
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
