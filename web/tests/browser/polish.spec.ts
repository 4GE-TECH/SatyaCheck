import { expect, test, type Page } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import { resolve } from 'node:path';
import { getMockFixture } from '../../src/api/mock';

const people = [
  { person_id: 'p_1', name: 'Aleksandra Wiśniewska-Kowalczyk Montgomery', relation: 'Family friend and emergency contact', phone_number: '+91 98765 43210', avatar_url: null, created_at: '2026-10-01T10:00:00Z', voiceprints: [{ voiceprint_id: 'v1', duration_s: 31 }] },
  { person_id: 'p_2', name: 'किरण चन्द्रशेखर विश्वनाथन श्रीवास्तव', relation: 'परिवार के सदस्य और आपातकालीन संपर्क', phone_number: null, avatar_url: null, created_at: '2026-10-01T10:00:00Z', voiceprints: [] },
  { person_id: 'p_3', name: '👩🏽‍⚕️ Dr Élodie', relation: '', phone_number: null, avatar_url: null, created_at: '', voiceprints: [{ voiceprint_id: 'v3', duration_s: 29 }] },
  { person_id: 'p_4', name: 'J', relation: 'Friend', phone_number: null, avatar_url: null, created_at: '', voiceprints: [] },
];

async function fixtures(page: Page) {
  await page.route('http://127.0.0.1:5173/api/**', route => route.fulfill({ status: 503, json: { detail: 'Service unavailable.' } }));
  await page.route('**/api/persons', route => route.fulfill({ json: people }));
}

async function noOverflow(page: Page) {
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1)).toBe(true);
}

test('known voices preserve complete names and graphemes at narrow widths', async ({ page }) => {
  await fixtures(page);
  for (const width of [320, 390, 768, 1440]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/enroll');
    await expect(page.locator('.people-list li')).toHaveCount(4);
    await expect(page.locator('.avatar').nth(1)).toHaveText('कि');
    await expect(page.locator('.avatar').nth(2)).toHaveText('👩🏽‍⚕️');
    const hiddenNames = await page.locator('.person-name').evaluateAll(names => names.filter(name => name.scrollWidth > name.clientWidth + 1).map(name => name.textContent));
    expect(hiddenNames).toEqual([]);
    await noOverflow(page);
  }
});

