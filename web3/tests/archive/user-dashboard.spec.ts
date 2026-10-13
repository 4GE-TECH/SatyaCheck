import { test, expect, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { getMockFixture } from '../../src/api/mock';

const TONE = resolve('tests/fixtures/test-tone.wav');
const CLONE = resolve('tests/fixtures/clone.wav');

async function openSample(page: Page, name: string) {
  await page.locator('.stack-card', { hasText: name }).getByRole('button', { name: 'Open sample' }).click();
}
const REVIEW = resolve('review');

/** Waits until no CSS/WAAPI animation is running and Motion's JS-driven values have had time to land. */
async function settle(page: Page) {
  await page.waitForLoadState('networkidle');
  await page.waitForFunction(() => document.getAnimations().every(a => a.playState !== 'running' || a.effect?.getTiming().iterations === Infinity));
  await page.waitForTimeout(1600);
}

/** Every API call fails unless a test routes it: the suite never touches a real service. */
async function offline(page: Page) {
  // Match the service by path only: a glob like **/api/** would also catch the /src/api/ source modules.
  await page.route(url => url.pathname.startsWith('/api/'), route => route.fulfill({ status: 503, json: { detail: 'Screening service is unavailable.' } }));
  // The call feed connects on every page; keep it silent and away from any real service.
  await page.routeWebSocket(url => url.pathname === '/api/ws/live', () => {});
}

async function noOverflow(page: Page, where: string) {
  const wide = await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
  expect(wide, where).toBeLessThanOrEqual(1);
}

const SAMPLE_BANDS: [string, string, boolean][] = [
  ['Cloned emergency', 'High risk', true],
  ['Bank IVR', 'Unverified', true],
  ['Familiar voice', 'Voice verified', true],
  ['Unusual request', 'Caution', true],
  ['Synthetic stranger', 'Suspicious', true],
  ['Too short', 'Not enough audio', false],
];

test('every labelled sample keeps the scoring rules and is marked as a sample', async ({ page }) => {
  await offline(page);
  for (const [name, band, scored] of SAMPLE_BANDS) {
    await page.goto('/');
    await openSample(page, name);
    await expect(page).toHaveURL(/\/report\//);
    await expect(page.getByText('Labelled sample. This demonstrates a result type')).toBeVisible();
    await expect(page.locator('.verdict .tone-chip')).toHaveText(band);
    if (scored) await expect(page.locator('.trust-number')).toBeVisible();
    else {
      await expect(page.locator('.trust-number')).toHaveCount(0);
      await expect(page.getByText('No score given.')).toBeVisible();
    }
    if (band === 'Unverified') {
      await expect(page.locator('.report')).toHaveClass(/tone-neutral/);
      await expect(page.getByText('Steps back in this check')).toBeVisible();
    }
  }
});

test('an upload is drawn, checked, and reported with a real spectrogram', async ({ page }) => {
  await offline(page);
  await page.route('**/api/screen', route => route.fulfill({ json: { ...getMockFixture('red'), session_id: 'session_upload' } }));
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(TONE);
  await expect(page.getByText('test-tone.wav')).toBeVisible();
  await expect(page.getByText('0:10 ·')).toBeVisible();
  await page.getByRole('button', { name: 'Check this recording' }).click();
  await expect(page).toHaveURL(/session_upload/);
  await expect(page.getByRole('img', { name: /Spectrogram of the recording/ })).toBeVisible();
  const slider = page.getByRole('slider', { name: 'Evidence timeline' });
  await slider.focus();
  for (let i = 0; i < 10; i++) await page.keyboard.press('ArrowRight');
  await expect(slider).toHaveAttribute('aria-valuenow', '5');
  await expect(page.locator('.caption-line')).toContainText('Phone kisi ko mat dena');
  await expect(page.getByRole('button', { name: 'Play recording' })).toBeVisible();
});

test('a failed check keeps the recording and shows no verdict', async ({ page }) => {
  await offline(page);
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(TONE);
  await page.getByRole('button', { name: 'Check this recording' }).click();
  await expect(page.getByRole('alert')).toContainText('Screening service is unavailable.');
  await expect(page).toHaveURL('/');
  await expect(page.getByText('test-tone.wav')).toBeVisible();
});

test('enrollment needs consent and a confirmed voiceprint', async ({ page }) => {
  await offline(page);
  await page.route('**/api/persons', route => route.fulfill({ json: [] }));
  await page.route('**/api/enroll', route => route.fulfill({ status: 201, json: { person_id: 'p', name: 'आरव', voiceprints: [] } }));
  await page.goto('/voices');
  await page.getByLabel('Name').fill('आरव');
  await page.getByLabel('Relationship').fill('Grandson');
  await page.locator('input[type=file]').setInputFiles(TONE);
  const submit = page.getByRole('button', { name: 'Enroll voice' });
  await expect(submit).toBeDisabled();
  await page.getByRole('checkbox').check();
  await submit.click();
  await expect(page.getByRole('alert')).toContainText('did not confirm a saved voiceprint');
  await expect(page.getByText('voice is enrolled')).toHaveCount(0);
});

test('removing a known voice asks first, then calls the service', async ({ page }) => {
  await offline(page);
  let method = '';
  await page.route('**/api/persons', route => route.fulfill({ json: [{ person_id: 'p_asha', name: 'Asha', relation: 'Mother', phone_number: null, avatar_url: null, created_at: '2026-10-01T10:00:00Z', voiceprints: [{ voiceprint_id: 'v', duration_s: 31 }] }] }));
  await page.route('**/api/persons/p_asha', route => { method = route.request().method(); return route.fulfill({ json: { deleted: 'p_asha' } }); });
  await page.goto('/voices');
  await page.getByRole('button', { name: 'Remove Asha' }).click();
  await page.getByRole('button', { name: 'Keep' }).click();
  expect(method).toBe('');
  await page.getByRole('button', { name: 'Remove Asha' }).click();
  await page.getByRole('button', { name: 'Remove', exact: true }).click();
  await expect(page.getByText('Asha was removed.')).toBeVisible();
  expect(method).toBe('DELETE');
  await expect(page.getByText('No one enrolled yet')).toBeVisible();
});

test('live listening streams v2 frames, updates in place, and finalises with the audio', async ({ page }) => {
  await offline(page);
  const log = { start: null as Record<string, unknown> | null, frames: 0, bytes: 0, ended: false };
  await page.routeWebSocket('**/api/ws/v2/screen/*', ws => {
    const sessionId = new URL(ws.url()).pathname.split('/').pop()!;
    let window = 0;
    const assess = (fixture: 'caution' | 'red', final: boolean) => {
      const current = { ...getMockFixture(fixture), session_id: sessionId };
      const alerts = fixture === 'red' ? [{
        type: 'alert', alert_id: 'a1', session_id: sessionId, window_index: window, audio_start_s: 2, audio_end_s: 5,
        band: current.fusion.band, evidence: current.fusion.reason_codes.slice(0, 1), transcript_rev: window, claim_rev: 0, resolved: false, resolved_reason: null,
      }] : [];
      ws.send(JSON.stringify({
        type: 'assessment', session_id: sessionId, window_index: window++, audio_start_s: 0, audio_end_s: log.frames / 2,
        current, display_band: current.fusion.band, alerts,
        transcript_committed: 'Beta, I am in trouble', transcript_tentative: final ? '' : 'send money',
        coverage: [{ start_s: 0, end_s: 2, scored: true }, { start_s: 2, end_s: 3, scored: false }, { start_s: 3, end_s: Math.max(4, log.frames / 2), scored: true }],
        coverage_degraded: false, authenticity: { median: 0.2, peak: 0.6, max_synth_run_s: 1, scored_s: 4 },
        transcript_rev: window, claim_rev: 0, is_final: final,
      }));
    };
    ws.onMessage(raw => {
      if (typeof raw !== 'string') {
        log.frames += 1;
        log.bytes = raw.length;
        if (log.frames === 4) assess('caution', false);
        return;
      }
      const message = JSON.parse(raw);
      if (message.type === 'start') {
        log.start = message;
        ws.send(JSON.stringify({ type: 'ready', session_id: sessionId, schema_version: 2, max_frame_bytes: 64000 }));
      } else if (message.type === 'end') {
        log.ended = true;
        assess('red', true);
        ws.close();
      }
    });
  });
  await page.goto('/live');
  await page.getByRole('button', { name: 'Start listening' }).click();
  await expect(page.getByText('Provisional')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('.trace-dot')).toHaveCount(1);
  await expect(page.getByText('Beta, I am in trouble')).toBeVisible();
  await expect(page.locator('.live-transcript .tentative')).toHaveText('send money');
  await expect(page.locator('.coverage-bar .gap')).toHaveCount(1);
  await page.waitForTimeout(1500);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(REVIEW, 'live-session.png') });
  await page.getByRole('button', { name: 'Stop and finalise' }).click();
  await expect(page).toHaveURL(/\/report\/live_/, { timeout: 10_000 });
  await expect(page.locator('.verdict .tone-chip')).toHaveText('High risk');
  await expect(page.getByRole('img', { name: /Spectrogram of the recording/ })).toBeVisible();
  expect(log.start).toMatchObject({ type: 'start', client: 'web3', sample_rate: 16000, encoding: 's16le' });
  expect(log.frames).toBeGreaterThanOrEqual(4);
  expect(log.bytes).toBeLessThanOrEqual(16000);  // 0.5 s of 16 kHz int16
  expect(log.ended).toBe(true);
});

