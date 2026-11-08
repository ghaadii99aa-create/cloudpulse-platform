import { Activity, Bell, Bot, Boxes, CircleDollarSign, FileText, LayoutDashboard, LogOut, Menu, Moon, Network, Server, Settings2, Sun, TrendingUp, X } from 'lucide-react';
import { useState } from 'react';
import { NavLink, Outlet } from 'react-router-dom';
import { useAuth } from '../lib/auth';
import { title } from '../lib/format';
import { useApi } from '../lib/hooks';
import { toggleTheme, useTheme } from '../lib/theme';
import type { AlertSummary } from '../lib/types';

const NAV = [
  { group: 'Operate', links: [
    { to: '/', label: 'Overview', Icon: LayoutDashboard },
    { to: '/infrastructure', label: 'Infrastructure', Icon: Server },
    { to: '/kubernetes', label: 'Kubernetes', Icon: Boxes },
    { to: '/map', label: 'Service map', Icon: Network },
    { to: '/alerts', label: 'Alerts', Icon: Bell },
  ] },
  { group: 'Optimize', links: [
    { to: '/costs', label: 'Costs', Icon: CircleDollarSign },
    { to: '/forecasts', label: 'Forecasts', Icon: TrendingUp },
    { to: '/advisor', label: 'Cloud Advisor', Icon: Bot },
    { to: '/reports', label: 'Reports', Icon: FileText },
  ] },
  { group: 'Manage', links: [{ to: '/system', label: 'System', Icon: Settings2 }] },
];

function Brand() {
  return (
    <span className="flex items-center gap-2 font-display text-xl font-semibold tracking-tight">
      <Activity size={20} className="text-accent" aria-hidden /> CloudPulse
    </span>
  );
}

function ThemeButton() {
  const theme = useTheme();
  const next = theme === 'dark' ? 'light' : 'dark';
  return (
    <button type="button" onClick={toggleTheme} aria-label={`Switch to ${next} theme`} title={`Switch to ${next} theme`} className="grid size-9 cursor-pointer place-items-center rounded-md text-muted hover:bg-raised hover:text-ink">
      {theme === 'dark' ? <Sun size={18} aria-hidden /> : <Moon size={18} aria-hidden />}
    </button>
  );
}

function Navigation({ onNavigate }: { onNavigate?: () => void }) {
  const alerts = useApi<AlertSummary>('/alerts/summary', { refetchInterval: 60_000 }).data;
  return (
    <nav aria-label="Main" className="space-y-5">
      {NAV.map(({ group, links }) => (
        <div key={group}>
          <p className="mb-1 px-3 text-sm text-muted">{group}</p>
          <ul className="space-y-0.5">
            {links.map(({ to, label, Icon }) => (
              <li key={to}>
                <NavLink to={to} end={to === '/'} onClick={onNavigate} className={({ isActive }) => `flex min-h-10 items-center gap-3 rounded-md px-3 font-medium ${isActive ? 'bg-accent-soft text-ink' : 'text-muted hover:bg-raised hover:text-ink'}`}>
                  <Icon size={18} aria-hidden />
                  <span className="flex-1">{label}</span>
                  {to === '/alerts' && !!alerts?.active_total && <span className="num rounded-full bg-raised px-2 text-xs text-ink" aria-label={`${alerts.active_total} active`}>{alerts.active_total}</span>}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Account() {
  const { user, signOut } = useAuth();
  if (!user) return null;
  return (
    <div className="flex items-center gap-2 border-t border-line pt-3">
      <div className="min-w-0 flex-1 px-1">
        <p className="truncate text-sm font-medium">{user.full_name}</p>
        <p className="text-sm text-muted">{title(user.role)}</p>
      </div>
      <ThemeButton />
      <button type="button" onClick={signOut} aria-label="Sign out" title="Sign out" className="grid size-9 cursor-pointer place-items-center rounded-md text-muted hover:bg-raised hover:text-ink">
        <LogOut size={18} aria-hidden />
      </button>
    </div>
  );
}

export function Shell() {
  const [open, setOpen] = useState(false);
  return (
    <div className="min-h-dvh lg:pl-60">
      <aside className="fixed inset-y-0 left-0 hidden w-60 flex-col justify-between overflow-y-auto bg-panel p-3 lg:flex">
        <div>
          <div className="mb-6 px-3 pt-2"><Brand /></div>
          <Navigation />
        </div>
        <Account />
      </aside>

      <div className="sticky top-0 z-20 flex h-14 items-center justify-between bg-panel px-4 lg:hidden">
        <Brand />
        <button type="button" onClick={() => setOpen(true)} aria-label="Open menu" aria-expanded={open} className="grid size-10 cursor-pointer place-items-center rounded-md hover:bg-raised">
          <Menu size={22} aria-hidden />
        </button>
      </div>

      {open && (
        <div className="fixed inset-0 z-30 lg:hidden" role="dialog" aria-modal="true" aria-label="Menu">
          <button type="button" aria-label="Close menu" className="absolute inset-0 bg-black/40" onClick={() => setOpen(false)} />
          <div className="absolute inset-y-0 right-0 flex w-72 max-w-[85vw] flex-col justify-between overflow-y-auto bg-panel p-3">
            <div>
              <div className="mb-4 flex items-center justify-between px-3">
                <Brand />
                <button type="button" onClick={() => setOpen(false)} aria-label="Close menu" className="grid size-10 cursor-pointer place-items-center rounded-md hover:bg-raised"><X size={22} aria-hidden /></button>
              </div>
              <Navigation onNavigate={() => setOpen(false)} />
            </div>
            <Account />
          </div>
        </div>
      )}

      <main className="mx-auto max-w-[1320px] px-4 py-6 sm:px-6 lg:px-8 lg:py-8">
        <Outlet />
      </main>
    </div>
  );
}
