import { Download } from 'lucide-react';
import { useState } from 'react';
import { Button, ErrorNote, PageHeader, Panel, Query } from '../components/ui';
import { fetchBlob } from '../lib/api';
import { dateTime, usd } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { Executive } from '../lib/types';

const CONTENTS = ['Key figures for health, spend and savings', 'Cost by service and daily spend charts', 'Unusual spending', 'Spend forecast with its interval', 'Performance by resource', 'Savings recommendations', 'Active alerts'];

export default function Reports() {
  const q = useApi<Executive>('/dashboard/executive');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [done, setDone] = useState<string | null>(null);

  async function download() {
    setBusy(true);
    setError(null);
    setDone(null);
    try {
      const blob = await fetchBlob('/reports/executive.pdf');
      const name = `cloudpulse-executive-report-${new Date().toISOString().slice(0, 10)}.pdf`;
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = name;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 30_000);
      setDone(`Downloaded ${name} (${Math.round(blob.size / 1024)} KB).`);
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader heading="Reports" intro="A PDF for people who will not open the dashboard." source={q.data?.data_source} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Panel heading="Executive report">
          <ul className="list-disc space-y-1 pl-5 text-muted">{CONTENTS.map((item) => <li key={item}>{item}</li>)}</ul>
          <Button variant="primary" className="mt-4" disabled={busy} onClick={download}><Download size={16} aria-hidden />{busy ? 'Generating PDF' : 'Download PDF'}</Button>
          <div aria-live="polite">{done && <p className="mt-3 text-ok">{done}</p>}</div>
          {error !== null && <div className="mt-3"><ErrorNote error={error} /></div>}
        </Panel>
        <Panel heading="What the report will show">
          <Query q={q}>
            {(d) => (
              <dl className="num grid grid-cols-[1fr_auto] gap-y-2">
                <dt className="text-muted">Metrics as of</dt><dd>{dateTime(d.health.as_of)}</dd>
                <dt className="text-muted">Health score</dt><dd>{d.health.health_score.toFixed(1)}</dd>
                <dt className="text-muted">Spend, last 30 days</dt><dd>{usd(d.costs.last_30d_usd, 2)}</dd>
                <dt className="text-muted">Month-end estimate</dt><dd>{usd(d.costs.month_end_estimate_usd, 2)}</dd>
                <dt className="text-muted">Savings found</dt><dd>{usd(d.costs.potential_monthly_savings_usd, 2)}/mo</dd>
                <dt className="text-muted">Active alerts</dt><dd>{d.active_alerts.total}</dd>
              </dl>
            )}
          </Query>
        </Panel>
      </div>
    </div>
  );
}
