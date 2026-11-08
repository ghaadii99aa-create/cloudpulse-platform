import { useId, useState, type ReactNode } from 'react';
import { Area, Bar, BarChart, CartesianGrid, ComposedChart, Line, LineChart, ReferenceLine, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';
import { day, usd } from '../lib/format';

const AXIS = { stroke: 'var(--muted)', fontSize: 12, tickLine: false, axisLine: false } as const;
const GRID = <CartesianGrid stroke="var(--grid)" vertical={false} />;

// Colour belongs to the entity, so a filter never repaints the survivors.
const SERIES: Record<string, string> = {
  Compute: 'var(--s-1)', Database: 'var(--s-2)', Kubernetes: 'var(--s-3)', Storage: 'var(--s-4)', Network: 'var(--s-5)', Cache: 'var(--s-6)',
  prod: 'var(--s-1)', staging: 'var(--s-2)', dev: 'var(--s-3)', shared: 'var(--s-4)',
};
export const seriesColor = (name: string, index = 0) => SERIES[name] ?? `var(--s-${(index % 6) + 1})`;

interface TipRow { name?: string | number; value?: unknown; color?: string; dataKey?: unknown }
interface TipProps { active?: boolean; label?: string | number; payload?: readonly TipRow[] }

function tip(format: (value: number) => string, labelFormat: (label: string) => string, names?: Record<string, string>, total?: boolean) {
  return function ChartTip({ active, label, payload }: TipProps) {
    if (!active || !payload?.length) return null;
    const rows = payload.filter((row) => row.value !== null && row.value !== undefined && String(row.dataKey) !== 'total');
    const sum = rows.reduce((acc, row) => acc + (typeof row.value === 'number' ? row.value : 0), 0);
    return (
      <div className="rounded-md border border-line bg-panel px-3 py-2 text-sm shadow-lg">
        <p className="mb-1 font-medium">{labelFormat(String(label))}</p>
        {rows.map((row) => (
          <p key={String(row.dataKey)} className="flex items-center justify-between gap-4">
            <span className="flex items-center gap-1.5 text-muted"><span className="size-2 rounded-full" style={{ background: row.color }} />{names?.[String(row.dataKey)] ?? row.name}</span>
            <span className="num">{Array.isArray(row.value) ? `${format(row.value[0] as number)} to ${format(row.value[1] as number)}` : format(row.value as number)}</span>
          </p>
        ))}
        {total && <p className="mt-1 flex justify-between gap-4 border-t border-line pt-1 font-medium"><span>Total</span><span className="num">{format(sum)}</span></p>}
      </div>
    );
  };
}

export function Legend({ items }: { items: { label: string; color: string; dashed?: boolean; band?: boolean }[] }) {
  return (
    <ul className="mb-2 flex flex-wrap gap-x-4 gap-y-1 text-sm text-muted">
      {items.map((item) => (
        <li key={item.label} className="flex items-center gap-1.5">
          {item.band ? <span className="h-3 w-4 rounded-sm" style={{ background: item.color }} /> : item.dashed ? <span className="w-4 border-t-2 border-dashed" style={{ borderColor: item.color }} /> : <span className="size-2.5 rounded-full" style={{ background: item.color }} />}
          {item.label}
        </li>
      ))}
    </ul>
  );
}

export function DataView({ columns, rows, label }: { columns: string[]; rows: (string | number)[][]; label: string }) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <div className="mt-2">
      <button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)} className="cursor-pointer text-sm text-accent hover:underline">
        {open ? 'Hide data table' : 'Show data table'}
      </button>
      {open && (
        <div id={id} tabIndex={0} role="region" aria-label={label} className="mt-2 max-h-64 overflow-auto">
          <table className="num w-full text-sm wrap-normal">
            <thead><tr>{columns.map((c) => <th key={c} className="sticky top-0 bg-panel py-1 pr-3 text-left font-medium text-muted">{c}</th>)}</tr></thead>
            <tbody>{rows.map((row, i) => <tr key={i} className="border-t border-line">{row.map((cell, j) => <td key={j} className="py-1 pr-3">{cell}</td>)}</tr>)}</tbody>
          </table>
        </div>
      )}
    </div>
  );
}

interface BandPoint { date: string; forecast: number; lower: number; upper: number }

