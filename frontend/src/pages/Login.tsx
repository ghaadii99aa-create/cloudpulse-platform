import { Activity, Moon, Sun } from 'lucide-react';
import { useEffect, useState, type FormEvent } from 'react';
import { Navigate, useLocation, useNavigate } from 'react-router-dom';
import { Button } from '../components/ui';
import { ApiError, signInOptions } from '../lib/api';
import { useAuth } from '../lib/auth';
import { toggleTheme, useTheme } from '../lib/theme';

const input = 'mt-1 block min-h-11 w-full rounded-md border border-line bg-panel px-3 text-base text-ink';

function loginMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return 'That email and password do not match. Check them and try again.';
    if (error.status === 429) return 'Too many failed attempts. Wait five minutes, then try again.';
    if (error.status === 422) return 'Enter a valid email address and your password.';
    return error.message;
  }
  return 'Sign-in failed. Try again.';
}

export default function Login() {
  const { user, signIn, signInDemo, notice } = useAuth();
  const theme = useTheme();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [demo, setDemo] = useState(false);

  useEffect(() => {
    signInOptions().then((options) => setDemo(options.demo_login)).catch(() => undefined);
  }, []);

  if (user) return <Navigate to="/" replace />;

  async function run(action: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await action();
      navigate((location.state as { from?: string } | null)?.from ?? '/', { replace: true });
    } catch (e) {
      setError(loginMessage(e));
    } finally {
      setBusy(false);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    void run(() => signIn(email.trim(), password));
  }

  return (
    <div className="grid min-h-dvh place-items-center p-4">
      <button type="button" onClick={toggleTheme} aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`} className="fixed right-4 top-4 grid size-10 cursor-pointer place-items-center rounded-md text-muted hover:bg-panel hover:text-ink">
        {theme === 'dark' ? <Sun size={18} aria-hidden /> : <Moon size={18} aria-hidden />}
      </button>
      <div className="w-full max-w-sm">
        <p className="flex items-center gap-2 font-display text-2xl font-semibold tracking-tight"><Activity className="text-accent" aria-hidden /> CloudPulse</p>
        <h1 className="mt-6 font-display text-4xl font-semibold leading-tight tracking-tight">Know what your cloud is doing and what it costs.</h1>
        <form onSubmit={submit} className="mt-8 space-y-4">
          {notice && <p role="status" className="text-warn">{notice}</p>}
          <label className="block text-sm font-medium">Email
            <input className={input} type="email" autoComplete="username" required value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
          <label className="block text-sm font-medium">Password
            <input className={input} type="password" autoComplete="current-password" required value={password} onChange={(e) => setPassword(e.target.value)} />
          </label>
          {error && <p role="alert" className="text-crit">{error}</p>}
          <Button type="submit" variant="primary" disabled={busy} className="min-h-11 w-full">Sign in</Button>
        </form>
        {demo && (
          <div className="mt-6 border-t border-line pt-5">
            <Button disabled={busy} className="min-h-11 w-full" onClick={() => void run(signInDemo)}>View the demo</Button>
            <p className="mt-2 text-sm text-muted">Read-only access to simulated data. No account needed.</p>
          </div>
        )}
      </div>
    </div>
  );
}
