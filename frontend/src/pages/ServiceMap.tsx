import { Box, Boxes, Cloud, Cpu, Database, Globe, HardDrive, Layers, Network, Server, Shuffle, type LucideIcon } from 'lucide-react';
import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { PageHeader, Panel, Query, Status, statusMeta } from '../components/ui';
import { pct, title, usd } from '../lib/format';
import { useApi } from '../lib/hooks';
import type { TopoEdge, TopoNode, Topology } from '../lib/types';

const ICONS: Record<string, LucideIcon> = {
  vm: Server, database: Database, cache: Layers, node: Cpu, cluster: Boxes, storage: HardDrive, volume: HardDrive, load_balancer: Shuffle, gateway: Network, external: Globe,
};
const NODE_W = 192;
const NODE_H = 46;
const COLUMN = 244;
const ROW = 62;
const TOP = 40;

/** Follows edges both ways from a node so a selection shows its whole dependency chain. */
export function connected(id: string, edges: TopoEdge[]): Set<string> {
  const walk = (from: 'source' | 'target', to: 'source' | 'target') => {
    const seen = new Set([id]);
    const queue = [id];
    while (queue.length) {
      const current = queue.pop();
      for (const edge of edges) {
        if (edge[from] === current && !seen.has(edge[to])) {
          seen.add(edge[to]);
          queue.push(edge[to]);
        }
      }
    }
    return seen;
  };
  return new Set([...walk('source', 'target'), ...walk('target', 'source')]);
}

function layout(t: Topology) {
  const positions = new Map<string, { x: number; y: number }>();
  const heights = t.tiers.map((tier) => t.nodes.filter((n) => n.tier === tier).length * ROW);
  const tallest = Math.max(...heights);
  t.tiers.forEach((tier, column) => {
    const nodes = t.nodes.filter((n) => n.tier === tier);
    const offset = (tallest - nodes.length * ROW) / 2;
    nodes.forEach((node, row) => positions.set(node.id, { x: column * COLUMN + 4, y: TOP + offset + row * ROW }));
  });
  return { positions, width: t.tiers.length * COLUMN - (COLUMN - NODE_W) + 8, height: TOP + tallest };
}

const STROKE: Record<string, string> = { healthy: 'var(--ok-mark)', warning: 'var(--warn-mark)', critical: 'var(--crit-mark)', orphaned: 'var(--warn-mark)' };

function Graph({ t, selected, onSelect }: { t: Topology; selected: string | null; onSelect: (id: string | null) => void }) {
  const [hover, setHover] = useState<string | null>(null);
  const { positions, width, height } = useMemo(() => layout(t), [t]);
  const focus = hover ?? selected;
  const lit = useMemo(() => (focus ? connected(focus, t.edges) : null), [focus, t.edges]);

  return (
    <div className="-mx-4 overflow-x-auto px-4 sm:-mx-5 sm:px-5" tabIndex={0} role="region" aria-label="Service dependency map">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ minWidth: 960 }} role="group" aria-label={`${t.nodes.length} services, ${t.edges.length} dependencies`} onClick={(e) => { if (e.target === e.currentTarget) onSelect(null); }}>
        {t.tiers.map((tier, i) => <text key={tier} x={i * COLUMN + 4} y={18} fill="var(--muted)" fontSize={13}>{title(tier)}</text>)}
        <g fill="none">
          {t.edges.map((edge) => {
            const a = positions.get(edge.source);
            const b = positions.get(edge.target);
            if (!a || !b) return null;
            const sameColumn = a.x === b.x;
            const x1 = sameColumn ? a.x + NODE_W : a.x + (b.x > a.x ? NODE_W : 0);
            const x2 = sameColumn ? b.x + NODE_W : b.x + (b.x > a.x ? 0 : NODE_W);
            const y1 = a.y + NODE_H / 2;
            const y2 = b.y + NODE_H / 2;
            const bend = sameColumn ? 26 : (x2 - x1) / 2;
            const on = !lit || (lit.has(edge.source) && lit.has(edge.target));
            return (
              <path key={edge.id} d={`M${x1} ${y1} C${x1 + bend} ${y1} ${x2 - (sameColumn ? -26 : bend)} ${y2} ${x2} ${y2}`} stroke={lit && on ? 'var(--accent)' : 'var(--muted)'} strokeWidth={lit && on ? 2 : 1.25} opacity={lit && on ? 1 : on ? 0.45 : 0.15}>
                <title>{`${edge.source} to ${edge.target}: ${edge.label}`}</title>
              </path>
            );
          })}
        </g>
        {t.nodes.map((node) => {
          const p = positions.get(node.id)!;
          const Icon = ICONS[node.kind] ?? Box;
          const StatusIcon = statusMeta(node.status).Icon;
          const active = selected === node.id;
          return (
            <g
              key={node.id}
              data-node={node.id}
              transform={`translate(${p.x} ${p.y})`}
              tabIndex={0}
              role="button"
              aria-pressed={active}
              aria-label={`${node.label}, ${statusMeta(node.status).label}`}
              opacity={!lit || lit.has(node.id) ? 1 : 0.35}
              className="cursor-pointer"
              onClick={() => onSelect(active ? null : node.id)}
              onKeyDown={(e) => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); onSelect(active ? null : node.id); } }}
              onMouseEnter={() => setHover(node.id)}
              onMouseLeave={() => setHover(null)}
            >
              <rect width={NODE_W} height={NODE_H} rx={7} fill={active ? 'var(--accent-soft)' : 'var(--raised)'} stroke={active ? 'var(--accent)' : STROKE[node.status] ?? 'var(--line)'} strokeWidth={active ? 2 : 1.25} strokeDasharray={node.isolated ? '4 3' : undefined} />
              <Icon x={10} y={14} width={18} height={18} color="var(--muted)" aria-hidden />
              <text x={36} y={20} fill="var(--ink)" fontSize={13} fontWeight={600}>{node.label.length > 20 ? `${node.label.slice(0, 19)}…` : node.label}</text>
              <text x={36} y={36} fill="var(--muted)" fontSize={12}>{statusMeta(node.status).label}</text>
              <StatusIcon x={NODE_W - 26} y={15} width={16} height={16} color={STROKE[node.status] ?? 'var(--muted)'} aria-hidden />
            </g>
          );
        })}
      </svg>
    </div>
  );
}

