import { useEffect, useRef, useState, type FormEvent } from 'react';
import { ArrowRight, BellRinging, BellSlash, Copy, Phone, PhoneDisconnect, PhoneIncoming } from '@phosphor-icons/react';
import { useCallFeed, type CallPoint, type CallState, type FeedStatus } from '../../app/callFeed';
import { useWorkspace } from '../../app/workspace';
import { wsUrl } from '../../lib/api';
import { BANDS, calm, clock, isDevanagari, languageName, pct, trustIntervals, type Tone } from '../../lib/verdict';
import { Button, ButtonLink, Notice, ToneChip } from '../../components/ui';
import { EASE, gsap, reducedMotion, useGSAP } from '../../lib/motion';

const OVERLAY_TONE: Record<string, Tone> = { green: 'safe', amber: 'caution', red: 'danger', grey: 'neutral' };

const FEED_LABEL: Record<FeedStatus, string> = {
  connecting: 'Connecting to the call feed…',
  open: 'Watching for calls',
  reconnecting: 'Reconnecting…',
  refused: 'The feed needs a token',
  closed: 'Disconnected',
};

const IDENTITY_TEXT = { match: 'A voice you enrolled', mismatch: 'Differs from the claimed person', unknown: 'Not an enrolled voice' } as const;
const VOICE_TEXT = { synthetic: 'Signs of a synthetic voice', bonafide: 'No synthetic signs', unavailable: 'Not measured' } as const;

export default function CallsPage() {
  const feed = useCallFeed();
  const live = feed.calls.filter(c => !c.final);
  const ended = feed.calls.filter(c => c.final);

  return (
    <div className="page calls-page">
      <header className="page-head">
        <h1>Phone calls</h1>
        <p>
          Calls routed through Exotel are screened on the server as they happen. Each call appears here within a few
          seconds and updates about every two seconds of speech. Nothing on this page records audio.
        </p>
      </header>

      <FeedBar />

      {feed.needsToken && <TokenForm />}

      <section aria-labelledby="calls-live" className="calls-section">
        <h2 id="calls-live" className="calls-heading">
          On a call now <span className="calls-count num">{live.length}</span>
        </h2>
        {live.length ? (
          <ul className="call-list" role="list">
            {live.map(call => <li key={call.sessionId}><CallCard call={call} /></li>)}
          </ul>
        ) : (
          <EmptyCalls status={feed.status} />
        )}
      </section>

      {ended.length > 0 && (
        <section aria-labelledby="calls-ended" className="calls-section">
          <div className="calls-heading-row">
            <h2 id="calls-ended" className="calls-heading">Ended in this session <span className="calls-count num">{ended.length}</span></h2>
            <Button variant="ghost" size="sm" onClick={feed.clearEnded}>Clear ended calls</Button>
          </div>
          <ul className="call-list" role="list">
            {ended.map(call => <li key={call.sessionId}><CallCard call={call} /></li>)}
          </ul>
        </section>
      )}
    </div>
  );
}

function FeedBar() {
  const feed = useCallFeed();
  const connected = feed.status === 'open';
  return (
    <div className={`feed-bar feed-${feed.status}`} role="status" aria-live="polite">
      <span className="feed-state">
        <span className="feed-dot" aria-hidden="true" />
        {FEED_LABEL[feed.status]}
      </span>
      <div className="feed-actions">
        <Button
          variant="ghost"
          size="sm"
          onClick={() => feed.setSoundOn(!feed.soundOn)}
          aria-pressed={feed.soundOn}
        >
          {feed.soundOn ? <BellRinging size={16} weight="bold" aria-hidden="true" /> : <BellSlash size={16} weight="bold" aria-hidden="true" />}
          {feed.soundOn ? 'Sound on for warnings' : 'Sound off'}
        </Button>
        {connected || feed.status === 'reconnecting' || feed.status === 'connecting'
          ? <Button variant="secondary" size="sm" onClick={feed.disconnect}>Disconnect</Button>
          : <Button variant="primary" size="sm" onClick={() => feed.connect()}>Connect</Button>}
      </div>
    </div>
  );
}

