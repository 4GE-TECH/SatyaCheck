import { test, expect, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { getMockFixture } from '../../src/api/mock';

/**
 * The admin console against a stand-in Supabase project (https://supabase.test, set in
 * playwright.config.ts) and a scripted /api/admin. The suite never touches a real service.
 */

const REVIEW = resolve('review');
const ADMIN = { id: 'admin-1', email: 'admin@satyacheck.test' };

async function settle(page: Page) {
  await page.waitForLoadState('networkidle');
  await page.waitForTimeout(800);
}

/** Supabase password sign-in: accepts `password`, refuses anything else. */
async function supabase(page: Page, user = ADMIN) {
  await page.route(url => url.hostname === 'supabase.test', async route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/auth/v1/token' && url.searchParams.get('grant_type') === 'password') {
      const body = route.request().postDataJSON() as { password?: string };
      if (body.password !== 'password') {
        return route.fulfill({ status: 400, json: { error: 'invalid_grant', error_description: 'Invalid login credentials' } });
      }
      const now = Math.floor(Date.now() / 1000);
      return route.fulfill({
        json: {
          access_token: `token-${user.id}`, token_type: 'bearer', expires_in: 3600, expires_at: now + 3600,
          refresh_token: 'refresh', user: { id: user.id, aud: 'authenticated', role: 'authenticated', email: user.email,
            app_metadata: { provider: 'email' }, user_metadata: {}, created_at: '2026-10-13T00:00:00Z' },
        },
      });
    }
    if (url.pathname === '/auth/v1/logout') return route.fulfill({ status: 204, body: '' });
    return route.fulfill({ status: 404, json: {} });
  });
}

/** /api/admin as an admin would see it. Anything unscripted fails loudly. */
async function adminApi(page: Page, opts: { admin?: boolean } = {}) {
  const red = { ...getMockFixture('red'), session_id: 'rtc_abc123_caller' };
  await page.route(url => url.pathname.startsWith('/api/'), route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/health') return route.fulfill({ json: { status: 'ok' } });   // public, like the real one
    const auth = route.request().headers()['authorization'];
    if (!auth?.startsWith('Bearer ')) return route.fulfill({ status: 401, json: { detail: 'Sign in required.' } });
    if (opts.admin === false) return route.fulfill({ status: 403, json: { detail: 'This console is for administrators.' } });
    switch (url.pathname) {
      case '/api/admin/me': return route.fulfill({ json: { user_id: ADMIN.id, admin: true } });
      case '/api/admin/overview': return route.fulfill({ json: {
        calls: { ringing: 1, active: 1 }, live_sessions: 2, max_live_sessions: 4, screenings_24h: 7,
        bands_24h: { high_risk: 2, unverified: 4, verified: 1 }, accounts_with_calls: 3, accounts_with_username: 2,
        device: 'cuda', ready: true, problems: [], webrtc_enabled: true,
      } });
      case '/api/admin/calls/live': return route.fulfill({ json: { calls: [{
        call_id: 'abc123', status: 'active', age_s: 95, in_call_s: 80, screening: true,
        caller: { user_id: 'u-asha', username: 'asha', display_name: 'Asha' },
        callee: { user_id: 'u-ravi', username: 'ravi', display_name: 'Ravi' },
        voices: [
          { session_id: 'rtc_abc123_caller', speaker_id: 'u-asha', listener_id: 'u-ravi', state: {
            rev: 4, display_band: 'high_risk', trust_score: 18, mode: 'authority_check', screening_available: true, reason: null,
            reasons: [], alerts: [{ alert_id: 'a1', band: 'high_risk', at_s: 22, resolved: false, evidence: 'Asks you not to tell anyone.' }],
            coverage: { screened_s: 70, unscreened_s: 0, degraded: false }, transcript_tail: 'tail only' } },
          { session_id: 'rtc_abc123_callee', speaker_id: 'u-ravi', listener_id: 'u-asha', state: {
            rev: 2, display_band: 'unverified', trust_score: 61, mode: 'authority_check', screening_available: true, reason: null,
            reasons: [], alerts: [], coverage: { screened_s: 60, unscreened_s: 0, degraded: false }, transcript_tail: 'haan bolo' } },
        ],
      }] } });
      case '/api/admin/screenings': return route.fulfill({ json: { next_cursor: null, items: [
        { session_id: 'rtc_abc123_caller', created_at: '2026-10-13T10:00:00Z', status: 'complete', channel_type: 'webrtc',
          owner: { user_id: 'u-ravi', username: 'ravi', display_name: 'Ravi' }, band: 'high_risk', trust_score: 18,
          mode: 'authority_check', transcript_preview: 'Papa ko mat batana, abhi paise bhejo' },
        { session_id: 'upload-1', created_at: '2026-10-13T09:00:00Z', status: 'complete', channel_type: 'upload',
          owner: { user_id: 'u-zed', username: null, display_name: null }, band: 'unverified', trust_score: 64,
          mode: 'authority_check', transcript_preview: 'Hello, this is the bank' },
      ] } });
      case '/api/admin/screenings/rtc_abc123_caller': return route.fulfill({ json: {
        session_id: 'rtc_abc123_caller', owner: { user_id: 'u-ravi', username: 'ravi', display_name: 'Ravi' },
        channel_type: 'webrtc', status: 'complete', created_at: '2026-10-13T10:00:00Z', response: red,
        timeline: [
          { chunk_index: 0, is_final: false, at: null, band: 'insufficient', trust_score: null },
          { chunk_index: 1, is_final: false, at: null, band: 'caution', trust_score: 40 },
          { chunk_index: 2, is_final: true, at: null, band: 'high_risk', trust_score: 18 },
        ],
      } });
      case '/api/admin/users': return route.fulfill({ json: { users: [
        { user_id: 'u-ravi', username: 'ravi', display_name: 'Ravi', calls: 3, enrolled_voices: 1, connections: 1, last_call_at: '2026-10-13T10:00:00Z', admin: false },
        { user_id: ADMIN.id, username: null, display_name: null, calls: 0, enrolled_voices: 0, connections: 0, last_call_at: null, admin: true },
      ] } });
      default: return route.fulfill({ status: 404, json: { detail: `unscripted ${url.pathname}` } });
    }
  });
}

