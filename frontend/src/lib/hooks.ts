import { useQuery } from '@tanstack/react-query';
import { api } from './api';
import type { SystemInfo } from './types';

export function useApi<T>(path: string, options?: { refetchInterval?: number; enabled?: boolean }) {
  return useQuery<T>({
    queryKey: [path],
    queryFn: ({ signal }) => api<T>(path, { signal }),
    refetchInterval: options?.refetchInterval,
    enabled: options?.enabled,
  });
}

const DEFAULTS = { cpu_warning_pct: 85, cpu_critical_pct: 95, memory_warning_pct: 85, memory_critical_pct: 95, capacity_threshold_pct: 85 };

export function useThresholds() {
  return useApi<SystemInfo>('/system/info').data?.thresholds ?? DEFAULTS;
}
