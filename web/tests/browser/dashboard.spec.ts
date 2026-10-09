import { test, expect, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { getMockFixture, type MockScenario } from '../../src/api/mock';

const review = resolve('.impeccable/review');
const examples: [MockScenario, string][] = [
  ['green', 'Verified voice'], ['caution', 'Caution'], ['suspicious', 'Suspicious signals'],
  ['red', 'High risk signals'], ['unverified', 'Unverified caller'], ['insufficient', 'Insufficient audio'],
];

async function offline(page: Page) {
  await page.route('http://127.0.0.1:5173/api/**', route => route.fulfill({ status: 503, json: { detail: 'Screening service is unavailable.' } }));
}

async function sample(page: Page, name: string) {
  await page.goto('/');
  await page.getByText('Explore sample results', { exact: true }).click();
  await page.getByRole('button', { name, exact: true }).click();
  await expect(page.getByText('Sample result. This is a demonstration and does not describe your recording.')).toBeVisible();
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 1)).toBe(true);
}

test('all six labelled results preserve scoring rules and report navigation', async ({ page }) => {
  await offline(page);
  for (const [scenario, label] of examples) {
    await sample(page, label);
    const score = page.locator('.trust-readout');
    if (scenario === 'insufficient') {
      await expect(score).toContainText('Not reported');
      await expect(score).not.toContainText('/100');
      await expect(page.locator('.results-table:not(.compact)')).toHaveCount(0);
    } else {
      await expect(score).toContainText('/100');
      await expect(page.locator('.results-table:not(.compact) tbody tr')).toHaveCount(3);
    }
    if (scenario === 'unverified') await expect(page.locator('.interpretation')).toHaveClass(/tone-neutral/);
    if (scenario === 'red') await expect(page.locator('.transcript mark.concern').first()).toBeVisible();
    await page.getByRole('link', { name: 'Open in reports' }).click();
    await expect(page.getByText('Sample report. Demonstration data, not evidence of a real incident.')).toBeVisible();
    await expect(page.getByRole('heading', { name: 'Screening report' })).toBeVisible();
  }
});

