import { useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { EASE, gsap, reducedMotion, useGSAP } from '../../lib/motion';
import { ambient } from '../../components/AmbientField';
import { Broadcast, DeviceMobileSpeaker, Microphone, Stop, Info, WarningCircle } from '@phosphor-icons/react';
import { useWorkspace } from '../../app/workspace';
import { useLiveSession, type LivePoint } from '../../hooks/useLiveSession';
import { LiveSpectrogram } from '../../components/SpectrogramCanvas';
import { Button, FlagBadge, Notice, ToneChip } from '../../components/ui';
import { CallerPicker } from '../../components/CallerPicker';
import type { CoverageSpan, StreamV2Alert } from '../../types/contracts';
import { BANDS, calm, clock, signals, trustIntervals } from '../../lib/verdict';

export default function LivePage() {
  const live = useLiveSession();
  const { addRecord } = useWorkspace();
  const navigate = useNavigate();
  const active = live.phase === 'connecting' || live.phase === 'listening' || live.phase === 'finishing';
  // The server's display band: it holds the most serious read of the call, so a calm
  // stretch later never quietly erases an earlier concern.
  const band = live.result ? live.band : null;
  const [claim, setClaim] = useState<string | null>(null);
  const copy = band ? BANDS[band] : null;

  const side = useRef<HTMLElement>(null);

  // The microphone level drives the whole ambient field while the room is listening.
  useEffect(() => {
    const analyser = live.analyser;
    if (!analyser) { ambient.level = 0; return; }
    const buffer = new Float32Array(analyser.fftSize);
    let frame = 0;
    const tick = () => {
      analyser.getFloatTimeDomainData(buffer);
      let total = 0;
      for (const sample of buffer) total += sample * sample;
      ambient.level = Math.min(1, Math.sqrt(total / buffer.length) * 7);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(frame); ambient.level = 0; };
  }, [live.analyser]);

  // Each new read lands with a small lift; a band change also flashes the room's edge.
  useGSAP(() => {
    if (reducedMotion() || !live.result) return;
    gsap.from('.room-verdict > *', { y: 10, duration: 0.6, stagger: 0.05, ease: EASE.out });
    gsap.fromTo('.room', { '--edge': 1 }, { '--edge': 0, duration: 1.2, ease: EASE.out });
  }, { dependencies: [band], scope: side });

  useEffect(() => {
    if (live.phase !== 'done' || !live.result) return;
    const data = live.result;
    addRecord({ data, name: 'Live listening', source: 'live', audio: live.recording });
    navigate(`/report/${encodeURIComponent(data.session_id)}`);
  }, [live.phase, live.result, live.recording, addRecord, navigate]);

  function keepPartial() {
    if (!live.result) return;
    addRecord({ data: live.result, name: 'Live listening (interrupted)', source: 'live', audio: live.recording });
    navigate(`/report/${encodeURIComponent(live.result.session_id)}`);
  }

  return (
    <div className="page live-page">
      <header className="page-head">
        <h1>Listen to a live call</h1>
        <p>Put the call on speaker and place this device beside it. SatyaCheck listens continuously and updates its read every few seconds.</p>
      </header>

      <section ref={side} className={`room phase-${live.phase}${copy ? ` tone-${copy.tone}` : ''}`} aria-label="Listening room">
        <div className="room-main">
          <div className="room-status">
            <span className="room-state">
              <span className="rec-dot" aria-hidden="true" />
              {live.phase === 'connecting' ? 'Connecting…' : live.phase === 'listening' ? 'Listening' : live.phase === 'finishing' ? 'Finalising the report…' : live.phase === 'error' ? 'Stopped' : 'Ready'}
            </span>
            <span className="num room-clock">{clock(live.elapsed)}</span>
            <span className="room-count">{clock(Math.round(live.sent * 0.5))} of audio sent · {live.history.length} {live.history.length === 1 ? 'update' : 'updates'}</span>
          </div>

          <div className="room-spectrum">
            <LiveSpectrogram analyser={live.analyser} label="Live spectrogram of the microphone" />
            {!active && (
              <div className="room-idle">
                <DeviceMobileSpeaker size={40} weight="duotone" aria-hidden="true" />
                <p>The phone on the call can’t hear its own call: Android gives other apps silence. Listen from this device instead.</p>
              </div>
            )}
          </div>

          <TrustTrace points={live.history} elapsed={live.elapsed} />
          <CoverageStrip spans={live.coverage} degraded={live.coverageDegraded} elapsed={live.elapsed} />
          <LiveTranscript committed={live.committed} tentative={live.tentative} active={active} />
        </div>

        <aside className="room-side" aria-live="polite">
            {live.result && copy && band ? (
              <div key={band} className="room-verdict">
                <div className="room-verdict-top">
                  <ToneChip tone={copy.tone}>{copy.label}</ToneChip>
                  <span className="provisional">Provisional</span>
                </div>
                <p className="room-headline">{copy.headline}</p>
                <p className="room-trust">
                  {band === 'insufficient' ? <span className="muted">No score yet: need more speech</span> : <><span className="num">{Math.round(live.result.fusion.trust_score)}</span><span className="muted">/100 trust</span></>}
                </p>
                <ul className="room-signals">
                  {signals(live.result).map(s => (
                    <li key={s.key}><span>{s.name}</span><span className="muted">{s.finding}</span><FlagBadge flag={s.flag} /></li>
                  ))}
                </ul>
                {live.result.fusion.recommended_actions[0] && <p className="room-action">{calm(live.result.fusion.recommended_actions[0])}</p>}
              </div>
            ) : (
              <div key="waiting" className="room-waiting">
                <Broadcast size={28} weight="duotone" aria-hidden="true" />
                <p>{active ? 'Waiting for the first few seconds of speech…' : 'The read appears here as soon as speech arrives.'}</p>
              </div>
            )}
          <AlertList alerts={live.alerts} />
          <p className="room-rule"><Info size={16} weight="bold" aria-hidden="true" />Warnings only escalate during a call. A calm stretch later does not erase an earlier concern.</p>
        </aside>

        <div className="room-controls">
          {live.warning && <Notice tone="caution">{live.warning}</Notice>}
          {live.error && (
            <Notice tone="danger" action={live.result ? <Button size="sm" onClick={keepPartial}>Open last read</Button> : undefined}>
              {live.error}
            </Notice>
          )}
          {!active && <CallerPicker value={claim} onChange={setClaim} />}
          <div className="row-gap">
            {active ? (
              <>
                <Button variant="danger" size="lg" onClick={live.stop} disabled={live.phase !== 'listening'} busy={live.phase === 'finishing'}>
                  {live.phase !== 'finishing' && <Stop size={18} weight="fill" aria-hidden="true" />}Stop and finalise
                </Button>
                <Button variant="ghost" onClick={live.reset}>Discard</Button>
              </>
            ) : (
              <Button variant="primary" size="lg" onClick={() => void live.start({ claimedPersonId: claim })}><Microphone size={18} weight="fill" aria-hidden="true" />Start listening</Button>
            )}
          </div>
          <p className="muted small">Only listen to calls you are part of. Audio is sent to your configured screening service.</p>
        </div>
      </section>
    </div>
  );
}

/** Which stretches of the call were actually screened. Gaps are audio the service could not keep up with. */
function CoverageStrip({ spans, degraded, elapsed }: { spans: CoverageSpan[]; degraded: boolean; elapsed: number }) {
  if (!spans.length) return null;
  const span = Math.max(30, elapsed, ...spans.map(s => s.end_s));
  const missed = spans.filter(s => !s.scored).reduce((total, s) => total + (s.end_s - s.start_s), 0);
  return (
    <figure className="coverage">
      <figcaption>
        Screened audio
        {missed >= 1 && <span className="muted"> · {Math.round(missed)} s not screened</span>}
      </figcaption>
      <div className="coverage-bar" role="img" aria-label={missed >= 1 ? `${Math.round(missed)} seconds of the call were not screened` : 'All audio so far was screened'}>
        {spans.map((s, i) => (
          <span key={i} className={s.scored ? 'covered' : 'gap'}
            style={{ left: `${(s.start_s / span) * 100}%`, width: `${Math.max(0.4, ((s.end_s - s.start_s) / span) * 100)}%` }} />
        ))}
      </div>
      {degraded && <p className="muted small">The service is busy, so some audio is being skipped. The read may miss short phrases.</p>}
    </figure>
  );
}

/** Settled words in full, the still-changing tail in a lighter style. */
function LiveTranscript({ committed, tentative, active }: { committed: string; tentative: string; active: boolean }) {
  if (!committed && !tentative) return null;
  return (
    <figure className="live-transcript">
      <figcaption>What was said{active && <span className="muted"> · the last few words may still change</span>}</figcaption>
      <p>
        {committed}
        {tentative && <>{committed ? ' ' : ''}<span className="tentative">{tentative}</span></>}
      </p>
    </figure>
  );
}

/** Every concern raised during the call. An alert is withdrawn only when the claim it rested on changed. */
function AlertList({ alerts }: { alerts: StreamV2Alert[] }) {
  if (!alerts.length) return null;
  return (
    <section className="live-alerts" aria-label="Concerns raised during the call">
      <h2>Concerns raised</h2>
      <ul>
        {alerts.map(alert => (
          <li key={alert.alert_id} className={`tone-${BANDS[alert.band].tone}${alert.resolved ? ' resolved' : ''}`}>
            <WarningCircle size={18} weight="fill" aria-hidden="true" />
            <div>
              <p>{alert.evidence[0]?.explanation ?? BANDS[alert.band].headline}</p>
              <p className="muted small num">
                At {clock(Math.floor(alert.audio_start_s))}
                {alert.resolved && ' · withdrawn: the caller details it relied on changed'}
              </p>
            </div>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Trust over the course of the call, one point per server update, over the band intervals. */
function TrustTrace({ points, elapsed }: { points: LivePoint[]; elapsed: number }) {
  const span = Math.max(30, elapsed, ...points.map(p => p.at));
  const width = 600;
  const height = 120;
  const x = (t: number) => (t / span) * width;
  const y = (trust: number) => height - (trust / 100) * height;
  const scored = points.filter(p => p.trust != null) as (LivePoint & { trust: number })[];
  const path = scored.map((p, i) => `${i ? 'L' : 'M'}${x(p.at).toFixed(1)} ${y(p.trust).toFixed(1)}`).join(' ');

  return (
    <figure className="trace">
      <figcaption>Trust over the call</figcaption>
      <div className="trace-plot">
      <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={scored.length ? `Latest trust ${Math.round(scored.at(-1)!.trust)} of 100 after ${scored.length} updates` : 'No trust readings yet'}>
        {trustIntervals(points.some(p => p.band === 'verified')).map(zone => (
          <rect key={zone.label} x="0" width={width} y={y(zone.to)} height={y(zone.from) - y(zone.to)} className={`trace-zone tone-${zone.tone}`} />
        ))}
        {path && <path d={path} className="trace-line" vectorEffect="non-scaling-stroke" />}
      </svg>
      {scored.map((p, i) => (
        <span key={i} className={`trace-dot tone-${BANDS[p.band].tone}`} style={{ left: `${(x(p.at) / width) * 100}%`, top: `${(y(p.trust) / height) * 100}%` }} aria-hidden="true" />
      ))}
      </div>
      <div className="trace-axis num" aria-hidden="true"><span>0:00</span><span>{clock(span)}</span></div>
    </figure>
  );
}