function verdict(over: Record<string, unknown> = {}) {
  return {
    type: 'verdict', schema_version: 1, session_id: 'MZcall01', window_index: 0, is_final: false, escalated: false,
    timestamp: '2026-10-10T10:00:00Z', band: 'insufficient', overlay_state: 'grey', trust_score: 100, risk_score: 0,
    mode: 'authority_check', signals: { identity: 'unknown', authenticity: 'unavailable', intent_risk: 0 },
    reason_codes: [], transcript: '', language: 'unknown',
    caller_context: { claimed_number: '+919876543210', claimed_name: null, claimed_identity: null, channel_type: 'telephony' },
    threat_label: null, recommended_actions: [], vernacular_warning: null, window_trust_score: 100, window_band: 'insufficient',
    ...over,
  };
}

test('phone calls arrive on the live feed, escalate in place, and end with a report link', async ({ page }) => {
  await offline(page);
  let feed: { send: (m: string) => void } | null = null;
  await page.routeWebSocket(url => url.pathname === '/api/ws/live', ws => {
    feed = ws;
    ws.send(JSON.stringify({ type: 'hello', schema_version: 1, server_time: '2026-10-10T10:00:00Z' }));
  });
  await page.goto('/calls');
  await expect(page.getByText('Watching for calls')).toBeVisible();
  await expect(page.getByText('No call in progress.')).toBeVisible();
  await expect(page.locator('.stream-url code')).toContainText('/api/exotel/stream');

  await expect.poll(() => feed !== null).toBe(true);
  feed!.send(JSON.stringify(verdict()));
  const card = page.locator('.call-card');
  await expect(card).toHaveCount(1);
  await expect(card).toContainText('+919876543210');
  await expect(card.locator('.tone-chip')).toHaveText('Listening…');

  feed!.send(JSON.stringify(verdict({
    window_index: 4, escalated: true, band: 'high_risk', overlay_state: 'red', trust_score: 12, risk_score: 0.88,
    signals: { identity: 'unknown', authenticity: 'synthetic', intent_risk: 0.94 },
    reason_codes: [{ code: 'RC_SYNTHETIC_VOICE_DETECTED', signal: 'authenticity', value: 'Peak 98%', threshold: '> 40%', explanation: 'Deepfake speech synthesis signatures detected.', citation_title: null, citation_url: null, severity: 'critical' }],
    transcript: 'Papa emergency ho gaya hai, turant 50000 bhejo is UPI ID pe!', language: 'hi',
    threat_label: { sector: 'law_enforcement_impersonation', threat: 'Digital arrest', family: 'digital_arrest' },
    recommended_actions: ['DO NOT transfer money via UPI.'],
    vernacular_warning: 'सावधान! कोई भी पैसा ट्रांसफर न करें।',
    window_trust_score: 40, window_band: 'suspicious',
  })));
  await expect(card.locator('.tone-chip')).toHaveText('High risk');
  await expect(card).toHaveClass(/tone-danger/);
  await expect(card).toContainText('Signs of a synthetic voice');
  await expect(card).toContainText('Digital arrest');
  await expect(card).toContainText('Deepfake speech synthesis signatures detected.');
  await expect(card).toContainText('turant 50000 bhejo');
  await expect(card).toContainText('Do not transfer money via UPI.');
  await expect(page.getByRole('link', { name: 'Open the full report' })).toHaveCount(0);
  await settle(page);
  await page.screenshot({ path: resolve(REVIEW, 'calls-live.png') });

  feed!.send(JSON.stringify(verdict({ window_index: 5, is_final: true, band: 'high_risk', overlay_state: 'red', trust_score: 12 })));
  await expect(page.getByRole('heading', { name: /Ended in this session/ })).toBeVisible();
  await expect(page.getByRole('link', { name: 'Open the full report' })).toHaveAttribute('href', '/report/MZcall01');
  await noOverflow(page, 'calls page');
});