/** Actuals running into a forecast and its interval: the page's main reading. */
export function ForecastRibbon({ history, forecast, height = 300, format = (v: number) => usd(v), actualLabel = 'Actual daily spend', domainMax }: {
  history: { date: string; value: number }[]; forecast: BandPoint[]; height?: number; format?: (v: number) => string; actualLabel?: string; domainMax?: number;
}) {
  const last = history[history.length - 1];
  const data = [
    ...history.map((p) => ({ date: p.date, actual: p.value })),
    ...forecast.map((p) => ({ date: p.date, forecast: p.forecast, band: [p.lower, p.upper] as [number, number] })),
  ].map((p) => (p.date === last?.date ? { ...p, forecast: last.value, band: [last.value, last.value] as [number, number] } : p));
  const Tip = tip(format, day, { actual: actualLabel, forecast: 'Forecast', band: '90% interval' });
  return (
    <>
      <Legend items={[{ label: actualLabel, color: 'var(--ink)' }, { label: 'Forecast', color: 'var(--accent)', dashed: true }, { label: '90% prediction interval', color: 'var(--band)', band: true }]} />
      <div style={{ height }}>
        <ResponsiveContainer>
          <ComposedChart data={data} margin={{ top: 16, right: 8, left: 0, bottom: 0 }}>
            {GRID}
            <XAxis dataKey="date" tickFormatter={day} minTickGap={48} {...AXIS} />
            <YAxis tickFormatter={format} width={58} domain={domainMax ? [0, domainMax] : ['auto', 'auto']} {...AXIS} />
            <Tooltip content={<Tip />} />
            <Area dataKey="band" stroke="none" fill="var(--band)" fillOpacity={1} isAnimationActive={false} activeDot={false} />
            {last && <ReferenceLine x={last.date} stroke="var(--muted)" strokeDasharray="2 3" label={{ value: 'Last actual', position: 'top', fill: 'var(--muted)', fontSize: 12 }} />}
            <Line dataKey="actual" stroke="var(--ink)" strokeWidth={2} dot={false} isAnimationActive={false} />
            <Line dataKey="forecast" stroke="var(--accent)" strokeWidth={2} strokeDasharray="5 4" dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

export function StackedDaily({ points, series, height = 300 }: { points: Record<string, string | number>[]; series: string[]; height?: number }) {
  const Tip = tip((v) => usd(v, 2), day, undefined, true);
  return (
    <>
      <Legend items={series.map((name, i) => ({ label: name, color: seriesColor(name, i) }))} />
      <div style={{ height }}>
        <ResponsiveContainer>
          <BarChart data={points} margin={{ top: 8, right: 8, left: 0, bottom: 0 }} barCategoryGap="12%">
            {GRID}
            <XAxis dataKey="date" tickFormatter={day} minTickGap={48} {...AXIS} />
            <YAxis tickFormatter={(v) => usd(v)} width={58} {...AXIS} />
            <Tooltip content={<Tip />} cursor={{ fill: 'var(--raised)' }} />
            {series.map((name, i) => <Bar key={name} dataKey={name} stackId="cost" fill={seriesColor(name, i)} isAnimationActive={false} />)}
          </BarChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

export interface LineSeries { key: string; label: string; color: string }

export function Lines({ data, x, series, height = 240, format = (v: number) => `${v.toFixed(0)}%`, xFormat = day, domain, width = 44, refs }: {
  data: object[]; x: string; series: LineSeries[]; height?: number; format?: (v: number) => string; xFormat?: (v: string) => string;
  domain?: [number, number]; width?: number; refs?: { y: number; label: string }[];
}) {
  const Tip = tip(format, xFormat);
  return (
    <>
      {series.length > 1 && <Legend items={series} />}
      <div style={{ height }}>
        <ResponsiveContainer>
          <LineChart data={data} margin={{ top: 12, right: 8, left: 0, bottom: 0 }}>
            {GRID}
            <XAxis dataKey={x} tickFormatter={xFormat} minTickGap={48} {...AXIS} />
            <YAxis tickFormatter={format} width={width} domain={domain ?? ['auto', 'auto']} {...AXIS} />
            <Tooltip content={<Tip />} />
            {refs?.map((r) => <ReferenceLine key={r.label} y={r.y} stroke="var(--warn-mark)" strokeDasharray="4 3" label={{ value: r.label, position: 'insideTopRight', fill: 'var(--muted)', fontSize: 12 }} />)}
            {series.map((s) => <Line key={s.key} dataKey={s.key} name={s.label} stroke={s.color} strokeWidth={2} dot={false} isAnimationActive={false} />)}
          </LineChart>
        </ResponsiveContainer>
      </div>
    </>
  );
}

/** Ranked horizontal bars in HTML: labels stay legible at any width. */
export function RankedBars({ items }: { items: { name: string; value: number; display: ReactNode; href?: ReactNode }[] }) {
  const max = Math.max(...items.map((i) => i.value), 1);
  return (
    <ul className="space-y-2.5">
      {items.map((item) => (
        <li key={item.name} title={item.name}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="min-w-0 truncate">{item.href ?? item.name}</span>
            <span className="num shrink-0 text-muted">{item.display}</span>
          </div>
          <div className="mt-1 h-1.5 rounded-full bg-raised"><div className="h-full rounded-full bg-accent" style={{ width: `${(item.value / max) * 100}%` }} /></div>
        </li>
      ))}
    </ul>
  );
}
