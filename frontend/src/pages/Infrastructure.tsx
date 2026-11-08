import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Empty, Figures, Meter, PageHeader, Panel, Query, Select, Status, Table } from '../components/ui';
import { clock, pct, title, usd } from '../lib/format';
import { useApi, useThresholds } from '../lib/hooks';
import type { FleetSummary, Live, Resources } from '../lib/types';

export default function Infrastructure() {
  const summary = useApi<FleetSummary>('/infrastructure/summary');
  const resources = useApi<Resources>('/infrastructure/resources');
  const live = useApi<Live>('/infrastructure/live', { refetchInterval: 15_000 });
  const limits = useThresholds();
  const [environment, setEnvironment] = useState('all');
  const [status, setStatus] = useState('all');

  const readings = useMemo(() => new Map(live.data?.readings.map((r) => [r.resource, r])), [live.data]);
  const environments = [...new Set(resources.data?.items.map((r) => r.environment))].sort();
  const statuses = [...new Set(resources.data?.items.map((r) => r.status))].sort();
  const rows = resources.data?.items.filter((r) => (environment === 'all' || r.environment === environment) && (status === 'all' || r.status === status)) ?? [];

  return (
    <div className="space-y-5">
      <PageHeader heading="Infrastructure" intro="Health and utilization for every resource in the fleet." source={summary.data?.data_source} />
      <Query q={summary}>
        {(s) => (
          <Panel>
            <Figures items={[
              { label: 'Health score', value: s.health_score.toFixed(1), detail: `${s.status_counts.healthy} healthy, ${s.status_counts.warning} warning, ${s.status_counts.critical} critical` },
              { label: 'Average CPU', value: pct(s.avg_cpu_pct) },
              { label: 'Average memory', value: pct(s.avg_memory_pct) },
              { label: 'Average disk', value: pct(s.avg_disk_pct) },
              { label: 'Network', value: `${s.total_network_mbps.toFixed(0)} Mbps` },
              { label: 'Availability, 24 h', value: pct(s.availability_24h_pct, 2) },
            ]} />
            <p className="mt-3 text-sm text-muted">Health score = {s.health_score_method}. {s.status_counts.no_telemetry} resources do not report host metrics and are left out.</p>
          </Panel>
        )}
      </Query>
      <Panel
        heading="Resources"
        note={live.data ? <span className="inline-flex items-center gap-2"><span className="beat size-2 rounded-full bg-ok-mark" aria-hidden />Simulated live readings, updated {clock(live.data.timestamp)}</span> : 'Latest hour of telemetry'}
        action={
          <div className="flex flex-wrap gap-3">
            <Select label="Environment" value={environment} onChange={setEnvironment} options={[{ value: 'all', label: 'All' }, ...environments.map((e) => ({ value: e, label: e }))]} />
            <Select label="Status" value={status} onChange={setStatus} options={[{ value: 'all', label: 'All' }, ...statuses.map((s) => ({ value: s, label: title(s) }))]} />
          </div>
        }
      >
        <Query q={resources}>
          {() => rows.length === 0 ? <Empty>No resources match these filters. Set both filters to All to see the full fleet.</Empty> : (
            <Table label="Resources">
              <thead>
                <tr><th>Resource</th><th>Status</th><th className="min-w-32">CPU</th><th className="min-w-32">Memory</th><th className="min-w-32">Disk</th><th>Network</th><th className="text-right!">30-day cost</th></tr>
              </thead>
              <tbody>
                {rows.map((r) => {
                  const now = readings.get(r.name);
                  const network = now?.network_mbps ?? r.network_mbps;
                  return (
                    <tr key={r.name}>
                      <td className="whitespace-nowrap">
                        <Link to={`/infrastructure/${encodeURIComponent(r.name)}`} className="font-medium text-accent hover:underline">{r.name}</Link>
                        <div className="text-muted">{r.service}, {r.environment}</div>
                      </td>
                      <td title={r.reasons.join('; ')}><Status status={r.status} /></td>
                      <td><Meter label="CPU" value={now?.cpu_pct ?? r.cpu_pct} warn={limits.cpu_warning_pct} crit={limits.cpu_critical_pct} /></td>
                      <td><Meter label="Memory" value={now?.memory_pct ?? r.memory_pct} warn={limits.memory_warning_pct} crit={limits.memory_critical_pct} /></td>
                      <td><Meter label="Disk" value={now?.disk_pct ?? r.disk_pct} warn={limits.capacity_threshold_pct} crit={95} /></td>
                      <td className="num whitespace-nowrap">{network === null || network === undefined ? 'n/a' : `${network.toFixed(0)} Mbps`}</td>
                      <td className="num text-right">{usd(r.cost_30d_usd)}</td>
                    </tr>
                  );
                })}
              </tbody>
            </Table>
          )}
        </Query>
      </Panel>
    </div>
  );
}
