import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useState, type FormEvent } from 'react';
import { Button, ErrorNote, PageHeader, Panel, Query, Status, Table } from '../components/ui';
import { api, ApiError } from '../lib/api';
import { useAuth } from '../lib/auth';
import { dateTime, day, title } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { Role, SystemInfo, User } from '../lib/types';

const ROLES: Role[] = ['viewer', 'engineer', 'admin'];
const field = 'mt-1 block min-h-10 w-full rounded-md border border-line bg-panel px-3 text-sm text-ink';

export function passwordProblem(password: string): string | null {
  if (password.length < 12) return 'Use at least 12 characters.';
  if (!/[a-zA-Z]/.test(password) || !/\d/.test(password)) return 'Use both letters and digits.';
  return null;
}

function apiMessage(error: unknown): string {
  if (error instanceof ApiError) return error.details?.map((d) => `${d.field}: ${d.message}`).join('; ') || error.message;
  return 'The request failed. Try again.';
}

function Users() {
  const { user: me } = useAuth();
  const client = useQueryClient();
  const users = useApi<User[]>('/users');
  const [form, setForm] = useState({ full_name: '', email: '', password: '', role: 'viewer' as Role });
  const [problem, setProblem] = useState<string | null>(null);
  const refresh = () => client.invalidateQueries({ queryKey: ['/users'] });
  const create = useMutation({
    mutationFn: () => api<User>('/users', { method: 'POST', body: form }),
    onSuccess: () => { setForm({ full_name: '', email: '', password: '', role: 'viewer' }); setProblem(null); return refresh(); },
    onError: (e) => setProblem(apiMessage(e)),
  });
  const update = useMutation({
    mutationFn: ({ id, body }: { id: number; body: Partial<User> }) => api<User>(`/users/${id}`, { method: 'PATCH', body }),
    onSuccess: () => { setProblem(null); return refresh(); },
    onError: (e) => setProblem(apiMessage(e)),
  });
  const submit = (event: FormEvent) => {
    event.preventDefault();
    const issue = passwordProblem(form.password);
    if (issue) setProblem(issue);
    else create.mutate();
  };
  const set = (key: keyof typeof form) => (e: { target: { value: string } }) => setForm({ ...form, [key]: e.target.value });

  return (
    <Panel heading="Users" note="Roles take effect on the user's next request.">
      <Query q={users}>
        {(list) => (
          <Table label="Users">
            <thead><tr><th>Name</th><th>Role</th><th>Status</th><th>Created</th></tr></thead>
            <tbody>
              {list.map((u) => (
                <tr key={u.id}>
                  <td><span className="font-medium">{u.full_name}</span><div className="text-muted">{u.email}</div></td>
                  <td>
                    <select aria-label={`Role for ${u.email}`} value={u.role} disabled={u.id === me?.id || update.isPending} onChange={(e) => update.mutate({ id: u.id, body: { role: e.target.value as Role } })} className="min-h-9 rounded-md border border-line bg-panel px-2 text-sm disabled:opacity-60">
                      {ROLES.map((r) => <option key={r} value={r}>{title(r)}</option>)}
                    </select>
                  </td>
                  <td>
                    <Button disabled={u.id === me?.id || update.isPending} onClick={() => update.mutate({ id: u.id, body: { is_active: !u.is_active } })}>{u.is_active ? 'Deactivate' : 'Activate'}</Button>
                  </td>
                  <td className="whitespace-nowrap text-muted">{day(u.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </Table>
        )}
      </Query>
      <form onSubmit={submit} className="mt-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-[1fr_1fr_1fr_auto_auto] xl:items-end">
        <label className="text-sm font-medium">Full name<input required className={field} value={form.full_name} onChange={set('full_name')} /></label>
        <label className="text-sm font-medium">Email<input required type="email" className={field} value={form.email} onChange={set('email')} /></label>
        <label className="text-sm font-medium">Password<input required type="password" autoComplete="new-password" className={field} value={form.password} onChange={set('password')} /></label>
        <label className="text-sm font-medium">Role<select className={field} value={form.role} onChange={set('role')}>{ROLES.map((r) => <option key={r} value={r}>{title(r)}</option>)}</select></label>
        <Button type="submit" variant="primary" className="min-h-10" disabled={create.isPending}>Add user</Button>
      </form>
      {problem && <p role="alert" className="mt-3 text-crit">{problem}</p>}
    </Panel>
  );
}

function ResetSimulation() {
  const client = useQueryClient();
  const [confirming, setConfirming] = useState(false);
  const reset = useMutation({
    mutationFn: () => api<object>('/system/reset-simulation', { method: 'POST' }),
    onSuccess: () => { setConfirming(false); return client.invalidateQueries(); },
  });
  return (
    <Panel heading="Simulated environment" note="Regenerates all simulated metrics and billing, and clears alert history.">
      {confirming ? (
        <div className="flex flex-wrap items-center gap-3">
          <p className="font-medium">Delete the current simulated data and alert history?</p>
          <Button variant="danger" disabled={reset.isPending} onClick={() => reset.mutate()}>{reset.isPending ? 'Resetting' : 'Reset simulation'}</Button>
          <Button disabled={reset.isPending} onClick={() => setConfirming(false)}>Keep data</Button>
        </div>
      ) : <Button onClick={() => { reset.reset(); setConfirming(true); }}>Reset simulation</Button>}
      {reset.isSuccess && <p className="mt-3 text-ok" role="status">Simulation reset.</p>}
      {reset.isError && <div className="mt-3"><ErrorNote error={reset.error} /></div>}
    </Panel>
  );
}

export default function System() {
  const { can } = useAuth();
  const q = useApi<SystemInfo>('/system/info');
  return (
    <div className="space-y-5">
      <PageHeader heading="System" intro="Where the data comes from and how the platform is configured." source={q.data?.data_sources[0]} />
      <Query q={q}>
        {(s) => (
          <>
            <div className="grid gap-5 lg:grid-cols-2">
              <Panel heading="Platform">
                <dl className="num grid grid-cols-[1fr_auto] gap-y-2">
                  <dt className="text-muted">API version</dt><dd>{s.version}</dd>
                  <dt className="text-muted">Environment</dt><dd>{s.environment}</dd>
                  <dt className="text-muted">Latest metrics</dt><dd>{dateTime(s.last_metric_at)}</dd>
                  <dt className="text-muted">Latest billing day</dt><dd>{day(s.last_cost_date)}</dd>
                  <dt className="text-muted">Advisor</dt><dd>{s.advisor_mode === 'ai' ? `AI, ${s.advisor_model}` : 'Rule-based fallback'}</dd>
                </dl>
              </Panel>
              <Panel heading="Alert thresholds" note="Set through environment variables">
                <dl className="num grid grid-cols-[1fr_auto] gap-y-2">
                  <dt className="text-muted">CPU warning / critical</dt><dd>{s.thresholds.cpu_warning_pct}% / {s.thresholds.cpu_critical_pct}%</dd>
                  <dt className="text-muted">Memory warning / critical</dt><dd>{s.thresholds.memory_warning_pct}% / {s.thresholds.memory_critical_pct}%</dd>
                  <dt className="text-muted">Capacity threshold</dt><dd>{s.thresholds.capacity_threshold_pct}%</dd>
                </dl>
              </Panel>
            </div>
            <Panel heading="Data sources and integrations">
              <ul className="divide-y divide-line">
                {s.integrations.map((i) => (
                  <li key={i.provider} className="py-3 first:pt-0">
                    <div className="flex flex-wrap items-center justify-between gap-3"><p className="font-medium">{title(i.provider)}</p><Status status={i.status} /></div>
                    {i.description && <p className="text-sm text-muted">{i.description}</p>}
                    {i.apis && <p className="text-sm text-muted">Uses {i.apis.join(', ')}</p>}
                    {i.requires && <p className="text-sm text-muted">Needs {i.requires.join(', ')}</p>}
                  </li>
                ))}
              </ul>
            </Panel>
          </>
        )}
      </Query>
      {can('admin') && <><Users /><ResetSimulation /></>}
    </div>
  );
}