test('real request failure leaves audio available and produces no verdict', async ({ page }) => {
  await offline(page);
  await page.goto('/');
  await page.locator('input[type=file]').setInputFiles({ name: 'test.wav', mimeType: 'audio/wav', buffer: Buffer.from('synthetic test bytes') });
  await expect(page.getByRole('button', { name: 'Check audio', exact: true })).toBeEnabled();
  await page.getByRole('button', { name: 'Check audio', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('Screening service is unavailable.');
  await expect(page.locator('.report-sheet')).toHaveCount(0);
  await expect(page.locator('audio')).toHaveAttribute('src', /^blob:/);
});

test('enrollment requires consent and rejects a success response without voiceprints', async ({ page }) => {
  await offline(page);
  await page.route('**/api/persons', route => route.fulfill({ json: [] }));
  await page.route('**/api/enroll', route => route.fulfill({ status: 201, json: { person_id: 'test-person', name: 'आरव', voiceprints: [] } }));
  await page.goto('/enroll');
  await page.getByLabel('Name', { exact: true }).fill('आरव');
  await page.locator('input[type=file]').setInputFiles({ name: 'enroll.wav', mimeType: 'audio/wav', buffer: Buffer.from('synthetic test bytes') });
  await expect(page.getByRole('button', { name: 'Enroll voice', exact: true })).toBeDisabled();
  await page.getByRole('checkbox').check();
  await page.getByRole('button', { name: 'Enroll voice', exact: true }).click();
  await expect(page.getByRole('alert')).toContainText('did not confirm a saved voiceprint');
  await expect(page.getByText('आरव’s voice was enrolled successfully.')).toHaveCount(0);
});

test('removing a known voice asks for confirmation and calls the service', async ({ page }) => {
  await offline(page);
  const person = { person_id: 'p_asha', name: 'Asha', relation: 'Mother', phone_number: null, avatar_url: null, created_at: '2026-10-01T10:00:00Z', voiceprints: [{ voiceprint_id: 'v1', duration_s: 31 }] };
  let deleted = '';
  await page.route('**/api/persons', route => route.fulfill({ json: [person] }));
  await page.route('**/api/persons/p_asha', route => { deleted = route.request().method(); return route.fulfill({ json: { deleted: 'p_asha' } }); });
  await page.goto('/enroll');
  await page.getByRole('button', { name: 'Remove Asha' }).click();
  await expect(page.getByText('Remove Asha?')).toBeVisible();
  await page.getByRole('button', { name: 'Keep' }).click();
  expect(deleted).toBe('');
  await page.getByRole('button', { name: 'Remove Asha' }).click();
  await page.getByRole('button', { name: 'Remove', exact: true }).click();
  await expect(page.getByText('Asha was removed.')).toBeVisible();
  expect(deleted).toBe('DELETE');
  await expect(page.getByText('No one enrolled yet')).toBeVisible();
});

test('live listening streams WAV slices and finalises a provisional report', async ({ page }) => {
  await offline(page);
  const chunks: { index: number; final: boolean; header: string }[] = [];
  await page.routeWebSocket('**/api/ws/screen/*', ws => {
    ws.onMessage(raw => {
      const message = JSON.parse(String(raw));
      const header = Buffer.from(message.audio_base64, 'base64').subarray(0, 4).toString('ascii');
      chunks.push({ index: message.chunk_index, final: message.is_final, header });
      const response = { ...getMockFixture('caution'), session_id: message.session_id };
      ws.send(JSON.stringify({ type: 'screening_update', session_id: message.session_id, chunk_index: message.chunk_index, response }));
      if (message.is_final) ws.close();
    });
  });
  await page.goto('/');
  await page.getByRole('tab', { name: 'Listen live' }).click();
  await page.getByRole('button', { name: 'Start listening' }).click();
  await expect(page.getByText('Provisional · updating')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: 'Stop and finalise' }).click();
  await expect(page.locator('.sheet-status.final')).toBeVisible({ timeout: 10_000 });
  expect(chunks.length).toBeGreaterThanOrEqual(2);
  expect(chunks.every(chunk => chunk.header === 'RIFF')).toBe(true);
  expect(chunks.at(-1)?.final).toBe(true);
  await page.getByRole('link', { name: 'Reports', exact: true }).click();
  await expect(page.getByRole('link', { name: 'Live listening' })).toBeVisible();
});

test('saved report retrieval and malformed responses are distinct', async ({ page }) => {
  await offline(page);
  await page.route('**/api/screen/stored', route => route.fulfill({ json: { ...getMockFixture('red'), session_id: 'stored' } }));
  await page.goto('/report?session=stored');
  await expect(page.getByRole('heading', { name: 'Screening report' })).toBeVisible();
  await page.route('**/api/screen/broken', route => route.fulfill({ json: { session_id: 'broken' } }));
  await page.goto('/report?session=broken');
  await expect(page.getByRole('alert')).toContainText('incomplete result');
  await expect(page.getByRole('heading', { name: 'Screening report' })).toHaveCount(0);
});

test('source tabs support roving keyboard focus', async ({ page }) => {
  await offline(page);
  await page.goto('/');
  const recording = page.getByRole('tab', { name: 'Recording', exact: true });
  const live = page.getByRole('tab', { name: 'Listen live' });
  await recording.focus();
  await recording.press('ArrowRight');
  await expect(live).toBeFocused();
  await expect(live).toHaveAttribute('aria-selected', 'true');
  await expect(recording).toHaveAttribute('tabindex', '-1');
  await live.press('Home');
  await expect(recording).toBeFocused();
  await recording.press('End');
  await expect(live).toBeFocused();
});

test('the acoustic illustration settles and honors reduced motion', async ({ page }) => {
  await offline(page);
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto('/');
  const ribbon = page.locator('.acoustic-ribbon');
  await expect(ribbon).toBeVisible();
  await expect(ribbon).toHaveAttribute('aria-hidden', 'true');
  await expect.poll(() => ribbon.evaluate(element => element.getAnimations().every(animation => animation.playState === 'finished'))).toBe(true);
  await page.emulateMedia({ reducedMotion: 'reduce' });
  expect(await ribbon.evaluate(element => getComputedStyle(element).animationName)).toBe('none');
  await expect(page.getByRole('button', { name: 'Choose audio file', exact: true })).toBeVisible();
});

test('screening stays available without WebGL', async ({ page }) => {
  await offline(page);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.addInitScript(() => {
    const original = HTMLCanvasElement.prototype.getContext;
    Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', { value: function(type: string, ...args: unknown[]) {
      return type === 'webgl' ? null : Reflect.apply(original, this, [type, ...args]);
    } });
  });
  await page.goto('/');
  await expect(page.locator('.acoustic-ribbon')).toBeVisible();
  await expect(page.getByRole('button', { name: 'Choose audio file', exact: true })).toBeVisible();
  await page.getByRole('tab', { name: 'Recording', exact: true }).focus();
  await expect(page.getByRole('tab', { name: 'Recording', exact: true })).toBeFocused();
  expect(errors).toEqual([]);
});