function TokenForm() {
  const feed = useCallFeed();
  const [token, setToken] = useState('');
  function submit(event: FormEvent) {
    event.preventDefault();
    feed.connect(token);
  }
  return (
    <form className="panel token-form" onSubmit={submit}>
      <Notice tone="caution">
        The screening service refused the feed. It is protected by a token because verdicts carry call transcripts.
        Ask whoever runs the service for it.
      </Notice>
      <div className="field">
        <label htmlFor="feed-token">Live-feed token</label>
        <input id="feed-token" className="input" type="password" autoComplete="off" value={token} onChange={e => setToken(e.target.value)} />
        <span className="hint">Kept only while this tab is open. It is never saved.</span>
      </div>
      <Button type="submit" variant="primary" disabled={!token.trim()}>Connect with token</Button>
    </form>
  );
}

function EmptyCalls({ status }: { status: FeedStatus }) {
  const stream = wsUrl('/api/exotel/stream');
  const [copied, setCopied] = useState(false);
  async function copy() {
    try {
      await navigator.clipboard.writeText(stream);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1800);
    } catch {
      setCopied(false);
    }
  }
  return (
    <div className="panel calls-empty">
      <PhoneIncoming size={36} weight="duotone" aria-hidden="true" />
      <div>
        <p className="calls-empty-title">{status === 'open' ? 'No call in progress.' : 'Not watching for calls yet.'}</p>
        <p className="muted">
          Verdicts only flow while a call is live, and earlier verdicts are not replayed. Keep this page open before the call starts.
        </p>
        <p className="muted small">In Exotel, point the Stream applet at this service’s stream address:</p>
        <div className="stream-url">
          <code>{stream}</code>
          <Button size="sm" variant="ghost" onClick={copy}><Copy size={15} weight="bold" aria-hidden="true" />{copied ? 'Copied' : 'Copy'}</Button>
        </div>
      </div>
    </div>
  );
}

function useTicker(active: boolean) {
  const [, setTick] = useState(0);
  useEffect(() => {
    if (!active) return;
    const timer = window.setInterval(() => setTick(n => n + 1), 1000);
    return () => window.clearInterval(timer);
  }, [active]);
}

