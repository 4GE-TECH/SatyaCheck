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

test('live listening streams WAV slices, updates in place, and finalises with the audio', async ({ page }) => {
  await offline(page);
  const slices: { final: boolean; riff: boolean }[] = [];
  await page.routeWebSocket('**/api/ws/screen/*', ws => {
    ws.onMessage(raw => {
      const message = JSON.parse(String(raw));
      slices.push({ final: message.is_final, riff: Buffer.from(message.audio_base64, 'base64').subarray(0, 4).toString() === 'RIFF' });
      const fixture = slices.length > 1 ? 'red' : 'caution';
      ws.send(JSON.stringify({ type: 'screening_update', session_id: message.session_id, chunk_index: message.chunk_index, response: { ...getMockFixture(fixture), session_id: message.session_id } }));
      if (message.is_final) ws.close();
    });
  });
  await page.goto('/live');
  await page.getByRole('button', { name: 'Start listening' }).click();
  await expect(page.getByText('Provisional')).toBeVisible({ timeout: 10_000 });
  await expect(page.locator('.trace-dot')).toHaveCount(1);
  await page.waitForTimeout(3300);
  await page.evaluate(() => window.scrollTo(0, 0));
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(REVIEW, 'live-session.png') });
  await page.getByRole('button', { name: 'Stop and finalise' }).click();
  await expect(page).toHaveURL(/\/report\/live_/, { timeout: 10_000 });
  await expect(page.locator('.verdict .tone-chip')).toHaveText('High risk');
  await expect(page.getByRole('img', { name: /Spectrogram of the recording/ })).toBeVisible();
  expect(slices.length).toBeGreaterThanOrEqual(2);
  expect(slices.every(s => s.riff)).toBe(true);
  expect(slices.at(-1)!.final).toBe(true);
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
    for (const path of ['/', '/live', '/voices', '/reports', '/help']) {
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
