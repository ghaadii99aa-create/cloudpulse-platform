import { useQueryClient } from '@tanstack/react-query';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { api, getToken, login as loginRequest, setExpiredHandler, setToken } from './api';
import type { Role, User } from './types';

const RANK: Record<Role, number> = { viewer: 0, engineer: 1, admin: 2 };

interface AuthValue {
  user: User | null;
  restoring: boolean;
  notice: string | null;
  signIn: (email: string, password: string) => Promise<void>;
  signOut: () => void;
  can: (role: Role) => boolean;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const client = useQueryClient();
  const [user, setUser] = useState<User | null>(null);
  const [restoring, setRestoring] = useState(() => getToken() !== null);
  const [notice, setNotice] = useState<string | null>(null);

  const clear = useCallback(() => {
    setToken(null);
    setUser(null);
    client.clear();
  }, [client]);

  useEffect(() => {
    setExpiredHandler(() => {
      clear();
      setNotice('Your session expired. Sign in again to continue.');
    });
    return () => setExpiredHandler(null);
  }, [clear]);

  useEffect(() => {
    if (!getToken()) return;
    api<User>('/auth/me')
      .then(setUser)
      .catch(() => undefined)
      .finally(() => setRestoring(false));
  }, []);

  const signIn = useCallback(async (email: string, password: string) => {
    const session = await loginRequest(email, password);
    setToken(session.access_token);
    setNotice(null);
    setUser(session.user);
  }, []);

  const value = useMemo<AuthValue>(
    () => ({
      user,
      restoring,
      notice,
      signIn,
      signOut: () => {
        setNotice(null);
        clear();
      },
      can: (role) => (user ? RANK[user.role] >= RANK[role] : false),
    }),
    [user, restoring, notice, signIn, clear],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error('useAuth must be used inside AuthProvider');
  return value;
}
