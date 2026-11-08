import type { LoginResponse } from './types';

const BASE = ((import.meta.env.VITE_API_URL as string | undefined) ?? '').replace(/\/$/, '');
const PREFIX = `${BASE}/api/v1`;
const TOKEN_KEY = 'cloudpulse.token';

export class ApiError extends Error {
  status: number;
  code: string;
  details?: { field: string; message: string }[];

  constructor(status: number, code: string, message: string, details?: { field: string; message: string }[]) {
    super(message);
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

function storage(): Storage | null {
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

let memoryToken: string | null = storage()?.getItem(TOKEN_KEY) ?? null;
let onExpired: (() => void) | null = null;

export const getToken = () => memoryToken;
export function setToken(token: string | null) {
  memoryToken = token;
  if (token) storage()?.setItem(TOKEN_KEY, token);
  else storage()?.removeItem(TOKEN_KEY);
}
export function setExpiredHandler(handler: (() => void) | null) {
  onExpired = handler;
}

async function send(path: string, init: RequestInit = {}): Promise<Response> {
  const sentToken = memoryToken;
  const headers = new Headers(init.headers);
  if (sentToken) headers.set('Authorization', `Bearer ${sentToken}`);
  if (init.body) headers.set('Content-Type', 'application/json');
  let response: Response;
  try {
    response = await fetch(`${PREFIX}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, 'network', 'The CloudPulse API is not responding. Check your connection and try again.');
  }
  if (response.ok) return response;

  let code = 'error';
  let message = `The request failed with status ${response.status}.`;
  let details: { field: string; message: string }[] | undefined;
  try {
    const body = await response.json();
    if (body?.error) ({ code, message, details } = { details: undefined, ...body.error });
  } catch {
    // Non-JSON error body: the generic message above stands.
  }
  if (response.status === 401 && sentToken) onExpired?.();
  throw new ApiError(response.status, code, message, details);
}

export async function api<T>(path: string, init?: { method?: string; body?: unknown; signal?: AbortSignal }): Promise<T> {
  const response = await send(path, {
    method: init?.method ?? 'GET',
    signal: init?.signal,
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
  });
  return response.json() as Promise<T>;
}

export const login = (email: string, password: string) =>
  api<LoginResponse>('/auth/login', { method: 'POST', body: { email, password } });

export const demoLogin = () => api<LoginResponse>('/auth/demo', { method: 'POST' });
export const signInOptions = () => api<{ demo_login: boolean }>('/auth/options');

export async function fetchBlob(path: string): Promise<Blob> {
  return (await send(path)).blob();
}