test('a token-protected call feed asks for the token instead of retrying blindly', async ({ page }) => {
  await offline(page);
  const tokens: string[] = [];
  await page.routeWebSocket(url => url.pathname === '/api/ws/live', ws => {
    const token = new URL(ws.url()).searchParams.get('token') ?? '';
    tokens.push(token);
    if (token !== 'secret') ws.close({ code: 1008, reason: 'token' });
    else ws.send(JSON.stringify({ type: 'hello', schema_version: 1 }));
  });
  await page.goto('/calls');
  await expect(page.getByText('The feed needs a token')).toBeVisible();
  await page.getByLabel('Live-feed token').fill('secret');
  await page.getByRole('button', { name: 'Connect with token' }).click();
  await expect(page.getByText('Watching for calls')).toBeVisible();
  expect(tokens.at(-1)).toBe('secret');
});

test('saved reports load by ID, and malformed ones are refused', async ({ page }) => {
  await offline(page);
  await page.route('**/api/screen/stored', route => route.fulfill({ json: { ...getMockFixture('red'), session_id: 'stored' } }));
  await page.route('**/api/screen/broken', route => route.fulfill({ json: { session_id: 'broken' } }));
  await page.goto('/reports');
  await page.getByLabel('Session ID').fill('stored');
  await page.getByRole('button', { name: 'Open report' }).click();
  await expect(page.getByRole('heading', { name: 'Pause. Verify independently.' })).toBeVisible();
  await page.goto('/report/broken');
  await expect(page.getByRole('alert')).toContainText('incomplete result');
  await expect(page.locator('.verdict')).toHaveCount(0);
});

