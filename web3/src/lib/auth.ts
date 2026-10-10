import { createClient, type Session, type SupabaseClient } from '@supabase/supabase-js';

/**
 * Sign-in with an emailed one-time code (Supabase Auth).
 *
 * On when the build names a Supabase project (VITE_SUPABASE_URL + VITE_SUPABASE_ANON_KEY,
 * both public values). Off otherwise: the backend then runs in AUTH_MODE=dev and every
 * request acts for its dev account, as before sign-in existed.
 *
 * The session lives in memory only. CLAUDE.md forbids browser storage in the web app, so
 * a reload means signing in again. That is deliberate, not a bug to "fix" with localStorage.
 */
const SUPABASE_URL = (import.meta.env?.VITE_SUPABASE_URL ?? '').replace(/\/+$/, '');
const SUPABASE_ANON_KEY = import.meta.env?.VITE_SUPABASE_ANON_KEY ?? '';

export const authEnabled = Boolean(SUPABASE_URL && SUPABASE_ANON_KEY);

let client: SupabaseClient | null = null;

function supabase(): SupabaseClient {
  if (!client) {
    client = createClient(SUPABASE_URL, SUPABASE_ANON_KEY, {
      auth: { persistSession: false, autoRefreshToken: true, detectSessionInUrl: false },
    });
  }
  return client;
}

/** Sends a 6-digit code to the address. Resolves to an error message, or null when sent. */
export async function sendCode(email: string): Promise<string | null> {
  const { error } = await supabase().auth.signInWithOtp({ email, options: { shouldCreateUser: true } });
  return error ? 'The code could not be sent. Check the address and try again.' : null;
}

/** Checks the code. Resolves to an error message, or null when signed in. */
export async function verifyCode(email: string, token: string): Promise<string | null> {
  const { error } = await supabase().auth.verifyOtp({ email, token, type: 'email' });
  return error ? 'That code did not work. Check it, or send a new one.' : null;
}

/** The current access token, refreshed when needed; null when signed out or sign-in is off. */
export async function accessToken(): Promise<string | null> {
  if (!authEnabled) return null;
  const { data } = await supabase().auth.getSession();
  return data.session?.access_token ?? null;
}

export async function signOut(): Promise<void> {
  if (authEnabled) await supabase().auth.signOut();
}

/** Calls back with the session now and on every change. Returns the unsubscribe function. */
export function watchSession(callback: (session: Session | null) => void): () => void {
  if (!authEnabled) return () => {};
  void supabase().auth.getSession().then(({ data }) => callback(data.session));
  const { data } = supabase().auth.onAuthStateChange((_event, session) => callback(session));
  return () => data.subscription.unsubscribe();
}