function CallCard({ call }: { call: CallState }) {
  const { healthDetail } = useWorkspace();
  const v = call.latest;
  const listening = v.band === 'insufficient';
  const band = BANDS[v.band] ?? BANDS.unverified;
  const tone = OVERLAY_TONE[v.overlay_state] ?? 'neutral';
  const caller = v.caller_context?.claimed_number || v.caller_context?.claimed_name || 'Unknown number';
  const card = useRef<HTMLElement>(null);
  useTicker(!call.final);

  // An escalation flashes the card's edge once; nothing else moves.
  useGSAP(() => {
    if (reducedMotion() || !call.escalations) return;
    gsap.fromTo(card.current, { '--edge': 1 }, { '--edge': 0, duration: 1.4, ease: EASE.out });
  }, { dependencies: [call.escalations], scope: card });

  const evidence = [...v.reason_codes]
    .filter(r => r.severity !== 'info')
    .sort((a, b) => SEVERITY.indexOf(a.severity) - SEVERITY.indexOf(b.severity))
    .slice(0, 3);
  const transcript = v.transcript?.trim() ?? '';
  const duration = call.final ? call.points.at(-1)?.at ?? 0 : (Date.now() - call.startedAt) / 1000;

  return (
    <article ref={card} className={`panel call-card tone-${tone}${call.final ? ' is-final' : ''}`} aria-label={`Call from ${caller}`}>
      <header className="call-head">
        <div className="call-who">
          <Phone size={20} weight="duotone" aria-hidden="true" />
          <div>
            <p className="call-number num">{caller}</p>
            <p className="muted small">
              {call.final ? <><PhoneDisconnect size={13} weight="bold" aria-hidden="true" /> Ended after {clock(duration)}</> : <>On call · <span className="num">{clock(duration)}</span></>}
              {v.mode === 'authority_check' ? ' · stranger check' : ' · known-contact check'}
            </p>
          </div>
        </div>
        <ToneChip tone={listening ? 'neutral' : tone} size="lg">{listening ? 'Listening…' : band.label}</ToneChip>
      </header>

      <div className="call-body">
        <div className="call-score">
          {listening ? (
            <p className="call-trust"><span className="muted">No score yet: not enough clear speech</span></p>
          ) : (
            <>
              <p className="call-trust"><span className="num">{Math.round(v.trust_score)}</span><span className="muted">/100 trust for the call</span></p>
              {Number.isFinite(v.window_trust_score) && !call.final && (
                <p className="muted small">Right now: <span className="num">{Math.round(v.window_trust_score!)}</span>/100. The call score only goes down, so an earlier warning stays visible.</p>
              )}
            </>
          )}
          <Sparkline points={call.points} verified={v.band === 'verified'} />
        </div>

        <dl className="call-signals">
          <div><dt>Identity</dt><dd>{IDENTITY_TEXT[v.signals.identity] ?? 'Not assessed'}</dd></div>
          <div><dt>Voice</dt><dd>{VOICE_TEXT[v.signals.authenticity] ?? 'Not measured'}</dd></div>
          <div>
            <dt>What is asked</dt>
            <dd>{pct(v.signals.intent_risk)} concern{healthDetail?.retrievalAvailable === false ? ' (keyword check only)' : ''}</dd>
          </div>
        </dl>
      </div>

      {v.threat_label && (
        <p className="call-threat">
          Resembles <strong>{v.threat_label.threat}</strong> <span className="muted">· {v.threat_label.sector.replace(/_/g, ' ')}</span>
        </p>
      )}

      {v.vernacular_warning && (
        <p className="call-vernacular" lang={isDevanagari(v.vernacular_warning) ? 'hi' : undefined}>{v.vernacular_warning}</p>
      )}

      {!listening && v.recommended_actions[0] && <p className="call-action">{calm(v.recommended_actions[0])}</p>}

      {evidence.length > 0 && (
        <ul className="call-evidence" aria-label="Evidence">
          {evidence.map((r, i) => (
            <li key={`${r.code}-${i}`} className={`sev-${r.severity}`}>
              <span>{r.explanation}</span>
              <span className="muted small num">{r.value}</span>
            </li>
          ))}
        </ul>
      )}

      <div className="call-transcript">
        <p className="muted small">Transcript{v.language && v.language !== 'unknown' ? ` · ${languageName(v.language)}` : ''} · automatic, may contain errors</p>
        {transcript
          ? <blockquote dir="auto" lang={isDevanagari(transcript) ? 'hi' : undefined}>{transcript.length > 360 ? `…${transcript.slice(-360)}` : transcript}</blockquote>
          : <p className="muted">Appears after roughly 10 to 15 seconds of speech. The score does not wait for it.</p>}
      </div>

      {call.final && (
        <div className="call-foot">
          <ButtonLink to={`/report/${encodeURIComponent(call.sessionId)}`} variant="secondary" trail={<ArrowRight size={16} weight="bold" />}>Open the full report</ButtonLink>
        </div>
      )}
    </article>
  );
}

const SEVERITY = ['critical', 'high', 'medium', 'low', 'info'];

/** Call trust (solid) and each window's own score (dotted) over the call, on the band intervals. */
function Sparkline({ points, verified }: { points: CallPoint[]; verified: boolean }) {
  const width = 320;
  const height = 64;
  const span = Math.max(20, ...points.map(p => p.at));
  const x = (t: number) => (t / span) * width;
  const y = (trust: number) => height - (Math.max(0, Math.min(100, trust)) / 100) * height;
  const scored = points.filter(p => p.band !== 'insufficient');
  const line = (pick: (p: CallPoint) => number | null) => scored
    .filter(p => pick(p) != null)
    .map((p, i) => `${i ? 'L' : 'M'}${x(p.at).toFixed(1)} ${y(pick(p)!).toFixed(1)}`)
    .join(' ');
  const last = scored.at(-1);
  return (
    <div className="call-spark">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img"
        aria-label={last ? `Call trust ${Math.round(last.trust)} of 100 after ${scored.length} scored ${scored.length === 1 ? 'window' : 'windows'}` : 'No scored windows yet'}>
        {trustIntervals(verified).map(zone => (
          <rect key={zone.label} x="0" width={width} y={y(zone.to)} height={y(zone.from) - y(zone.to)} className={`trace-zone tone-${zone.tone}`} />
        ))}
        <path d={line(p => p.window)} className="spark-window" vectorEffect="non-scaling-stroke" />
        <path d={line(p => p.trust)} className="trace-line" vectorEffect="non-scaling-stroke" />
      </svg>
      {last && <span className="spark-dot" style={{ left: `clamp(7px, ${(x(last.at) / width) * 100}%, calc(100% - 7px))`, top: `clamp(7px, ${(y(last.trust) / height) * 100}%, calc(100% - 7px))` }} aria-hidden="true" />}
    </div>
  );
}
