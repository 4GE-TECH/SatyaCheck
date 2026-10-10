import { useEffect, useState, type FormEvent, type ReactNode } from 'react';
import type { Session } from '@supabase/supabase-js';
import { authEnabled, sendCode, verifyCode, watchSession } from '../lib/auth';
import { Button, Notice } from '../components/ui';

/** Shows the app only to a signed-in account (when sign-in is on). */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(authEnabled ? undefined : null);
  useEffect(() => watchSession(setSession), []);
  if (!authEnabled) return <>{children}</>;
  if (session === undefined) return <div className="page-loading" role="status">Loading…</div>;
  return session ? <>{children}</> : <SignIn />;
}

function SignIn() {
  const [email, setEmail] = useState('');
  const [code, setCode] = useState('');
  const [step, setStep] = useState<'email' | 'code'>('email');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setError(null);
    const problem = step === 'email' ? await sendCode(email.trim()) : await verifyCode(email.trim(), code.trim());
    setBusy(false);
    if (problem) setError(problem);
    else if (step === 'email') setStep('code');
  }

  return (
    <main className="fallback sign-in">
      <h1>Sign in to SatyaCheck</h1>
      <p>We will email you a 6-digit code. There is no password to remember.</p>
      <form onSubmit={submit} className="sign-in-form">
        {step === 'email' ? (
          <div className="field">
            <label htmlFor="sign-in-email">Email address</label>
            <input id="sign-in-email" className="input" type="email" required autoComplete="email"
              value={email} onChange={e => setEmail(e.target.value)} />
          </div>
        ) : (
          <div className="field">
            <label htmlFor="sign-in-code">Code sent to {email}</label>
            <input id="sign-in-code" className="input num" inputMode="numeric" pattern="[0-9]{6}" maxLength={6}
              required autoComplete="one-time-code" value={code} onChange={e => setCode(e.target.value.replace(/\D/g, ''))} />
          </div>
        )}
        {error && <Notice tone="danger">{error}</Notice>}
        <Button type="submit" variant="primary" busy={busy}>
          {step === 'email' ? 'Email me a code' : 'Sign in'}
        </Button>
        {step === 'code' && (
          <Button variant="ghost" onClick={() => { setStep('email'); setCode(''); setError(null); }}>
            Use a different address
          </Button>
        )}
      </form>
      <p className="muted">You stay signed in until you close or reload this tab.</p>
    </main>
  );
}
