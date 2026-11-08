import { useState } from 'react';
import { Empty, Figures, Meter, PageHeader, Panel, Query, Select, Status, Table } from '../components/ui';
import { pct } from '../lib/format';
import { useApi, useThresholds } from '../lib/hooks';
import type { K8s } from '../lib/types';

export default function Kubernetes() {
  const q = useApi<K8s>('/kubernetes/cluster', { refetchInterval: 60_000 });
  const limits = useThresholds();
  const [namespace, setNamespace] = useState('all');
  const namespaceOptions = [{ value: 'all', label: 'All' }, ...(q.data?.summary.namespaces.map((n) => ({ value: n, label: n })) ?? [])];
  const matches = (item: { namespace: string }) => namespace === 'all' || item.namespace === namespace;

  return (
    <div className="space-y-5">
      <PageHeader heading="Kubernetes" intro={q.data ? `Cluster ${q.data.cluster.name}, ${q.data.mode} mode.` : undefined} source={q.data?.data_source}>
        {q.data && <Status status={q.data.cluster.health} />}
      </PageHeader>
      <Query q={q}>
        {(k) => {
          const deployments = k.deployments.filter(matches);
          const pods = k.pods.filter(matches);
          return (
            <>
              {k.notice && <p role="status" className="rounded-lg bg-panel p-4 text-warn">{k.notice}</p>}
              <Panel>
                <Figures items={[
                  { label: 'Nodes ready', value: `${k.summary.nodes_ready}/${k.summary.nodes_total}` },
                  { label: 'Pods running', value: `${k.summary.pods_running}/${k.summary.pods_total}`, detail: `${k.summary.pods_pending} pending` },
                  { label: 'Deployments healthy', value: `${k.summary.deployments_healthy}/${k.summary.deployments_total}` },
                  { label: 'Average CPU', value: pct(k.summary.avg_cpu_pct) },
                  { label: 'Average memory', value: pct(k.summary.avg_memory_pct) },
                ]} />
              </Panel>
              <Panel heading="Nodes">
                <Table label="Nodes">
                  <thead><tr><th>Node</th><th>Status</th><th className="min-w-36">CPU</th><th className="min-w-36">Memory</th><th className="text-right!">Pods</th><th>Capacity</th></tr></thead>
                  <tbody>
                    {k.nodes.map((n) => (
                      <tr key={n.name}>
                        <td className="whitespace-nowrap font-medium">{n.name}<div className="font-normal text-muted">{n.kubelet_version}</div></td>
                        <td><Status status={n.status} /></td>
                        <td><Meter label="CPU" value={n.cpu_pct} warn={limits.cpu_warning_pct} crit={limits.cpu_critical_pct} /></td>
                        <td><Meter label="Memory" value={n.memory_pct} warn={limits.memory_warning_pct} crit={limits.memory_critical_pct} /></td>
                        <td className="num text-right">{n.pod_count}</td>
                        <td className="num whitespace-nowrap text-muted">{(n.cpu_capacity_m / 1000).toFixed(0)} vCPU, {(n.memory_capacity_mib / 1024).toFixed(0)} GiB</td>
                      </tr>
                    ))}
                  </tbody>
                </Table>
              </Panel>
              <div className="grid gap-5 xl:grid-cols-5">
                <Panel className="xl:col-span-2" heading="Deployments" action={<Select label="Namespace" value={namespace} onChange={setNamespace} options={namespaceOptions} />}>
                  {deployments.length === 0 ? <Empty>No deployments in this namespace.</Empty> : (
                    <Table label="Deployments">
                      <thead><tr><th>Deployment</th><th className="text-right!">Ready</th><th>Status</th></tr></thead>
                      <tbody>
                        {deployments.map((d) => (
                          <tr key={d.namespace + d.name}>
                            <td><span className="font-medium">{d.name}</span><div className="text-muted">{d.namespace}</div></td>
                            <td className="num text-right">{d.ready}/{d.desired}</td>
                            <td><Status status={d.status} /></td>
                          </tr>
                        ))}
                      </tbody>
                    </Table>
                  )}
                </Panel>
                <Panel className="xl:col-span-3" heading="Pods" note={`${pods.length} shown`}>
                  {pods.length === 0 ? <Empty>No pods in this namespace.</Empty> : (
                    <div className="max-h-[560px] overflow-y-auto">
                      <Table label="Pods">
                        <thead><tr><th>Pod</th><th>Node</th><th>Phase</th><th className="text-right!">CPU</th><th className="text-right!">Memory</th><th className="text-right!">Restarts</th></tr></thead>
                        <tbody>
                          {pods.map((p) => (
                            <tr key={p.name}>
                              <td className="font-medium">{p.name}<div className="font-normal text-muted">{p.namespace}</div></td>
                              <td className="whitespace-nowrap">{p.node}</td>
                              <td>{p.phase}</td>
                              <td className="num whitespace-nowrap text-right">{p.cpu_usage_m}m</td>
                              <td className="num whitespace-nowrap text-right">{p.memory_usage_mib} MiB</td>
                              <td className="num text-right">{p.restarts}</td>
                            </tr>
                          ))}
                        </tbody>
                      </Table>
                    </div>
                  )}
                </Panel>
              </div>
            </>
          );
        }}
      </Query>
    </div>
  );
}
