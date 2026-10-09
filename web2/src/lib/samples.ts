import type { ScreeningResponse, TrustBand } from './contracts';
import type { Check } from './api';

export const samples = [
  { band: 'high_risk', name: 'The urgent money request', description: 'Familiar voice. Pressure to transfer.', lang: 'Hinglish', duration: '12 sec', icon: 'alert' },
  { band: 'unverified', name: 'The automated reminder', description: 'An unknown voice, without pressure.', lang: 'English', duration: '8 sec', icon: 'phone' },
  { band: 'verified', name: 'The family check-in', description: 'A known voice invites verification.', lang: 'Hindi', duration: '10 sec', icon: 'voice' },
] as const;

export function sampleCheck(band: TrustBand): Check {
  const concerning = ['high_risk','suspicious','caution'].includes(band);
  const unknown = band === 'unverified';
  const insufficient = band === 'insufficient';
  const score = { verified: 92, caution: 63, suspicious: 42, high_risk: 16, unverified: 74, insufficient: 50 }[band];
  const result: ScreeningResponse = {
    session_id: `sample_${band}_${crypto.randomUUID()}`, timestamp: new Date().toISOString(), audio_sha256: 'Sample illustration — no audio was analysed', processing_time_ms: 0,
    quality: { passed: !insufficient, speech_duration_s: insufficient ? .7 : 12, snr_db: 18, min_speech_threshold_s: 1.5, min_snr_threshold_db: 5, reason: insufficient ? 'The sample contains less than 1.5 seconds of usable speech.' : null },
    speaker: { verdict: unknown ? 'unknown' : concerning ? 'mismatch' : 'match', matched_person_id: unknown ? null : 'sample-person', matched_person_name: unknown ? null : 'Aarav (sample contact)', claimed_person_id: null, raw_score: 0, norm_score: 0, risk: concerning ? .84 : unknown ? .5 : .08, is_replay: false, confidence: .8, details: {} },
    spoof: { median_score: concerning ? .82 : unknown ? .9 : .13, peak_score: concerning ? .97 : unknown ? .95 : .22, max_synth_run_s: concerning ? 4.5 : unknown ? 6 : 0, raw_score: 0, norm_score: 0, risk: concerning ? .82 : .13, is_synthetic: concerning || unknown,
      timeline: Array.from({ length: 12 }, (_, i) => ({ start_s: i, end_s: i + 1, score: concerning ? [.2,.22,.3,.45,.68,.92,.97,.94,.93,.85,.63,.46][i] : unknown ? .82 + i % 3 * .04 : .1 + i % 4 * .04, is_synthetic: concerning ? i >= 4 && i < 10 : unknown })), details: {} },
    transcript: { text: concerning ? 'Papa, main mushkil mein hoon. Abhi paise bhejo. Kisi ko mat batana, phone mat kaatna.' : unknown ? 'This is an automated appointment reminder. Please call the number on your appointment letter if you need to make a change.' : 'पापा, मैं घर पहुँच गया। समय मिले तो मेरे पुराने नंबर पर फोन कर लेना। हम सब ठीक हैं।', segments: [], detected_language: concerning ? 'Hinglish' : unknown ? 'English' : 'Hindi', confidence: .9 },
    script: { risk: concerning ? .9 : .06, intent_summary: concerning ? 'Urgent payment request with secrecy and pressure to stay on the call.' : 'A routine update with an invitation to verify independently.',
      incriminating_markers: concerning ? [{ marker_id: 'isolation', marker_type: 'incriminating', category: 'isolation', matched_text: 'Kisi ko mat batana', weight: .8, description: 'The caller asks the listener not to tell anyone.' }, { marker_id: 'payment', marker_type: 'incriminating', category: 'payment', matched_text: 'Abhi paise bhejo', weight: .9, description: 'An immediate request to send money.' }] : [],
      exculpatory_markers: concerning ? [] : [{ marker_id: 'callback', marker_type: 'exculpatory', category: 'verification', matched_text: unknown ? 'call the number on your appointment letter' : 'मेरे पुराने नंबर पर फोन कर लेना', weight: -.4, description: 'The caller invites an independent callback.' }], playbooks: [], details: {} },
    fusion: { trust_score: score, risk_score: 1 - score / 100, band, mode: unknown ? 'authority_check' : 'identity_check', weights_used: { asv_weight: unknown ? .1 : .4, cm_weight: unknown ? .45 : .35, text_weight: unknown ? .45 : .25 }, identity_risk: concerning ? .84 : .08, authenticity_risk: concerning ? .82 : .13, authenticity_risk_effective: concerning ? .8 : .05, intent_risk: concerning ? .9 : .06,
      reason_codes: concerning ? [{ code: 'ISOLATION_PRESSURE', signal: 'intent', value: '2 concerning phrases', threshold: 'Pressure and isolation markers', explanation: 'The caller combines an immediate payment request with a demand for secrecy. Confirm through a separate, trusted channel.', citation_title: 'National Cyber Crime Reporting Portal', citation_url: 'https://cybercrime.gov.in', severity: 'high' }, { code: 'SYNTHETIC_RUN', signal: 'authenticity', value: '4.5 seconds', threshold: 'Sample synthetic segment threshold: 0.60', explanation: 'The illustrative signal remains elevated across the sensitive request. Synthetic audio is considered alongside intent, not as proof of fraud.', citation_title: null, citation_url: null, severity: 'high' }] : [{ code: 'VERIFY_INVITED', signal: 'intent', value: 'Independent callback invited', threshold: null, explanation: 'The invitation to verify independently lowers concern. It does not guarantee that the request is safe.', citation_title: null, citation_url: null, severity: 'info' }],
      recommended_actions: concerning ? ['Pause the conversation before sending money or sharing an OTP.', 'Call back using a number you already know.', 'Ask a trusted family member to help verify the request.'] : ['Verify unexpected requests through a known number.', 'Use this result as supporting evidence, not a guarantee.'],
      challenge_question: concerning ? { question_id: 'sample-question', question_text: 'Where did we go together on our last family trip?', relation_context: 'Illustrative shared question', expected_answer_hash: null } : null, vernacular_warning: concerning ? 'रुकिए। पैसे भेजने से पहले परिचित नंबर पर फोन करके पुष्टि करें।' : null },
  };
  return { result, sample: true, name: samples.find(s => s.band === band)?.name || 'Sample result' };
}