function Details({ node, t }: { node: TopoNode; t: Topology }) {
  const incoming = t.edges.filter((e) => e.target === node.id);
  const outgoing = t.edges.filter((e) => e.source === node.id);
  const links = (edges: TopoEdge[], key: 'source' | 'target') => edges.length === 0 ? <p className="text-muted">None</p> : (
    <ul>{edges.map((e) => <li key={e.id}>{e[key]} <span className="text-muted">({e.label})</span></li>)}</ul>
  );
  const monitored = node.cpu_pct !== null && node.cpu_pct !== undefined;
  return (
    <div className="grid gap-x-8 gap-y-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
      <div>
        <p className="font-display text-lg font-semibold">{node.label}</p>
        <Status status={node.status} />
        <p className="text-muted">{title(node.kind)}{node.environment ? ` in ${node.environment}` : ''}</p>
        {monitored && <Link className="text-accent hover:underline" to={`/infrastructure/${encodeURIComponent(node.id)}`}>Open metrics</Link>}
      </div>
      <dl className="num grid grid-cols-2 content-start gap-x-3 gap-y-1">
        <dt className="text-muted">CPU</dt><dd>{pct(node.cpu_pct)}</dd>
        <dt className="text-muted">Memory</dt><dd>{pct(node.memory_pct)}</dd>
        <dt className="text-muted">30-day cost</dt><dd>{node.cost_30d_usd === null || node.cost_30d_usd === undefined ? 'n/a' : usd(node.cost_30d_usd, 2)}</dd>
      </dl>
      <div><p className="mb-1 font-medium">Called by</p>{links(incoming, 'source')}</div>
      <div><p className="mb-1 font-medium">Depends on</p>{links(outgoing, 'target')}</div>
    </div>
  );
}

export default function ServiceMap() {
  const q = useApi<Topology>('/topology', { refetchInterval: 60_000 });
  const [selected, setSelected] = useState<string | null>(null);
  return (
    <div className="space-y-5">
      <PageHeader heading="Service map" intro="Select a service to trace everything it depends on and everything that depends on it." source={q.data?.data_source} />
      <Query q={q}>
        {(t) => {
          const node = t.nodes.find((n) => n.id === selected);
          return (
            <>
              <Panel note={t.note}><Graph t={t} selected={selected} onSelect={setSelected} /></Panel>
              <Panel>
                {node ? <Details node={node} t={t} /> : <p className="flex items-center gap-2 text-muted"><Cloud size={18} aria-hidden />Select a service on the map to see its status, cost and dependencies.</p>}
              </Panel>
            </>
          );
        }}
      </Query>
    </div>
  );
}
