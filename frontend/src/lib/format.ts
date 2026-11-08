const TZ = 'UTC';

export function usd(value: number, digits = 0): string {
  return value.toLocaleString('en-US', { style: 'currency', currency: 'USD', minimumFractionDigits: digits, maximumFractionDigits: digits });
}

export function pct(value: number | null | undefined, digits = 1): string {
  return value === null || value === undefined ? 'n/a' : `${value.toFixed(digits)}%`;
}

export function signedPct(value: number, digits = 1): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(digits)}%`;
}

/** The API sends naive ISO strings in UTC; plain dates are calendar days. */
export function toDate(value: string): Date {
  if (/^\d{4}-\d{2}-\d{2}$/.test(value)) return new Date(`${value}T00:00:00Z`);
  return new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : `${value}Z`);
}

export function day(value: string): string {
  return toDate(value).toLocaleDateString('en-US', { month: 'short', day: 'numeric', timeZone: TZ });
}

export function dateTime(value: string): string {
  return `${toDate(value).toLocaleString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: TZ })} UTC`;
}

export function clock(value: string): string {
  return `${toDate(value).toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false, timeZone: TZ })} UTC`;
}

export function monthName(value: string): string {
  return toDate(`${value}-01`).toLocaleDateString('en-US', { month: 'long', timeZone: TZ });
}

const ACRONYMS: Record<string, string> = { cpu: 'CPU', aws: 'AWS', vm: 'VM' };

export function title(value: string): string {
  if (ACRONYMS[value]) return ACRONYMS[value];
  const text = value.replace(/_/g, ' ');
  return text.charAt(0).toUpperCase() + text.slice(1);
}

export const METRIC_LABEL: Record<string, string> = { cpu_pct: 'CPU', memory_pct: 'Memory', disk_pct: 'Disk' };