/** The admin live feed: signs in with the first message, then sends one verdict per session. */
async function adminFeed(page: Page) {
  const seen: unknown[] = [];
  await page.routeWebSocket(url => url.pathname === '/api/admin/ws/live', ws => {
    ws.onMessage(raw => {
      const msg = JSON.parse(String(raw));
      seen.push(msg);
      if (msg.type !== 'auth' || msg.token !== `token-${ADMIN.id}`) { ws.close({ code: 1008 }); return; }
      ws.send(JSON.stringify({ type: 'hello', schema_version: 1 }));
      ws.send(JSON.stringify({ type: 'verdict', session_id: 'rtc_abc123_caller', owner_id: 'u-ravi', window_index: 4,
        is_final: false, band: 'high_risk', trust_score: 18, mode: 'authority_check',
        transcript: 'Beta main police station mein hoon. Papa ko mat batana, abhi paise bhejo.', language: 'hi',
        signals: { identity: 'unknown', authenticity: 'synthetic', intent_risk: 0.8 }, reason_codes: [] }));
      ws.send(JSON.stringify({ type: 'verdict', session_id: 'live_web_1', owner_id: 'u-zed', window_index: 1,
        is_final: false, band: 'unverified', trust_score: 62, mode: 'authority_check',
        transcript: 'Hello, I am calling about your delivery.', language: 'en',
        signals: { identity: 'unknown', authenticity: 'bonafide', intent_risk: 0.1 }, reason_codes: [] }));
    });
  });
  // The earlier per-account feed is not used by the console; keep it silent.
  await page.routeWebSocket(url => url.pathname === '/api/ws/live', () => {});
  return seen;
}

async function signIn(page: Page, password = 'password') {
  await page.goto('/');
  await page.getByLabel('Email').fill(ADMIN.email);
  await page.getByLabel('Password').fill(password);
  await page.getByRole('button', { name: 'Sign in' }).click();
}

test.beforeAll(async () => { await mkdir(REVIEW, { recursive: true }); });

test('the console asks for the admin sign-in and refuses a wrong password', async ({ page }) => {
  await supabase(page);
  await adminApi(page);
  await adminFeed(page);
  await signIn(page, 'wrong');
  await expect(page.getByText('That email and password did not work.')).toBeVisible();
  await page.getByLabel('Password').fill('password');
  await page.getByRole('button', { name: 'Sign in' }).click();
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
});

