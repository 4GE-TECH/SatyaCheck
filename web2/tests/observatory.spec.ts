import { test, expect, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { sampleCheck } from '../src/lib/samples';
import { bandFor, readResult } from '../src/lib/api';
import type { TrustBand } from '../src/lib/contracts';
const file = { name: 'Family-callback-Hinglish.wav', mimeType: 'audio/wav', buffer: Buffer.from('fixture audio') };
const person = { person_id: 'p1', name: 'किरण चन्द्रशेखर विश्वनाथन श्रीवास्तव', relation: 'Family friend and emergency contact', phone_number: null, created_at: '2026-10-09T10:00:00Z', voiceprints: [{ voiceprint_id: 'v1', duration_s: 60 }] };
async function offline(page: Page) { await page.route('**/api/**', route => route.fulfill({ status: 503, json: { detail: 'Service unavailable. Please retry.' } })); }
async function noOverflow(page: Page) { expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true); }
async function sample(page: Page, band: TrustBand) {
  await page.goto('/');
  const labels = { high_risk: 'The urgent money request', unverified: 'The automated reminder', verified: 'The family check-in', caution: 'Caution', suspicious: 'Suspicious signals', insufficient: 'Insufficient audio' };
  if (['caution','suspicious','insufficient'].includes(band)) await page.getByText('Explore more result states', { exact: true }).click();
  await page.getByRole('button', { name: new RegExp(labels[band]) }).click();
  await expect(page.locator('.sample-notice')).toContainText('not an analysis of your audio');
}

test('contract guards keep unknown voices neutral and reject corrupted evidence', () => {
  const result = sampleCheck('verified').result;
  expect(readResult(result).ok).toBe(true);
  result.fusion.mode = 'authority_check'; expect(bandFor(result)).toBe('unverified');
  result.fusion.mode = 'identity_check'; result.speaker.verdict = 'unknown'; expect(bandFor(result)).toBe('unverified');
  result.quality.passed = false; expect(bandFor(result)).toBe('insufficient');
  expect(readResult({ ...result, spoof: null }).ok).toBe(false);
  expect(readResult({ ...result, fusion: { ...result.fusion, recommended_actions: [null] } }).ok).toBe(false);
});

test('six sample results preserve score semantics and tabs expose returned evidence', async ({ page }) => {
  await offline(page);
  for (const band of ['verified','caution','suspicious','high_risk','unverified','insufficient'] as const) {
    await sample(page, band);
    if (band === 'insufficient') { await expect(page.locator('.score-dial')).toContainText('Not reported'); await expect(page.locator('.score-dial')).not.toContainText('/100'); await expect(page.locator('.signal-cards')).toHaveCount(0); }
    else await expect(page.locator('.score-dial')).toContainText('/100');
    if (band === 'unverified') await expect(page.locator('.score-dial')).toHaveClass(/neutral/);
    await page.getByRole('tab', { name: 'transcript', exact: true }).click(); await expect(page.locator('.transcript')).toBeVisible();
    await page.getByRole('tab', { name: 'references', exact: true }).click(); await expect(page.locator('.reason').first()).toBeVisible();
    await page.getByRole('link', { name: 'Your reports', exact: true }).click(); await expect(page.locator('.report-list-item')).toHaveCount(1);
  }
});

test('real upload failure stays recoverable without a fabricated result', async ({ page }) => {
  await offline(page); await page.goto('/');
  await page.locator('input[type=file]').setInputFiles(file); await page.getByRole('button', { name: 'Analyze recording' }).click();
  await expect(page.getByRole('alert')).toContainText('Service unavailable'); await expect(page.locator('.chosen-file')).toContainText(file.name); await expect(page.locator('.score-dial')).toHaveCount(0);
  const result = sampleCheck('high_risk').result; result.session_id = 'actual-session';
  await page.route('**/api/screen', route => route.fulfill({ json: result }));
  await page.getByRole('button', { name: 'Analyze recording' }).click(); await expect(page).toHaveURL(/actual-session/); await expect(page.locator('.sample-notice')).toHaveCount(0);
});