for (const failure of ['disconnect', 'timeout'] as const) {
  test(`live ${failure} preserves an unfinished report`, async ({ page }) => {
    await offline(page);
    await page.routeWebSocket('**/api/ws/screen/*', ws => {
      ws.onMessage(raw => {
        const message = JSON.parse(String(raw));
        if (message.is_final) { if (failure === 'disconnect') ws.close(); return; }
        ws.send(JSON.stringify({ type: 'screening_update', session_id: message.session_id, chunk_index: message.chunk_index, response: { ...getMockFixture('caution'), session_id: message.session_id } }));
      });
    });
    await page.goto('/');
    await page.getByRole('tab', { name: 'Listen live' }).click();
    await page.getByRole('button', { name: 'Start listening' }).click();
    await expect(page.getByText('Provisional · updating')).toBeVisible({ timeout: 10_000 });
    if (failure === 'timeout') await page.clock.install();
    await page.getByRole('button', { name: 'Stop and finalise' }).click();
    if (failure === 'timeout') await page.clock.fastForward(45_001);
    await expect(page.getByRole('alert')).toContainText('did not confirm the final audio slice');
    await expect(page.getByText('Provisional · interrupted')).toBeVisible();
    await expect(page.locator('.sheet-status.final')).toHaveCount(0);
    await page.getByRole('link', { name: 'Reports', exact: true }).click();
    await expect(page.getByText('A report starts with a check')).toBeVisible();
  });
}

test('nested malformed evidence is recoverable without a render crash', async ({ page }) => {
  await offline(page);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  await page.route('**/api/screen/nested', route => route.fulfill({ json: { ...getMockFixture('red'), fusion: { ...getMockFixture('red').fusion, weights_used: null } } }));
  await page.goto('/report?session=nested');
  await expect(page.getByRole('alert')).toContainText('incomplete result');
  await expect(page.getByRole('button', { name: 'Try again' })).toBeVisible();
  expect(errors).toEqual([]);
});

test('a response from another session cannot acknowledge final audio', async ({ page }) => {
  await offline(page);
  await page.routeWebSocket('**/api/ws/screen/*', ws => {
    ws.onMessage(raw => {
      const message = JSON.parse(String(raw));
      const session = message.is_final ? 'another-session' : message.session_id;
      ws.send(JSON.stringify({ type: 'screening_update', session_id: session, chunk_index: message.chunk_index, response: { ...getMockFixture('caution'), session_id: session } }));
      if (message.is_final) ws.close();
    });
  });
  await page.goto('/');
  await page.getByRole('tab', { name: 'Listen live' }).click();
  await page.getByRole('button', { name: 'Start listening' }).click();
  await expect(page.getByText('Provisional · updating')).toBeVisible({ timeout: 10_000 });
  await page.getByRole('button', { name: 'Stop and finalise' }).click();
  await expect(page.getByRole('alert')).toContainText('did not confirm the final audio slice');
  await expect(page.locator('.sheet-status.final')).toHaveCount(0);
});

test('a socket closed during microphone setup cannot start listening', async ({ page }) => {
  await offline(page);
  await page.addInitScript(() => {
    const original = navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
    navigator.mediaDevices.getUserMedia = async constraints => {
      const media = await original(constraints);
      const state = window as typeof window & { releaseMicrophone?: () => void; lateMedia?: MediaStream };
      state.lateMedia = media;
      await new Promise<void>(resolve => { state.releaseMicrophone = resolve; });
      return media;
    };
  });
  let connection: { close: () => void } | undefined;
  await page.routeWebSocket('**/api/ws/screen/*', ws => { connection = ws; });
  await page.goto('/');
  await page.getByRole('tab', { name: 'Listen live' }).click();
  await page.getByRole('button', { name: 'Start listening' }).click();
  await page.waitForFunction(() => Boolean((window as typeof window & { releaseMicrophone?: () => void }).releaseMicrophone));
  connection!.close();
  await expect(page.getByRole('alert')).toContainText('connection to the screening service closed');
  await page.evaluate(() => (window as typeof window & { releaseMicrophone?: () => void }).releaseMicrophone?.());
  await expect.poll(() => page.evaluate(() => (window as typeof window & { lateMedia?: MediaStream }).lateMedia?.getTracks().every(track => track.readyState === 'ended'))).toBe(true);
  await expect(page.getByRole('button', { name: 'Start listening' })).toBeVisible();
  await expect(page.getByRole('button', { name: 'Stop and finalise' })).toHaveCount(0);
});

