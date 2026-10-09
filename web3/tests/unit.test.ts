import { test } from 'node:test';
import assert from 'node:assert/strict';
import { getMockFixture } from '../src/api/mock.ts';
import { audioError, parseScreening, request } from '../src/lib/api.ts';
import { encodeWav, peaks, resample } from '../src/lib/audio.ts';
import { calm, displayBand, measurements, trustIntervals, markPhrases, reportText, safeLink, signals } from '../src/lib/verdict.ts';

test('unknown speakers and authority checks never display as verified', () => {
  const green = getMockFixture('green');
  assert.equal(displayBand(green), 'verified');
  assert.equal(displayBand({ ...green, speaker: { ...green.speaker, verdict: 'unknown' } }), 'unverified');
  assert.equal(displayBand({ ...green, fusion: { ...green.fusion, mode: 'authority_check' } }), 'unverified');
});

test('failed quality gate means no score, whatever the band says', () => {
  const red = getMockFixture('red');
  assert.equal(displayBand({ ...red, quality: { ...red.quality, passed: false } }), 'insufficient');
  assert.equal(displayBand(getMockFixture('insufficient')), 'insufficient');
});

test('identity abstains in authority mode and flags follow the evidence', () => {
  const ivr = signals(getMockFixture('unverified'));
  assert.equal(ivr[0].abstains, true);
  assert.equal(ivr[0].flag.mark, '—');
  const red = signals(getMockFixture('red'));
  // A voiceprint match on a synthetic voice is not trusted: never 'OK', never green.
  assert.deepEqual(red.map(s => s.flag.mark), ['—', 'H', 'H']);
  assert.equal(red[0].flag.label, 'Not trusted');
  assert.match(red[0].finding, /^Sounds like/);
  const green = signals(getMockFixture('green'));
  assert.equal(green[0].flag.mark, 'OK');
});

test('trust intervals tile 0–100, match the configured bands, and are never green unless verified', () => {
  const TRUST_INTERVALS = trustIntervals(true);
  assert.equal(trustIntervals(false).at(-1)!.tone, 'neutral');
  assert.equal(trustIntervals(false).some(z => z.tone === 'safe'), false);
  assert.equal(TRUST_INTERVALS[0].from, 0);
  assert.equal(TRUST_INTERVALS.at(-1)!.to, 100);
  for (let i = 1; i < TRUST_INTERVALS.length; i++) assert.equal(TRUST_INTERVALS[i].from, TRUST_INTERVALS[i - 1].to);
  // config.BAND_THRESHOLDS: risk 0.15 / 0.40 / 0.65  ->  trust 85 / 60 / 35
  assert.deepEqual(TRUST_INTERVALS.slice(1).map(z => z.from), [35, 60, 85]);
});

test('marker phrases are found case-insensitively without overlap', () => {
  const red = getMockFixture('red');
  const runs = markPhrases(red.transcript.text, red);
  assert.equal(runs.map(r => r.text).join(''), red.transcript.text);
  assert.equal(runs.filter(r => r.kind === 'concern').length, 2);
});

test('malformed service replies never become verdicts', () => {
  for (const body of [null, {}, { session_id: 'x' }, { ...getMockFixture('red'), fusion: {} }]) {
    assert.throws(() => parseScreening(body), /incomplete/);
  }
  assert.equal(parseScreening(getMockFixture('red')).session_id, 'session_mock_red');
});

test('files are validated before upload', () => {
  assert.match(audioError(new File([], 'a.wav'))!, /empty/);
  assert.match(audioError(new File(['x'], 'notes.txt', { type: 'text/plain' }))!, /supported/);
  assert.equal(audioError(new File(['x'], 'call.amr')), null);
});

test('service errors keep the server explanation', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'Need more speech.' }), { status: 422 });
    await assert.rejects(request('/api/screen'), /Need more speech/);
    globalThis.fetch = async () => { throw new TypeError('offline'); };
    await assert.rejects(request('/api/screen'), /Cannot reach/);
  } finally {
    globalThis.fetch = original;
  }
});

test('live slices are valid 16 kHz mono PCM WAV files', () => {
  const wav = encodeWav(resample(new Float32Array(48_000).fill(0.25), 48_000, 16_000), 16_000);
  const view = new DataView(wav.buffer);
  assert.equal(new TextDecoder().decode(wav.subarray(0, 4)), 'RIFF');
  assert.equal(view.getUint32(24, true), 16_000);
  assert.equal(view.getUint16(22, true), 1);
  assert.equal(view.getUint32(40, true), 16_000 * 2);
});

test('waveform peaks are normalised to the loudest sample', () => {
  const p = peaks(Float32Array.from([0, 0.5, -0.25, 0.1]), 2);
  assert.equal(Math.max(...p), 1);
});

test('links and summaries stay safe and honest', () => {
  assert.equal(safeLink('javascript:alert(1)'), undefined);
  assert.equal(safeLink('https://cybercrime.gov.in/x'), 'https://cybercrime.gov.in/x');
  const sample = reportText(getMockFixture('red'), true);
  assert.match(sample, /^SAMPLE/);
  assert.match(sample, /not an official complaint or a determination of fraud/);
  assert.match(reportText(getMockFixture('insufficient'), false), /not given/);
});

test('synthetic measures carry references and flags, and shouting templates are calmed', () => {
  const rows = measurements(getMockFixture('red'));
  assert.deepEqual(rows.slice(2).map(r => [r.value, r.flag.mark]), [['86%', 'H'], ['98%', 'H'], ['6.5 s', 'H']]);
  assert.equal(calm('DO NOT transfer money via UPI.'), 'Do not transfer money via UPI.');
});