test('an account that is not an admin sees a refusal, not the console', async ({ page }) => {
  await supabase(page, { id: 'u-ravi', email: 'ravi@example.com' });
  await adminApi(page, { admin: false });
  await adminFeed(page);
  await signIn(page);
  await expect(page.getByRole('heading', { name: 'This account is not an administrator' })).toBeVisible();
  await expect(page.getByRole('navigation', { name: 'Main' }).first()).toHaveCount(0);
});

test('the overview counts live calls and the last day by band', async ({ page }) => {
  await supabase(page);
  await adminApi(page);
  await adminFeed(page);
  await signIn(page);
  await expect(page.getByText('App calls in progress')).toBeVisible();
  await expect(page.locator('.admin-tile-value').first()).toHaveText('1');
  await expect(page.locator('.band-bars li')).toHaveCount(3);
  await settle(page);
  await page.screenshot({ path: resolve(REVIEW, 'admin-overview.png'), fullPage: true });
});

test('live calls show both people, what each says, and what each listener is shown', async ({ page }) => {
  await supabase(page);
  await adminApi(page);
  const seen = await adminFeed(page);
  await signIn(page);
  await page.getByRole('link', { name: 'Live calls' }).first().click();
  const call = page.locator('.live-call').first();
  await expect(call.getByRole('heading', { name: /@asha.*@ravi/ })).toBeVisible();
  await expect(call.getByText('Papa ko mat batana, abhi paise bhejo.')).toBeVisible();   // full transcript from the feed
  await expect(call.getByText('haan bolo')).toBeVisible();                               // the agent's tail when the feed has none
  await expect(call.getByText('Asks you not to tell anyone.')).toBeVisible();
  await expect(call.locator('.voice-pane').first().getByText('High risk')).toBeVisible();
  await expect(page.getByText('Hello, I am calling about your delivery.')).toBeVisible(); // another live session
  expect(seen[0]).toEqual({ type: 'auth', token: `token-${ADMIN.id}` });                 // signed in by message, not URL
  await settle(page);
  await page.screenshot({ path: resolve(REVIEW, 'admin-live.png'), fullPage: true });
});

test('all calls lists every account, and a call opens with its transcript and how it moved', async ({ page }) => {
  await supabase(page);
  await adminApi(page);
  await adminFeed(page);
  await signIn(page);
  await page.getByRole('link', { name: 'All calls' }).first().click();
  await expect(page.locator('.admin-table tbody tr')).toHaveCount(2);
  await expect(page.getByText('@ravi')).toBeVisible();
  await expect(page.getByText(/Account u-zed/)).toBeVisible();
  await page.getByText('Papa ko mat batana, abhi paise bhejo').click();
  await expect(page).toHaveURL(/\/calls\/rtc_abc123_caller$/);
  await expect(page.locator('.verdict-strip li')).toHaveCount(3);
  await expect(page.getByText('the caller’s voice')).toBeVisible();
  await expect(page.locator('.verdict .tone-chip').first()).toHaveText('High risk');
  await settle(page);
  await page.screenshot({ path: resolve(REVIEW, 'admin-call.png'), fullPage: true });
});

test('accounts list links to each account’s calls', async ({ page }) => {
  await supabase(page);
  await adminApi(page);
  await adminFeed(page);
  await signIn(page);
  await page.getByRole('link', { name: 'Accounts' }).first().click();
  await expect(page.locator('.admin-table tbody tr')).toHaveCount(2);
  await page.getByRole('link', { name: '@ravi' }).click();
  await expect(page).toHaveURL(/\/calls\?owner=u-ravi$/);
});

test('every page fits a phone screen without sideways scrolling', async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await supabase(page);
  await adminApi(page);
  await adminFeed(page);
  await signIn(page);
  await expect(page.getByRole('heading', { name: 'Overview' })).toBeVisible();
  for (const path of ['/', '/live', '/calls', '/calls/rtc_abc123_caller', '/users']) {
    // In-app navigation: a reload would drop the in-memory sign-in and measure the sign-in screen.
    await page.evaluate(p => { history.pushState({}, '', p); dispatchEvent(new PopStateEvent('popstate')); }, path);
    await expect(page.locator('.admin-page').first()).toBeVisible();
    await settle(page);
    const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
    expect(wide, path).toBeLessThanOrEqual(1);
  }
});
