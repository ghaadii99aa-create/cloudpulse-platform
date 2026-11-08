import { dateTime, day, monthName, pct, signedPct, title, toDate, usd } from './format';

describe('format', () => {
  it('formats money', () => {
    expect(usd(5743.26)).toBe('$5,743');
    expect(usd(5743.26, 2)).toBe('$5,743.26');
  });
  it('shows missing percentages as n/a, not zero', () => {
    expect(pct(null)).toBe('n/a');
    expect(pct(undefined)).toBe('n/a');
    expect(pct(0)).toBe('0.0%');
  });
  it('signs positive changes only', () => {
    expect(signedPct(3.87)).toBe('+3.9%');
    expect(signedPct(-1.2)).toBe('-1.2%');
  });
  it('reads naive API timestamps as UTC', () => {
    expect(toDate('2026-11-08T14:00:00').toISOString()).toBe('2026-11-08T14:00:00.000Z');
    expect(toDate('2026-11-08T14:00:00+00:00').toISOString()).toBe('2026-11-08T14:00:00.000Z');
    expect(dateTime('2026-11-08T14:00:00')).toBe('Nov 8, 14:00 UTC');
  });
  it('keeps calendar days on their day', () => {
    expect(day('2026-10-01')).toBe('Oct 1');
    expect(monthName('2026-11')).toBe('November');
  });
  it('humanizes identifiers', () => {
    expect(title('no_telemetry')).toBe('No telemetry');
    expect(title('cpu')).toBe('CPU');
  });
});
