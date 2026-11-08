import { useSyncExternalStore } from 'react';

export type Theme = 'light' | 'dark';
const KEY = 'cloudpulse.theme';

function stored(): Theme | null {
  try {
    const value = localStorage.getItem(KEY);
    return value === 'light' || value === 'dark' ? value : null;
  } catch {
    return null;
  }
}

function system(): Theme {
  return window.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

let current: Theme = 'light';
const listeners = new Set<() => void>();

function apply(theme: Theme) {
  current = theme;
  document.documentElement.dataset.theme = theme;
  listeners.forEach((listener) => listener());
}

export function initTheme() {
  apply(stored() ?? system());
}

export function toggleTheme() {
  const next: Theme = current === 'dark' ? 'light' : 'dark';
  try {
    localStorage.setItem(KEY, next);
  } catch {
    // The choice still applies for this page view.
  }
  apply(next);
}

export function useTheme(): Theme {
  return useSyncExternalStore(
    (listener) => {
      listeners.add(listener);
      return () => listeners.delete(listener);
    },
    () => current,
  );
}