test('cancelled analysis cannot save a late result', async ({ page }) => {
  await offline(page); let release: (() => void) | undefined;
  await page.route('**/api/screen', async route => { await new Promise<void>(r => { release = r; }); await route.fulfill({ json: sampleCheck('verified').result }); });
  await page.goto('/'); await page.locator('input[type=file]').setInputFiles(file); await page.getByRole('button', { name: 'Analyze recording' }).click();
  await expect(page.getByRole('button', { name: 'Cancel check' })).toBeVisible(); await page.getByRole('button', { name: 'Cancel check' }).click();
  await expect(page.locator('.chosen-file')).toBeVisible(); await expect.poll(() => Boolean(release)).toBe(true); release!();
  await page.getByRole('navigation', { name: 'Main' }).getByRole('link', { name: 'Reports' }).click(); await expect(page.locator('.report-list-item')).toHaveCount(0);
});

test('invalid input and denied microphone permissions have clear recovery', async ({ page }) => {
  await offline(page); await page.addInitScript(() => { navigator.mediaDevices.getUserMedia = async () => { throw new DOMException('Denied', 'NotAllowedError'); }; });
  await page.goto('/'); await page.locator('input[type=file]').setInputFiles({ name: 'empty.wav', mimeType: 'audio/wav', buffer: Buffer.alloc(0) });
  await expect(page.getByRole('alert')).toContainText('empty'); await page.getByRole('button', { name: 'Record nearby' }).click(); await page.getByRole('button', { name: 'Start recording' }).click();
  await expect(page.getByRole('alert')).toContainText('permission was denied'); await page.getByRole('button', { name: 'Back to upload' }).click(); await expect(page.getByRole('button', { name: 'Upload recording' })).toBeVisible();
});

test('enrollment requires consent and service-confirmed voiceprints', async ({ page }) => {
  await offline(page); await page.route('**/api/persons', route => route.fulfill({ json: [] })); await page.route('**/api/enroll', route => route.fulfill({ status: 201, json: { ...person, voiceprints: [] } }));
  await page.goto('/voices'); await page.getByRole('button', { name: 'Enroll a voice', exact: true }).click(); await expect(page.getByRole('dialog')).toBeVisible();
  await page.getByLabel('Name', { exact: true }).fill(person.name); await page.locator('input[type=file]').setInputFiles(file);
  await expect(page.getByRole('button', { name: 'Save voiceprint' })).toBeDisabled(); await page.getByRole('checkbox').check(); await page.getByRole('button', { name: 'Save voiceprint' }).click();
  await expect(page.getByRole('alert')).toContainText('did not confirm'); await page.route('**/api/enroll', route => route.fulfill({ status: 201, json: person })); await page.getByRole('button', { name: 'Save voiceprint' }).click();
  await expect(page.getByRole('dialog')).toHaveCount(0); await expect(page.locator('.voice-card')).toContainText(person.name); await expect(page.locator('.voice-avatar')).toHaveText('कि');
});

