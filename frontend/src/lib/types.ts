export type Role = 'viewer' | 'engineer' | 'admin';
export type DataSource = 'SIMULATED' | 'SIMULATED_LIVE' | 'AWS' | 'AZURE' | 'LIVE_KUBERNETES';

export interface User { id: number; email: string; full_name: string; role: Role; is_active: boolean; created_at: string }
export interface LoginResponse { access_token: string; token_type: string; expires_in: number; user: User }

export interface FleetSummary {
  as_of: string; data_source: DataSource; resource_count: number; monitored_count: number;
  status_counts: { healthy: number; warning: number; critical: number; no_telemetry: number };
  health_score: number; health_score_method: string; avg_cpu_pct: number; avg_memory_pct: number; avg_disk_pct: number;
  total_network_mbps: number; availability_24h_pct: number;
}
export interface ServiceCost { service: string; cost_usd: number; share_pct: number }
export interface CostSummary {
  as_of: string; data_source: DataSource; currency: string; last_30d_usd: number; previous_30d_usd: number; change_pct: number;
  daily_average_usd: number; month: string; month_to_date_usd: number; month_end_estimate_usd: number;
  next_30d_forecast: { horizon_days: number; projected_usd: number; low_usd: number; high_usd: number; previous_period_usd: number };
  potential_monthly_savings_usd: number; top_service: ServiceCost; cost_spike_count_30d: number;
}
export interface TrendPoint { date: string; cpu_pct: number; memory_pct: number; disk_pct: number; network_mbps: number; availability_pct: number }
export interface ForecastPoint { date: string; forecast: number; lower: number; upper: number }
export interface Backtest { holdout_days: number; mape_pct: number; interval_coverage_pct: number }
export interface CostForecast {
  data_source?: DataSource; horizon_days?: number; model: string; interval?: string; backtest: Backtest;
  history: { date: string; cost_usd: number }[]; forecast: ForecastPoint[]; total: { forecast: number; lower: number; upper: number };
}
export interface Recommendation {
  resource: string; category: string; action: string; reason: string; monthly_cost_usd: number; estimated_monthly_savings_usd: number;
}
export interface CapacityRisk { resource: string; metric: string; current_pct: number; daily_change_pct: number; days_to_threshold: number }
export type AlertStatus = 'open' | 'acknowledged' | 'resolved';
export interface Alert {
  id: number; fingerprint: string; category: string; severity: 'critical' | 'warning' | 'info'; status: AlertStatus; resource: string | null;
  title: string; message: string; value: number | null; threshold: number | null; observed_at: string; first_seen: string; last_seen: string;
  acknowledged_by: string | null; acknowledged_at: string | null; resolved_at: string | null; data_source: DataSource;
}
export interface AlertPage { total: number; items: Alert[] }
export interface AlertSummary { active_total: number; by_severity: Record<string, number>; by_category: Record<string, number>; resolved_total: number }
export interface Executive {
  data_source: DataSource; health: FleetSummary; costs: CostSummary; utilization_trend: TrendPoint[]; cost_forecast: CostForecast;
  cost_by_service: ServiceCost[]; top_recommendations: Recommendation[]; capacity_risks: CapacityRisk[];
  active_alerts: { total: number; critical: number; warning: number; items: Alert[] };
}
export interface Resource {
  name: string; service: string; kind: string; environment: string; provider: string; region: string; attached: boolean; cost_30d_usd: number;
  data_source: DataSource; status: string; reasons: string[]; cpu_pct: number | null; memory_pct: number | null; disk_pct: number | null;
  network_mbps: number | null; available: boolean | null; availability_24h_pct: number | null;
}
export interface Resources { as_of: string; data_source: DataSource; items: Resource[] }
export interface LiveReading { resource: string; cpu_pct: number; memory_pct: number; disk_pct: number; network_mbps: number }
export interface Live { timestamp: string; data_source: DataSource; method: string; readings: LiveReading[] }
export interface MetricPoint { timestamp: string; cpu_pct: number; memory_pct: number; disk_pct: number; network_mbps: number; available: number }
export interface Metrics { resource: string; resolution: string; hours: number; data_source: DataSource; points: MetricPoint[] }
export interface Breakdown { by: string; days: number; data_source: DataSource; total_usd: number; items: (Record<string, string | number> & { cost_usd: number; share_pct: number })[] }
export interface Daily { by: string; series: string[]; data_source: DataSource; points: (Record<string, string | number> & { date: string; total: number })[] }
export interface CostAnomaly { date: string; resource: string; service: string; cost_usd: number; expected_usd: number; excess_usd: number; score: number }
export interface CostAnomalies { data_source: DataSource; method: string; items: CostAnomaly[] }
export interface Recommendations { data_source: DataSource; total_monthly_savings_usd: number; items: Recommendation[] }
export interface UtilForecast { resource: string; metric: string; horizon_days: number; data_source: DataSource; history: { date: string; value: number }[]; forecast: ForecastPoint[] }
export interface UsageAnomalies { data_source: DataSource; method: string; items: { timestamp: string; resource: string; cpu_pct: number; memory_pct: number; network_mbps: number }[] }
export interface Capacity { data_source: DataSource; threshold_pct: number; within_days: number; method: string; items: CapacityRisk[] }
export interface K8sNode { name: string; ready: boolean; status: string; conditions: string[]; cpu_pct: number; memory_pct: number; cpu_capacity_m: number; memory_capacity_mib: number; pod_count: number; kubelet_version: string }
export interface K8sDeployment { name: string; namespace: string; desired: number; ready: number; available: number; status: string }
export interface K8sPod { name: string; namespace: string; deployment: string; node: string; phase: string; ready: boolean; restarts: number; cpu_request_m: number; memory_request_mib: number; cpu_usage_m: number; memory_usage_mib: number }
export interface K8s {
  mode: string; data_source: DataSource; notice?: string; cluster: { name: string; health: string };
  summary: { nodes_total: number; nodes_ready: number; pods_total: number; pods_running: number; pods_pending: number; deployments_total: number; deployments_healthy: number; avg_cpu_pct: number; avg_memory_pct: number; namespaces: string[] };
  nodes: K8sNode[]; deployments: K8sDeployment[]; pods: K8sPod[];
}
export interface TopoNode { id: string; label: string; kind: string; service?: string; environment?: string; tier: string; status: string; cpu_pct?: number | null; memory_pct?: number | null; cost_30d_usd?: number | null; data_source?: DataSource; isolated?: boolean }
export interface TopoEdge { id: string; source: string; target: string; label: string }
export interface Topology { tiers: string[]; nodes: TopoNode[]; edges: TopoEdge[]; data_source: DataSource; note: string }
export interface Advice {
  question: string | null; topics: string[]; data_source: DataSource; generated_at: string; estimated_monthly_savings_usd: number;
  recommendations: Recommendation[]; mode: 'ai' | 'fallback'; model: string | null; answer: string; notice?: string;
}
export interface Integration { provider: string; status: string; data_source: DataSource; description?: string; apis?: string[]; requires?: string[] }
export interface SystemInfo {
  version: string; environment: string; data_sources: DataSource[]; simulated: boolean; last_metric_at: string; last_cost_date: string; advisor_mode: 'ai' | 'fallback'; advisor_model: string | null;
  integrations: Integration[]; thresholds: { cpu_warning_pct: number; cpu_critical_pct: number; memory_warning_pct: number; memory_critical_pct: number; capacity_threshold_pct: number };
}