test('authority references remain neutral and dark-mode print uses legible semantic colors', async ({ page }) => {
  await offline(page);
  await sample(page, 'Unverified caller');
  await expect(page.locator('.trust-readout .range-zone.tone-success')).toHaveCount(0);
  await page.getByRole('button', { name: 'Switch to dark theme' }).click();
  await page.emulateMedia({ media: 'print' });
  const colors = await page.locator('html').evaluate(element => {
    const style = getComputedStyle(element);
    return ['--neutral-ink', '--success-ink', '--danger-ink'].map(token => style.getPropertyValue(token).trim());
  });
  expect(colors).toEqual(['#404659', '#095432', '#8b2017']);
});

test('small screens and long filenames remain usable across routes', async ({ page }) => {
  await offline(page);
  for (const width of [320, 390, 768]) {
    await page.setViewportSize({ width, height: 900 });
    for (const route of ['/', '/enroll', '/report', '/help']) {
      await page.goto(route);
      const wide = await page.evaluate(() => [...document.querySelectorAll('body *')].filter(e => !e.matches('.range-position, .strip-position') && e.getBoundingClientRect().right > window.innerWidth + 1).slice(0, 5).map(e => `${e.tagName}.${e.className}`));
      expect(wide, `${route} at ${width}px`).toEqual([]);
      await noOverflow(page);
    }
    await page.goto('/');
    await page.locator('input[type=file]').setInputFiles({ name: 'very-long-recording-name-'.repeat(12) + '.wav', mimeType: 'audio/wav', buffer: Buffer.from('test') });
    await noOverflow(page);
    await sample(page, 'High risk signals');
    // Transform carriers are intentionally wider than the visible measurement.
    // Their parent clips them; check visible children and real document overflow.
    const wide = await page.evaluate(() => [...document.querySelectorAll('body *')].filter(e => !e.matches('.range-position, .strip-position') && e.getBoundingClientRect().right > window.innerWidth + 1).slice(0, 5).map(e => `${e.tagName}.${e.className}`));
    expect(wide, `result at ${width}px`).toEqual([]);
    await noOverflow(page);
    await page.getByRole('link', { name: 'Open in reports' }).click(); await noOverflow(page);
  }
});

test('desktop and mobile light/dark visual evidence has no runtime exceptions', async ({ page }) => {
  test.setTimeout(60_000);
  const exceptions: string[] = [];
  page.on('pageerror', error => exceptions.push(error.message));
  await mkdir(review, { recursive: true });
  await offline(page);
  for (const [label, width, height] of [['desktop', 1440, 1000], ['mobile', 390, 844]] as const) {
    await page.setViewportSize({ width, height });
    await page.emulateMedia({ colorScheme: 'light' });
    await page.goto('/');
    await expect(page.getByRole('button', { name: 'Choose audio file', exact: true })).toBeVisible();
    await page.screenshot({ path: resolve(review, `${label}.png`), fullPage: true });
    await page.getByRole('button', { name: 'Switch to dark theme' }).click();
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'dark');
    await page.screenshot({ path: resolve(review, `${label}-dark.png`), fullPage: true });
    await sample(page, 'High risk signals');
    await expect(page.locator('html')).toHaveAttribute('data-theme', 'light');
    await page.evaluate(() => window.scrollTo(0, 0));
    await page.screenshot({ path: resolve(review, `${label}-result.png`), fullPage: true });
    await page.getByRole('button', { name: 'Switch to dark theme' }).click();
    await page.screenshot({ path: resolve(review, `${label}-result-dark.png`), fullPage: true });
    await page.getByRole('button', { name: 'Switch to light theme' }).click();
    await page.getByRole('link', { name: 'Open in reports' }).click();
    await expect(page.getByRole('heading', { name: 'Screening report' })).toBeVisible();
    await page.screenshot({ path: resolve(review, `${label}-report.png`), fullPage: true });
    await page.goto('/enroll');
    await expect(page.getByRole('heading', { name: 'Known voices', level: 1 })).toBeVisible();
    await expect(page.getByRole('status', { name: 'Loading known voices' })).toHaveCount(0);
    await page.screenshot({ path: resolve(review, `${label}-enroll.png`), fullPage: true });
  }
  expect(exceptions).toEqual([]);
});
