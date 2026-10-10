import { test } from 'node:test';
import assert from 'node:assert/strict';
import { getMockFixture } from '../src/api/mock.ts';
import { apiUrl, audioError, checkHealth, deletePerson, enroll, listScreenings, parseScreening, request, screenFile } from '../src/lib/api.ts';
import { toInt16 } from '../src/hooks/useLiveSession.ts';
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

test('the API defaults to same-origin paths so the dev proxy carries them', () => {
  assert.equal(apiUrl('/api/health'), '/api/health');
});

test('enrollment sends consent and still requires a confirmed voiceprint', async () => {
  const original = globalThis.fetch;
  let sent: FormData | null = null;
  try {
    globalThis.fetch = async (_url, init) => {
      sent = init?.body as FormData;
      return new Response(JSON.stringify({ person_id: 'p1', name: 'Asha', voiceprints: [{ voiceprint_id: 'v1', duration_s: 20 }] }), { status: 201 });
    };
    const file = new File([new Uint8Array(10)], 'a.wav', { type: 'audio/wav' });
    await enroll({ name: 'Asha', relation: 'Mother', file, consent: true }, new AbortController().signal);
    assert.equal(sent!.get('consent'), 'true');

    globalThis.fetch = async () => new Response(JSON.stringify({ person_id: 'p1', name: 'Asha', voiceprints: [] }), { status: 201 });
    await assert.rejects(enroll({ name: 'Asha', relation: 'Mother', file, consent: true }, new AbortController().signal), /did not confirm a saved voiceprint/);
  } finally {
    globalThis.fetch = original;
  }
});

test('delete reports whether the stored voiceprint was removed', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ deleted: 'p1', voiceprint_deleted: false }), { status: 200 });
    assert.deepEqual(await deletePerson('p1'), { voiceprintDeleted: false });
    globalThis.fetch = async () => new Response(JSON.stringify({ deleted: 'p1' }), { status: 200 });
    assert.deepEqual(await deletePerson('p1'), { voiceprintDeleted: null });
  } finally {
    globalThis.fetch = original;
  }
});

test('health reports when intent runs on keyword markers only', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response(JSON.stringify({ status: 'ok', nlp_retrieval_available: false, nlp_retrieval_reason: 'index missing', use_real_spoof: true }), { status: 200 });
    const health = await checkHealth(new AbortController().signal);
    assert.equal(health.status, 'online');
    assert.equal(health.retrievalAvailable, false);
    assert.equal(health.retrievalReason, 'index missing');
    globalThis.fetch = async () => { throw new TypeError('offline'); };
    assert.equal((await checkHealth(new AbortController().signal)).status, 'offline');
  } finally {
    globalThis.fetch = original;
  }
});

test('live frames go out as clipped little-endian int16', () => {
  const pcm = new Int16Array(toInt16(new Float32Array([0, 0.5, -0.5, 1, -1, 2, -2])));
  assert.deepEqual(Array.from(pcm), [0, 16383, -16384, 32767, -32768, 32767, -32768]);
});

test('enrollment sends extra numbers and aliases, skipping blanks', async () => {
  const original = globalThis.fetch;
  let sent: FormData | null = null;
  try {
    globalThis.fetch = async (_url, init) => {
      sent = init?.body as FormData;
      return new Response(JSON.stringify({ person_id: 'p1', name: 'Asha', voiceprints: [{ voiceprint_id: 'v1', duration_s: 20 }] }), { status: 201 });
    };
    const file = new File([new Uint8Array(10)], 'a.wav', { type: 'audio/wav' });
    await enroll({ name: 'Asha', relation: 'Mother', file, consent: true, phoneNumbers: ['+919800000001', ' '], aliases: ['Mummy', ' Maa '] }, new AbortController().signal);
    assert.deepEqual(sent!.getAll('phone_numbers'), ['+919800000001']);
    assert.deepEqual(sent!.getAll('aliases'), ['Mummy', 'Maa']);
  } finally {
    globalThis.fetch = original;
  }
});

test('a claimed caller is sent with the upload, and only when chosen', async () => {
  const original = globalThis.fetch;
  const bodies: FormData[] = [];
  try {
    globalThis.fetch = async (_url, init) => {
      bodies.push(init?.body as FormData);
      return new Response('{}', { status: 200 });
    };
    const file = new File([new Uint8Array(10)], 'a.wav', { type: 'audio/wav' });
    await assert.rejects(screenFile(file, new AbortController().signal, 'p1'), /incomplete result/);
    await assert.rejects(screenFile(file, new AbortController().signal), /incomplete result/);
    assert.equal(bodies[0].get('claimed_identity'), 'p1');
    assert.equal(bodies[1].get('claimed_identity'), null);
  } finally {
    globalThis.fetch = original;
  }
});

test('the reports list pages with the server cursor and rejects a malformed reply', async () => {
  const original = globalThis.fetch;
  const urls: string[] = [];
  try {
    globalThis.fetch = async url => {
      urls.push(String(url));
      return new Response(JSON.stringify({ items: [{ session_id: 's1', created_at: '2026-10-10', status: 'complete', channel_type: 'upload', band: 'caution', trust_score: 51 }], next_cursor: 'abc' }), { status: 200 });
    };
    const page = await listScreenings('xyz', 5);
    assert.equal(page.items[0].session_id, 's1');
    assert.equal(page.nextCursor, 'abc');
    assert.match(urls[0], /\/api\/screen\?limit=5&cursor=xyz$/);

    globalThis.fetch = async () => new Response(JSON.stringify({ rows: [] }), { status: 200 });
    await assert.rejects(listScreenings(), /could not be read/);
  } finally {
    globalThis.fetch = original;
  }
});

test('a 401 is reported as an expired sign-in, not a generic failure', async () => {
  const original = globalThis.fetch;
  try {
    globalThis.fetch = async () => new Response('{}', { status: 401 });
    await assert.rejects(request('/api/persons'), /sign-in has expired/);
  } finally {
    globalThis.fetch = original;
  }
});