test('removing a voice locks conflicting actions and retains a failed removal', async ({ page }) => {
  await fixtures(page);
  let finish: (() => void) | undefined;
  await page.route('**/api/persons/p_1', async route => {
    await new Promise<void>(resolve => { finish = resolve; });
    await route.fulfill({ status: 503, json: { detail: 'Could not remove the voice. Try again.' } });
  });
  await page.goto('/enroll');
  await page.getByRole('button', { name: `Remove ${people[0].name}`, exact: true }).click();
  await page.getByRole('button', { name: 'Remove', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Refresh known voices' })).toBeDisabled();
  await expect(page.getByLabel('Name', { exact: true })).toBeDisabled();
  for (const button of await page.getByRole('button', { name: 'Re-record', exact: true }).all()) await expect(button).toBeDisabled();
  await expect.poll(() => Boolean(finish)).toBe(true);
  finish!();
  await expect(page.getByRole('alert')).toContainText('Could not remove the voice');
  await expect(page.locator('.people-list li')).toHaveCount(4);
  await expect(page.getByRole('button', { name: 'Remove', exact: true })).toBeEnabled();
  await expect(page.getByLabel('Name', { exact: true })).toBeEnabled();
});

test('compact controls, inputs and enlarged text remain usable across routes', async ({ page }) => {
  await fixtures(page);
  for (const width of [390, 768]) {
    await page.setViewportSize({ width, height: 1000 });
    for (const route of ['/', '/enroll', '/report', '/help']) {
      await page.goto(route);
      await expect(page.locator('main')).toBeVisible();
      const small = await page.locator('button:visible').evaluateAll(buttons => buttons.filter(button => button.getBoundingClientRect().height < 43.9).map(button => button.getAttribute('aria-label') || button.textContent));
      expect(small, route).toEqual([]);
      const smallInputs = await page.locator('input:not([type=file]):not([type=checkbox])').evaluateAll(inputs => inputs.filter(input => parseFloat(getComputedStyle(input).fontSize) < 16).map(input => input.id));
      expect(smallInputs, route).toEqual([]);
      await page.evaluate(() => document.documentElement.style.fontSize = '200%');
      await noOverflow(page);
      const overlap = await page.locator('.letterhead-inner').evaluate(header => {
        const nav = header.querySelector('nav')!.getBoundingClientRect();
        const actions = header.querySelector('.letterhead-actions')!.getBoundingClientRect();
        const lastLink = header.querySelector('nav a:last-child')!.getBoundingClientRect();
        return nav.top < actions.bottom && nav.bottom > actions.top && lastLink.right > actions.left;
      });
      expect(overlap, `${route} at ${width}px with enlarged text`).toBe(false);
      expect(await page.locator('.skip-link').evaluate(link => link.getBoundingClientRect().bottom)).toBeLessThan(0);
      await page.evaluate(() => document.documentElement.style.fontSize = '');
    }
  }
});

test('mobile navigation remains reachable and moves between real routes', async ({ page }) => {
  await fixtures(page);
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto('/');
  const nav = page.getByRole('navigation', { name: 'Main' });
  await page.evaluate(() => scrollTo(0, document.body.scrollHeight));
  const box = await nav.boundingBox();
  expect(box!.y + box!.height).toBeLessThanOrEqual(844);
  await nav.getByRole('link', { name: 'Known voices' }).click();
  await expect(page.getByRole('heading', { name: 'Known voices', exact: true })).toBeVisible();
  await expect(nav.getByRole('link', { name: 'Known voices' })).toHaveAttribute('aria-current', 'page');
  await nav.getByRole('link', { name: 'Reports', exact: true }).click();
  await expect(page.getByText('A report starts with a check')).toBeVisible();
  await noOverflow(page);
});

test('evidence transforms retain measured positions and long reports remain legible', async ({ page }) => {
  await fixtures(page);
  const data = getMockFixture('red');
  data.fusion.reason_codes[0].value = 'Peak synthesis observed in EmergencyVerificationRecording_20261009_184500_family_callback.wav';
  data.fusion.reason_codes[0].threshold = 'Supplied reference for comparison: independent callback to the enrolled family contact';
  data.transcript.text = 'कृपया अपने परिवार के परिचित नंबर पर बात करके इस अनुरोध की पुष्टि करें। '.repeat(14);
  data.fusion.challenge_question = { ...data.fusion.challenge_question!, question_text: 'What was the name of the hospital where we met your grandmother last week?' };
  await page.route('**/api/screen/long-report', route => route.fulfill({ json: { ...data, session_id: 'long-report' } }));
  await mkdir(resolve('.impeccable/review'), { recursive: true });
  for (const [label, width] of [['polish-mobile', 390], ['polish-desktop', 1440]] as const) {
    await page.setViewportSize({ width, height: 1000 });
    await page.goto('/report?session=long-report');
    await expect(page.getByRole('heading', { name: 'Screening report' })).toBeVisible();
    await noOverflow(page);
    const splitActions = await page.locator('.advisories .text-link').evaluateAll(links => links.filter(link => getComputedStyle(link).whiteSpace !== 'nowrap' || link.scrollWidth > link.clientWidth + 1).map(link => link.textContent));
    expect(splitActions).toEqual([]);
    const geometry = await page.locator('.trust-readout .range-track').evaluate(track => {
      const bounds = track.getBoundingClientRect();
      const tick = track.querySelector('.range-tick')!.getBoundingClientRect();
      return ((tick.left + tick.width / 2 - bounds.left) / bounds.width) * 100;
    });
    expect(geometry).toBeCloseTo(data.fusion.trust_score, 1);
    const bar = await page.locator('.strip-bar').first().evaluate(element => ({ height: element.getBoundingClientRect().height, total: element.parentElement!.clientHeight, transition: getComputedStyle(element).transitionProperty }));
    expect(bar.height / bar.total).toBeCloseTo(Math.max(.04, data.spoof.timeline[0].score), 2);
    expect(bar.transition).toBe('transform');
    await page.screenshot({ path: resolve('.impeccable/review', `${label}-long-report.png`), fullPage: true });
    await page.goto('/enroll');
    await expect(page.locator('.people-list li')).toHaveCount(4);
    await page.screenshot({ path: resolve('.impeccable/review', `${label}-voices.png`), fullPage: true });
  }
});
