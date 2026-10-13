import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, PhoneCall, WarningCircle } from '@phosphor-icons/react';
import {
  CHANNELS, duration, getLiveCalls, rtcSession, useAdminFeed, whoLabel,
  type FeedVerdict, type LiveCall, type VoiceState,
} from '../../lib/admin';
import { BANDS } from '../../lib/verdict';
import type { TrustBand } from '../../types/contracts';
import { Notice, ToneChip } from '../../components/ui';

const FEED_LABEL = { connecting: 'Connecting…', open: 'Live', reconnecting: 'Reconnecting…', refused: 'Refused' } as const;

export default function LiveCallsPage() {
  const [calls, setCalls] = useState<LiveCall[]>([]);
  const [error, setError] = useState('');
  const feed = useAdminFeed();

  useEffect(() => {
    let stop = false;
    const controller = new AbortController();
    const load = () => getLiveCalls(controller.signal)
      .then(c => { if (!stop) { setCalls(c); setError(''); } })
      .catch(e => { if (!stop && !controller.signal.aborted) setError(e.message); });
    void load();
    const timer = window.setInterval(load, 2000);
    return () => { stop = true; controller.abort(); window.clearInterval(timer); };
  }, []);

  const bySession = new Map(feed.sessions.map(v => [v.session_id, v]));
  const liveCallIds = new Set(calls.map(c => c.call_id));
  const others = feed.sessions.filter(v => {
    const rtc = rtcSession(v.session_id);
    return !rtc || !liveCallIds.has(rtc.callId);
  });

  return (
    <div className="page admin-page">
      <header className="page-head">
        <h1>Live calls</h1>
        <p>Calls in progress across every account: who is talking, what is being said, and what each person is being shown.</p>
      </header>

      <p className={`feed-status is-${feed.status}`} role="status">
        <span className="rec-dot" aria-hidden="true" />{FEED_LABEL[feed.status]}
        {feed.status === 'refused' && ' — this account may not watch the live feed.'}
      </p>
      {error && <Notice tone="danger">{error}</Notice>}

      <section aria-labelledby="app-calls">
        <h2 id="app-calls" className="admin-section-title">App calls</h2>
        {calls.length === 0 ? (
          <div className="panel people-empty"><PhoneCall size={32} weight="duotone" aria-hidden="true" /><p>No app call is ringing or in progress.</p></div>
        ) : (
          <div className="live-call-list">
            {calls.map(call => <CallCard key={call.call_id} call={call} feed={bySession} />)}
          </div>
        )}
      </section>

      <section aria-labelledby="other-sessions">
        <h2 id="other-sessions" className="admin-section-title">Other live sessions</h2>
        <p className="muted small">Web listening, the app’s own stream and phone lines, from the moment this page opened.</p>
        {others.length === 0 ? <p className="muted">Nothing else is being screened right now.</p> : (
          <div className="live-call-list">
            {others.map(v => <SessionCard key={v.session_id} verdict={v} />)}
          </div>
        )}
      </section>
    </div>
  );
}

function CallCard({ call, feed }: { call: LiveCall; feed: Map<string, FeedVerdict> }) {
  const voice = (role: 'caller' | 'callee') => call.voices.find(v => v.session_id.endsWith(`_${role}`));
  return (
    <article className="panel live-call">
      <header className="live-call-head">
        <div>
          <h3>{whoLabel(call.caller)} <ArrowRight size={14} weight="bold" aria-label="calling" /> {whoLabel(call.callee)}</h3>
          <p className="muted small num">
            {call.status === 'ringing' ? `Ringing for ${duration(call.age_s)}` : `In call ${duration(call.in_call_s)}`}
            {' · '}{call.screening ? 'screening running' : 'screening not running'}
          </p>
        </div>
        <ToneChip tone={call.status === 'active' ? 'safe' : 'neutral'}>{call.status === 'active' ? 'In progress' : 'Ringing'}</ToneChip>
      </header>
      {call.status === 'ringing' ? (
        <p className="muted">Nobody is screened until the call is answered.</p>
      ) : (
        <div className="voice-pair">
          <VoicePane title={`${whoLabel(call.caller)} speaking`} listener={whoLabel(call.callee)}
            state={voice('caller')?.state ?? null} feed={feed.get(voice('caller')?.session_id ?? '')} sessionId={voice('caller')?.session_id} />
          <VoicePane title={`${whoLabel(call.callee)} speaking`} listener={whoLabel(call.caller)}
            state={voice('callee')?.state ?? null} feed={feed.get(voice('callee')?.session_id ?? '')} sessionId={voice('callee')?.session_id} />
        </div>
      )}
    </article>
  );
}

function VoicePane({ title, listener, state, feed, sessionId }:
  { title: string; listener: string; state: VoiceState | null; feed?: FeedVerdict; sessionId?: string }) {
  const band = (state?.display_band ?? 'insufficient') as TrustBand;
  const copy = BANDS[band] ?? BANDS.insufficient;
  const transcript = feed?.transcript || state?.transcript_tail || '';
  const open = state?.alerts.filter(a => !a.resolved) ?? [];
  return (
    <section className="voice-pane" aria-label={title}>
      <div className="voice-pane-head">
        <h4>{title}</h4>
        <ToneChip tone={copy.tone}>{copy.label}</ToneChip>
      </div>
      <p className="muted small">
        Shown to {listener}
        {state?.trust_score != null && band !== 'insufficient' && <> · <span className="num">{Math.round(state.trust_score)}</span>/100</>}
        {state?.mode && <> · {state.mode === 'identity_check' ? 'checked against a saved voice' : 'stranger check'}</>}
      </p>
      {state && !state.screening_available && <Notice tone="caution">Screening paused: {state.reason}</Notice>}
      {state?.coverage && (state.coverage.unscreened_s > 0 || state.coverage.degraded) && (
        <p className="muted small">Part of this voice could not be checked ({Math.round(state.coverage.unscreened_s)} s).</p>
      )}
      {open.length > 0 && (
        <ul className="voice-alerts">
          {open.map(a => (
            <li key={a.alert_id}><WarningCircle size={16} weight="fill" aria-hidden="true" />{a.evidence ?? BANDS[a.band]?.headline}</li>
          ))}
        </ul>
      )}
      <p className="voice-transcript">{transcript || <span className="muted">No words yet.</span>}</p>
      {sessionId && <Link className="small" to={`/calls/${encodeURIComponent(sessionId)}`}>Open this voice’s report</Link>}
    </section>
  );
}

function SessionCard({ verdict }: { verdict: FeedVerdict }) {
  const copy = BANDS[verdict.band] ?? BANDS.insufficient;
  const rtc = rtcSession(verdict.session_id);
  const ago = Math.round((Date.now() - verdict.received_at) / 1000);
  return (
    <article className="panel live-call">
      <header className="live-call-head">
        <div>
          <h3 className="mono">{verdict.session_id}</h3>
          <p className="muted small">
            {rtc ? CHANNELS.webrtc : 'Live session'} · account {verdict.owner_id ? `${verdict.owner_id.slice(0, 8)}…` : 'unknown'}
            {' · '}{verdict.is_final ? 'ended' : `updated ${ago} s ago`}
          </p>
        </div>
        <ToneChip tone={copy.tone}>{copy.label}</ToneChip>
      </header>
      <p className="voice-transcript">{verdict.transcript || <span className="muted">No words yet.</span>}</p>
      <Link className="small" to={`/calls/${encodeURIComponent(verdict.session_id)}`}>Open the report</Link>
    </article>
  );
}
