import { render, screen } from '@testing-library/react';
import { connected } from '../pages/ServiceMap';
import { headline } from '../pages/Overview';
import { passwordProblem } from '../pages/System';
import type { Executive, TopoEdge } from '../lib/types';
import { Markdown } from './Markdown';
import { DataBadge, Meter, Status } from './ui';

describe('DataBadge', () => {
  it('labels simulated data', () => {
    render(<DataBadge source="SIMULATED" />);
    expect(screen.getByText('Simulated data')).toBeInTheDocument();
  });
  it('labels real data differently', () => {
    render(<DataBadge source="AWS" />);
    expect(screen.getByText('AWS data')).toBeInTheDocument();
  });
});

describe('Status', () => {
  it('always carries a text label', () => {
    render(<Status status="no_telemetry" />);
    expect(screen.getByText('No telemetry')).toBeInTheDocument();
  });
  it('handles unknown statuses', () => {
    render(<Status status="pending_review" />);
    expect(screen.getByText('Pending review')).toBeInTheDocument();
  });
});

describe('Meter', () => {
  it('shows n/a for a resource without telemetry', () => {
    render(<Meter label="CPU" value={null} warn={85} crit={95} />);
    expect(screen.getByText('n/a')).toBeInTheDocument();
  });
  it('clamps the bar but reports the value', () => {
    const { container } = render(<Meter label="CPU" value={120} warn={85} crit={95} />);
    expect(screen.getByRole('img', { name: 'CPU 120.0%' })).toBeInTheDocument();
    expect(container.querySelector('[style]')).toHaveStyle({ width: '100%' });
  });
});

describe('Markdown', () => {
  it('renders bold and lists', () => {
    render(<Markdown text={'**Top**\n- **a**: one\n- two'} />);
    expect(screen.getByText('Top').tagName).toBe('STRONG');
    expect(screen.getAllByRole('listitem')).toHaveLength(2);
  });
  it('never injects HTML from an answer', () => {
    const { container } = render(<Markdown text={'<img src=x onerror=alert(1)>'} />);
    expect(container.querySelector('img')).toBeNull();
  });
});

describe('connected', () => {
  const edges = [['a', 'b'], ['b', 'c'], ['x', 'b'], ['d', 'e']].map(([source, target]) => ({ id: source + target, source, target, label: '' })) as TopoEdge[];
  it('follows upstream and downstream', () => {
    expect([...connected('b', edges)].sort()).toEqual(['a', 'b', 'c', 'x']);
  });
  it('does not cross through siblings', () => {
    expect([...connected('a', edges)].sort()).toEqual(['a', 'b', 'c']);
  });
});

describe('headline', () => {
  const base = (status_counts: object) => ({ health: { monitored_count: 14, status_counts }, costs: { month: '2026-11', month_end_estimate_usd: 5779.7 } }) as unknown as Executive;
  it('leads with critical resources', () => {
    expect(headline(base({ healthy: 10, warning: 3, critical: 1 }))).toBe('1 of 14 monitored resources is critical. November is on track to cost $5,780.');
  });
  it('reports warnings', () => {
    expect(headline(base({ healthy: 11, warning: 3, critical: 0 }))).toContain('11 of 14 monitored resources are healthy and 3 need attention');
  });
  it('reports an all-clear', () => {
    expect(headline(base({ healthy: 14, warning: 0, critical: 0 }))).toContain('All 14 monitored resources are healthy');
  });
});

describe('passwordProblem', () => {
  it('mirrors the API rules', () => {
    expect(passwordProblem('short1')).toMatch(/12/);
    expect(passwordProblem('onlyletterslong')).toMatch(/digits/);
    expect(passwordProblem('letters-and-123')).toBeNull();
  });
});