test('failed voice removal retains the entry and can be retried', async ({ page }) => {
  await offline(page); await page.route('**/api/persons', route => route.fulfill({ json: [person] })); await page.goto('/voices');
  await page.getByRole('button', { name: `Remove ${person.name}` }).click(); await page.getByRole('button', { name: 'Remove voice', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Service unavailable'); await expect(page.locator('.voice-card')).toHaveCount(1);
  await page.route('**/api/persons/p1', route => route.fulfill({ status: 204, body: '' })); await page.getByRole('button', { name: 'Remove voice', exact: true }).click(); await expect(page.locator('.voice-card')).toHaveCount(0);
});

test('report retrieval rejects malformed or mismatched sessions', async ({ page }) => {
  await offline(page); await page.route('**/api/screen/test', route => route.fulfill({ json: { fusion: null } })); await page.goto('/reports/test'); await expect(page.getByRole('alert')).toContainText('incomplete evidence');
  await page.route('**/api/screen/test', route => route.fulfill({ json: sampleCheck('verified').result })); await page.getByRole('button', { name: 'Try again' }).click(); await expect(page.getByRole('alert')).toContainText('different report');
});

test('keyboard signal tabs, modal focus and reduced motion remain usable', async ({ page }) => {
  await offline(page); await page.route('**/api/persons', route => route.fulfill({ json: [] })); await page.goto('/');
  const tab = page.getByRole('tab', { name: /Identity/ }); await tab.focus(); await page.keyboard.press('ArrowRight'); await expect(page.getByRole('tab', { name: /Authenticity/ })).toBeFocused();
  await expect(page.getByRole('tabpanel')).toContainText('halfway through a call');
  expect(await page.locator('.sculpture-object').evaluate(el => getComputedStyle(el).transform)).toBe('none');
  await page.goto('/voices'); const enroll = page.getByRole('button', { name: 'Enroll a voice', exact: true }); await enroll.click(); await expect(page.getByLabel('Name', { exact: true })).toBeFocused(); await page.keyboard.press('Escape'); await expect(page.getByRole('dialog')).toHaveCount(0); await expect(enroll).toBeFocused();
});

test('sample exports stay labelled and printing exposes all evidence tabs', async ({ page }) => {
  await offline(page); await sample(page,'high_risk'); const pending = page.waitForEvent('download'); await page.getByRole('button', { name: 'JSON', exact: true }).click(); const download = await pending; expect(download.suggestedFilename()).toMatch(/satyacheck-sample_/);
  await page.emulateMedia({ media: 'print' }); await expect(page.locator('#report-transcript')).toBeVisible(); await expect(page.locator('#report-references')).toBeVisible(); await expect(page.locator('.site-header')).toBeHidden();
});

test('responsive routes, long names, artwork and visual captures', async ({ page }) => {
  test.setTimeout(90000); await offline(page); await page.route('**/api/persons', route => route.fulfill({ json: [person, { ...person, person_id: 'p2', name: 'Aleksandra Wiśniewska-Kowalczyk Montgomery' }] }));
  const errors: string[] = []; page.on('pageerror', error => errors.push(error.message)); await mkdir('design/review', { recursive: true });
  for (const width of [1440,768,390,320]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of ['/','/voices','/reports','/guide']) {
      await page.goto(route); await page.evaluate(() => document.fonts.ready); await expect(page.locator('h1')).toBeVisible();
      if (route === '/') { await expect(page.locator('.sculpture-object img')).toBeVisible(); expect(await page.locator('.sculpture-object img').evaluate(img => (img as HTMLImageElement).naturalWidth)).toBeGreaterThan(0); }
      await noOverflow(page); if (width === 1440 || width === 390) await page.screenshot({ path: `design/review/${width}-${route === '/' ? 'home' : route.slice(1)}.png`, fullPage: true });
    }
    await sample(page,'high_risk'); await noOverflow(page); if (width === 1440 || width === 390) await page.screenshot({ path: `design/review/${width}-evidence.png`, fullPage: true });
    await page.goto('/voices'); await page.getByRole('button', { name: 'Enroll a voice', exact: true }).click(); await noOverflow(page); await expect(page.getByLabel('Name', { exact: true })).toBeVisible();
    if (width === 1440 || width === 390) await page.screenshot({ path: `design/review/${width}-enroll.png` });
  }
  expect(errors).toEqual([]);
});


test('silent microphone data is rejected and capture tracks are released', async ({ page }) => {
  await offline(page);
  await page.addInitScript(() => {
    AnalyserNode.prototype.getFloatTimeDomainData = function(array) { array.fill(0); };
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async constraints => {
      const stream = await original(constraints);
      Object.assign(window, { captureTracks: stream.getTracks() });
      return stream;
    };
  });
  await page.goto('/'); await page.getByRole('button', { name: 'Record nearby' }).click();
  await page.getByRole('button', { name: 'Start recording' }).click();
  await expect(page.getByRole('button', { name: 'Stop and use recording' })).toBeEnabled();
  await page.waitForTimeout(400);
  await page.getByRole('button', { name: 'Stop and use recording' }).click();
  await expect(page.getByRole('alert')).toContainText('No audible speech');
  await expect(page.locator('.chosen-audio')).toHaveCount(0);
  expect(await page.evaluate(() => (window as unknown as { captureTracks: MediaStreamTrack[] }).captureTracks.every(track => track.readyState === 'ended'))).toBe(true);
});
