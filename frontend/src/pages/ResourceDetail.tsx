import { ChevronLeft } from 'lucide-react';
import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { Lines } from '../components/charts';
import { Empty, Figures, PageHeader, Panel, Query, Segmented, Status } from '../components/ui';
import { dateTime, day, pct, title, usd } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { Metrics, Resources } from '../lib/types';

const RANGES = [
  { value: 24, label: '24 h', resolution: 'hour' },
  { value: 168, label: '7 days', resolution: 'hour' },
  { value: 720, label: '30 days', resolution: 'day' },
];

export default function ResourceDetail() {
  const name = useParams().name ?? '';
  const [hours, setHours] = useState(168);
  const resolution = RANGES.find((r) => r.value === hours)?.resolution ?? 'hour';
  const resources = useApi<Resources>('/infrastructure/resources');
  const metrics = useApi<Metrics>(`/infrastructure/resources/${encodeURIComponent(name)}/metrics?hours=${hours}&resolution=${resolution}`);
  const r = resources.data?.items.find((item) => item.name === name);
  const xFormat = resolution === 'day' ? day : dateTime;

  return (
    <div className="space-y-5">
      <Link to="/infrastructure" className="inline-flex items-center gap-1 text-sm text-accent hover:underline"><ChevronLeft size={16} aria-hidden />Infrastructure</Link>
      <PageHeader heading={name} intro={r ? `${title(r.kind)} in ${r.environment}, ${r.region}` : undefined} source={r?.data_source}>
        {r && <Status status={r.status} />}
      </PageHeader>
      <Query q={resources}>
        {() => !r ? <Empty>No resource is named {name}. Pick one from the Infrastructure list.</Empty> : (
          <Panel>
            <Figures items={[
              { label: 'CPU', value: pct(r.cpu_pct) },
              { label: 'Memory', value: pct(r.memory_pct) },
              { label: 'Disk', value: pct(r.disk_pct) },
              { label: 'Availability, 24 h', value: pct(r.availability_24h_pct, 2) },
              { label: '30-day cost', value: usd(r.cost_30d_usd, 2) },
            ]} />
            {r.reasons.length > 0 && <p className="mt-3 text-sm text-muted">{r.reasons.join('. ')}.</p>}
          </Panel>
        )}
      </Query>
      {r && r.cpu_pct !== null && (
        <>
          <Panel heading="Utilization" action={<Segmented label="Time range" value={hours} onChange={setHours} options={RANGES} />}>
            <Query q={metrics}>
              {(m) => <Lines data={m.points} x="timestamp" xFormat={xFormat} domain={[0, 100]} height={280} series={[
                { key: 'cpu_pct', label: 'CPU', color: 'var(--s-1)' },
                { key: 'memory_pct', label: 'Memory', color: 'var(--s-2)' },
                { key: 'disk_pct', label: 'Disk', color: 'var(--s-3)' },
              ]} />}
            </Query>
          </Panel>
          <Query q={metrics}>
            {(m) => (
              <div className="grid gap-5 lg:grid-cols-2">
                <Panel heading="Network traffic">
                  <Lines data={m.points} x="timestamp" xFormat={xFormat} height={200} width={72} format={(v) => `${v.toFixed(0)} Mbps`} series={[{ key: 'network_mbps', label: 'Network', color: 'var(--accent)' }]} />
                </Panel>
                <Panel heading="Availability" note={resolution === 'day' ? 'Share of each day the health check passed' : 'Hourly health check'}>
                  <Lines data={m.points.map((p) => ({ ...p, up: p.available * 100 }))} x="timestamp" xFormat={xFormat} height={200} domain={[0, 100]} series={[{ key: 'up', label: 'Available', color: 'var(--accent)' }]} />
                </Panel>
              </div>
            )}
          </Query>
        </>
      )}
    </div>
  );
}
