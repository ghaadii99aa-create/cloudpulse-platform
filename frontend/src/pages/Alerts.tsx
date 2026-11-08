import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { Button, Empty, Figures, PageHeader, Panel, Query, Select, Status } from '../components/ui';
import { api, ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { dateTime, title } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { Alert, AlertPage, AlertSummary } from '../lib/types';

const PAGE = 20;
const ALL = { value: 'all', label: 'All' };
const refreshKeys = ['/alerts', '/dashboard/executive'];

function Row({ alert, canAct, onAct, busy }: { alert: Alert; canAct: boolean; busy: boolean; onAct: (id: number, action: 'acknowledge' | 'resolve') => void }) {
  return (
    <li className="flex flex-wrap items-start justify-between gap-x-6 gap-y-2 py-3 first:pt-0">
      <div className="min-w-0 max-w-3xl flex-1 basis-80">
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <Status status={alert.severity} />
          <span className="text-sm text-muted">{title(alert.category)}, {title(alert.status)}</span>
        </div>
        <p className="mt-0.5 font-medium">{alert.title}</p>
        <p className="text-sm text-muted">{alert.message}</p>
        <p className="mt-1 text-sm text-muted">
          Observed {dateTime(alert.observed_at)}
          {alert.acknowledged_at && `. Acknowledged ${alert.acknowledged_by ? `by ${alert.acknowledged_by} ` : ''}${dateTime(alert.acknowledged_at)}`}
          {alert.resolved_at && `. Resolved ${dateTime(alert.resolved_at)}`}
        </p>
      </div>
      {canAct && alert.status !== 'resolved' && (
        <div className="flex gap-2">
          {alert.status === 'open' && <Button disabled={busy} onClick={() => onAct(alert.id, 'acknowledge')}>Acknowledge</Button>}
          <Button disabled={busy} onClick={() => onAct(alert.id, 'resolve')}>Resolve</Button>
        </div>
      )}
    </li>
  );
}

export default function Alerts() {
  const { can } = useAuth();
  const client = useQueryClient();
  const [status, setStatus] = useState('active');
  const [severity, setSeverity] = useState('all');
  const [category, setCategory] = useState('all');
  const [offset, setOffset] = useState(0);
  const [message, setMessage] = useState<{ text: string; error?: boolean } | null>(null);

  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (status !== 'all') params.set('status', status);
  if (severity !== 'all') params.set('severity', severity);
  if (category !== 'all') params.set('category', category);
  const q = useApi<AlertPage>(`/alerts?${params}`);
  const summary = useApi<AlertSummary>('/alerts/summary');

  const refresh = () => client.invalidateQueries({ predicate: (query) => refreshKeys.some((key) => String(query.queryKey[0]).startsWith(key)) });
  const fail = (e: unknown) => setMessage({ text: e instanceof ApiError ? e.message : 'The action failed. Try again.', error: true });

  const act = useMutation({
    mutationFn: ({ id, action }: { id: number; action: 'acknowledge' | 'resolve' }) => api<Alert>(`/alerts/${id}/${action}`, { method: 'POST' }),
    onSuccess: (alert, { action }) => { setMessage({ text: `${alert.title}: ${action === 'resolve' ? 'resolved' : 'acknowledged'}.` }); return refresh(); },
    onError: fail,
  });
  const evaluate = useMutation({
    mutationFn: () => api<object>('/alerts/evaluate', { method: 'POST' }),
    onSuccess: () => { setMessage({ text: 'Alert rules ran against the latest data.' }); return refresh(); },
    onError: fail,
  });
  const filter = (set: (value: string) => void) => (value: string) => { set(value); setOffset(0); };

  return (
    <div className="space-y-5">
      <PageHeader heading="Alerts" intro="CPU, memory, availability, capacity and cost alerts, with their full history." source={q.data?.items[0]?.data_source}>
        {can('engineer') && <Button variant="primary" disabled={evaluate.isPending} onClick={() => evaluate.mutate()}>{evaluate.isPending ? 'Running rules' : 'Run rules now'}</Button>}
      </PageHeader>
      <Query q={summary}>
        {(s) => (
          <Panel>
            <Figures items={[
              { label: 'Active', value: s.active_total },
              { label: 'Critical', value: s.by_severity.critical ?? 0 },
              { label: 'Warning', value: s.by_severity.warning ?? 0 },
              { label: 'Resolved to date', value: s.resolved_total },
            ]} />
          </Panel>
        )}
      </Query>
      <div aria-live="polite">{message && <p className={`rounded-lg bg-panel p-3 ${message.error ? 'text-crit' : 'text-ok'}`}>{message.text}</p>}</div>
      <Panel
        heading="Alert history"
        note={can('engineer') ? undefined : 'Your viewer role can read alerts. Engineers and admins can acknowledge and resolve them.'}
        action={
          <div className="flex flex-wrap gap-3">
            <Select label="Status" value={status} onChange={filter(setStatus)} options={[{ value: 'active', label: 'Active' }, { value: 'open', label: 'Open' }, { value: 'acknowledged', label: 'Acknowledged' }, { value: 'resolved', label: 'Resolved' }, ALL]} />
            <Select label="Severity" value={severity} onChange={filter(setSeverity)} options={[ALL, { value: 'critical', label: 'Critical' }, { value: 'warning', label: 'Warning' }]} />
            <Select label="Category" value={category} onChange={filter(setCategory)} options={[ALL, ...['cpu', 'memory', 'availability', 'capacity', 'cost'].map((c) => ({ value: c, label: title(c) }))]} />
          </div>
        }
      >
        <Query q={q}>
          {(page) => page.items.length === 0 ? <Empty>No alerts match these filters. Change Status to All to see the full history.</Empty> : (
            <>
              <ul className="divide-y divide-line">
                {page.items.map((a) => <Row key={a.id} alert={a} canAct={can('engineer')} busy={act.isPending} onAct={(id, action) => act.mutate({ id, action })} />)}
              </ul>
              <div className="mt-3 flex items-center justify-between gap-3 border-t border-line pt-3 text-sm text-muted">
                <span className="num">{offset + 1} to {offset + page.items.length} of {page.total}</span>
                <span className="flex gap-2">
                  <Button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))}>Previous</Button>
                  <Button disabled={offset + page.items.length >= page.total} onClick={() => setOffset(offset + PAGE)}>Next</Button>
                </span>
              </div>
            </>
          )}
        </Query>
      </Panel>
    </div>
  );
}
