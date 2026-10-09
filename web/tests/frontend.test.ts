import { test } from 'node:test';
import assert from 'node:assert/strict';
import { displayBand, safeLink, number, reportIntervals, signalRows } from '../src/lib/presentation.ts';
import { audioError, parseScreening, request } from '../src/api/client.ts';
import { initial } from '../src/lib/initial.ts';
const fixture = (mode = 'identity_check', verdict = 'match', passed = true) => ({
 session_id: 'test', timestamp: '2026-10-08T10:00:00Z', processing_time_ms: 10,
 quality: { passed, speech_duration_s: 8, snr_db: 20, min_speech_threshold_s: 1.5, min_snr_threshold_db: 5 }, speaker: { verdict, is_replay: false },
 fusion: { mode, band: 'verified', trust_score: 90, reason_codes: [], recommended_actions: [], weights_used: { asv_weight: 0.4, cm_weight: 0.35, text_weight: 0.25 }, identity_risk: 0.1, authenticity_risk: 0.1, authenticity_risk_effective: 0.05, intent_risk: 0.1 },
 spoof: { timeline: [], median_score: 0.1, peak_score: 0.2, max_synth_run_s: 0, is_synthetic: false }, script: { incriminating_markers: [], exculpatory_markers: [], playbooks: [] }, transcript: { text: '', detected_language: 'en' }
});
test('avatar initials preserve complete Hindi and emoji graphemes', () => {
 assert.equal(initial('  किरण शर्मा'), 'कि');
 assert.equal(initial('👩🏽‍⚕️ Dr Asha'), '👩🏽‍⚕️');
 assert.equal(initial('e\u0301lodie'), 'E\u0301');
 assert.equal(initial('J'), 'J');
 assert.equal(initial('  '), '?');
});
test('authority and unknown identity cannot become verified', () => {
 assert.equal(displayBand(parseScreening(fixture('authority_check'))), 'unverified');
 assert.equal(displayBand(parseScreening(fixture('identity_check', 'unknown'))), 'unverified');
 assert.equal(displayBand(parseScreening(fixture())), 'verified');
});
test('failed quality takes precedence over a score', () => {
 assert.equal(displayBand(parseScreening(fixture('identity_check', 'match', false))), 'insufficient');
});
test('malformed responses do not become demo verdicts', () => {
 for (const body of [null, {}, { ...fixture(), fusion: {} }]) assert.throws(() => parseScreening(body), /incomplete/);
});
test('nested service corruption is rejected before report rendering', () => {
 const cases = [
  { ...fixture(), fusion: { ...fixture().fusion, weights_used: null } },
  { ...fixture(), fusion: { ...fixture().fusion, recommended_actions: [{}] } },
  { ...fixture(), fusion: { ...fixture().fusion, reason_codes: [null] } },
  { ...fixture(), fusion: { ...fixture().fusion, trust_score: 101 } },
  { ...fixture(), quality: { ...fixture().quality, passed: 'yes' } },
  { ...fixture(), script: { ...fixture().script, playbooks: [{}] } },
  { ...fixture(), script: { ...fixture().script, incriminating_markers: [null] } },
  { ...fixture(), transcript: { text: {}, detected_language: 'hi' } },
  { ...fixture(), spoof: { ...fixture().spoof, timeline: [{ start_s: 4, end_s: 2, score: 0.5, is_synthetic: true }] } },
 ];
 for (const body of cases) assert.throws(() => parseScreening(body), /incomplete/);
});
test('unverified reports have no green reference interval', () => {
 assert.ok(reportIntervals(parseScreening(fixture('authority_check', 'unknown'))).every(zone => zone.tone === 'neutral'));
 assert.ok(reportIntervals(parseScreening(fixture())).some(zone => zone.tone === 'success'));
});
test('synthetic property alone is neutral and reference thresholds come from evidence', () => {
 const data = parseScreening(fixture('authority_check', 'unknown'));
 data.spoof.is_synthetic = true;
 data.spoof.timeline = [{ start_s: 0, end_s: 3, score: 0.98, is_synthetic: true }];
 const initial = signalRows(data)[1];
 assert.equal(initial.flag.tone, 'neutral');
 assert.equal(initial.reference, undefined);
 data.fusion.reason_codes = [{ code: 'CM_HIGH', signal: 'authenticity', value: 'Peak 98%', threshold: '> 40%', explanation: 'Concerning synthesis with risky intent.', severity: 'high', citation_title: null, citation_url: null }];
 const row = signalRows(data)[1];
 assert.equal(row.flag.mark, 'H');
 assert.deepEqual(row.reference?.interval, { value: 98, threshold: 40 });
});
test('evidence links exclude script and data URLs', () => {
 assert.equal(safeLink('javascript:alert(1)'), undefined);
 assert.equal(safeLink('data:text/html,test'), undefined);
 assert.equal(safeLink('https://example.com/evidence'), 'https://example.com/evidence');
 assert.equal(number(NaN), 'Unavailable');
});
test('empty and nonaudio files are rejected before upload', () => {
 assert.match(audioError(new File([], 'empty.wav'))!, /empty/);
 assert.match(audioError(new File(['test'], 'readme.txt', { type: 'text/plain' }))!, /supported/);
 assert.equal(audioError(new File(['test'], 'voice.wav', { type: 'audio/wav' })), null);
});
test('service errors preserve the server explanation', async () => {
 const original = globalThis.fetch;
 try {
  globalThis.fetch = async () => new Response(JSON.stringify({ detail: 'Need more speech.' }), { status: 422 });
  await assert.rejects(request('/api/screen'), /Need more speech/);
  globalThis.fetch = async () => { throw new TypeError('network unavailable'); };
  await assert.rejects(request('/api/screen'), /Cannot reach/);
 } finally { globalThis.fetch = original; }
});

