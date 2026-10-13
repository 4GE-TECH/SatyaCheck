import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import type { Session } from '@supabase/supabase-js';
import { authEnabled, signInWithPassword, signOut, watchSession } from '../lib/auth';
import { adminMe } from '../lib/admin';
import { Button, Notice } from '../components/ui';

type Access = 'checking' | 'admin' | 'not-admin' | 'error';

/**
 * The admin console is for accounts the server lists in ADMIN_USER_IDS. This screen signs in
 * (email and password: the shared admin account), then asks the server whether that account
 * is an admin. The server decides; this only keeps the console from showing to anyone else.
 */
export default function AdminGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(authEnabled ? undefined : null);
  const [access, setAccess] = useState<Access>('checking');
  const [problem, setProblem] = useState('');

  useEffect(() => watchSession(setSession), []);

  useEffect(() => {
    if (!session) return;
    const controller = new AbortController();
    setAccess('checking');
    adminMe(controller.signal)
      .then(me => setAccess(me ? 'admin' : 'not-admin'))
      .catch(e => { if (!controller.signal.aborted) { setProblem(e instanceof Error ? e.message : String(e)); setAccess('error'); } });
    return () => controller.abort();
  }, [session]);

  if (!authEnabled) {
    return (
      <main className="fallback sign-in">
        <h1>SatyaCheck admin</h1>
        <Notice tone="caution">
          This build has no sign-in configured. Set VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY, then rebuild.
        </Notice>
      </main>
    );
  }
  if (session === undefined) return <div className="page-loading" role="status">Loading…</div>;
  if (!session) return <AdminSignIn />;
  if (access === 'checking') return <div className="page-loading" role="status">Checking access…</div>;
  if (access === 'admin') return <>{children}</>;
  return (
    <main className="fallback sign-in">
      <h1>{access === 'not-admin' ? 'This account is not an administrator' : 'The console could not start'}</h1>
      <p>{access === 'not-admin'
        ? 'Only accounts listed on the server as administrators can open this console.'
        : problem || 'The screening service did not answer.'}</p>
      <Button variant="primary" onClick={() => void signOut()}>Sign out</Button>
    </main>
  );
}

function AdminSignIn() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const problem = await signInWithPassword(email.trim(), password);
    setBusy(false);
    if (problem) setError(problem);
  }

  return (
    <main className="fallback sign-in">
      <h1>SatyaCheck admin</h1>
      <p>For the development team. Every call you open here is logged against your account.</p>
      <form onSubmit={submit} className="sign-in-form">
        <div className="field">
          <label htmlFor="admin-email">Email</label>
          <input id="admin-email" className="input" type="email" required autoComplete="username"
            value={email} onChange={e => setEmail(e.target.value)} />
        </div>
        <div className="field">
          <label htmlFor="admin-password">Password</label>
          <input id="admin-password" className="input" type="password" required autoComplete="current-password"
            value={password} onChange={e => setPassword(e.target.value)} />
        </div>
        {error && <Notice tone="danger">{error}</Notice>}
        <Button type="submit" variant="primary" busy={busy}>Sign in</Button>
      </form>
      <p className="muted">You stay signed in until you close or reload this tab.</p>
    </main>
  );
}
