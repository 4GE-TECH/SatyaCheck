import type { ScreeningResponse } from '../types/contracts';
import { bands, date, displayBand } from './presentation';

export function reportText(data: ScreeningResponse, demo: boolean): string {
  const band = displayBand(data);
  return `${demo ? 'SAMPLE — DEMONSTRATION ONLY\n' : ''}SatyaCheck screening report
Session: ${data.session_id}
Received: ${date(data.timestamp)}
Result: ${bands[band].label}
Trust score: ${band === 'insufficient' ? 'Not reported (insufficient speech)' : `${Math.round(data.fusion.trust_score)}/100 (not a probability)`}
Audio SHA-256: ${demo ? 'sample digest' : data.audio_sha256 || 'Not supplied'}

Remarks
${data.fusion.reason_codes.map(r => `- ${r.explanation}\n  Observed: ${r.value}; threshold: ${r.threshold || 'not supplied'}\n  Source: ${r.citation_title || 'not supplied'} ${r.citation_url || ''}`).join('\n') || '- None returned'}

Transcript (automatic; may contain errors)
${data.transcript.text || 'Not available'}

Recommended actions
${data.fusion.recommended_actions.map(action => `- ${action}`).join('\n') || '- Verify through a number you already trust.'}

This is a screening summary, not an official complaint or a determination of fraud.`;
}