test('the command menu finds pages and samples from the keyboard', async ({ page }) => {
  await offline(page);
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible();
  await page.keyboard.press('Control+k');
  await page.getByRole('combobox', { name: 'Search commands' }).fill('bank');
  await page.keyboard.press('Enter');
  await expect(page.locator('.verdict .tone-chip')).toHaveText('Unverified');
});

test('every route fits small screens without sideways scrolling', async ({ page }) => {
  await offline(page);
  await page.route('**/api/persons', route => route.fulfill({ json: [] }));
  for (const width of [320, 390, 768]) {
    await page.setViewportSize({ width, height: 860 });
    for (const path of ['/', '/live', '/calls', '/voices', '/reports', '/help']) {
      await page.goto(path);
      await noOverflow(page, `${path} at ${width}px`);
    }
    await page.goto('/');
    await page.locator('input[type=file]').setInputFiles({ name: `${'a-very-long-recording-name-'.repeat(8)}.wav`, mimeType: 'audio/wav', buffer: Buffer.from('RIFF') });
    await noOverflow(page, `long file name at ${width}px`);
    await page.goto('/');
    await openSample(page, 'Cloned emergency');
    await expect(page).toHaveURL(/report/);
    await noOverflow(page, `report at ${width}px`);
  }
});

test('visual evidence across themes and sizes, with no runtime errors', async ({ page }) => {
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await mkdir(REVIEW, { recursive: true });
  await offline(page);
  await page.route('**/api/screen', route => route.fulfill({ json: { ...getMockFixture('red'), session_id: 'session_visual' } }));
  for (const [label, width, height] of [['desktop', 1440, 900], ['mobile', 390, 844]] as const) {
    for (const scheme of ['dark', 'light'] as const) {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ colorScheme: scheme, reducedMotion: 'reduce' });
      await page.goto('/');
      await settle(page);
      await page.screenshot({ path: resolve(REVIEW, `${label}-${scheme}-home.png`) });
      if (scheme === 'dark') await page.screenshot({ path: resolve(REVIEW, `${label}.png`) });
      await page.locator('input[type=file]').setInputFiles(CLONE);
      await page.getByRole('button', { name: 'Check this recording' }).click();
      await expect(page.getByRole('img', { name: /Spectrogram of the recording/ })).toBeVisible();
      for (let y = 0; y < 4000; y += 600) { await page.mouse.wheel(0, 600); await page.waitForTimeout(120); }
      await page.evaluate(() => window.scrollTo(0, 0));
      await settle(page);
      await page.screenshot({ path: resolve(REVIEW, `${label}-${scheme}-report.png`), fullPage: true });
    }
  }
  expect(errors).toEqual([]);
});
