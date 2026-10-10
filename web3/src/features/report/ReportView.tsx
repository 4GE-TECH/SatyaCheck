import { useEffect, useRef, useState } from 'react';
import { ArrowSquareOut, Check, CopySimple, DownloadSimple, Printer, Question, SpeakerHigh, Stop } from '@phosphor-icons/react';
import type { EvidenceAnchor, ScreeningResponse } from '../../types/contracts';
import type { CheckRecord } from '../../app/workspace';
import { useEvidence } from '../../hooks/useEvidence';
import { downloadReportPdf, getReportPacket } from '../../lib/api';
import {
  BANDS, calm, displayBand, fixed, isDevanagari, languageName, markPhrases, measurements, reportText, safeLink, verifiable, when,
} from '../../lib/verdict';
import { EASE, ScrollTrigger, SplitText, gsap, reducedMotion, useGSAP } from '../../lib/motion';
import { Button, FlagBadge, Notice, ToneChip } from '../../components/ui';
import TrustScale from './TrustScale';
import Fusion from './Fusion';
import EvidenceScrubber from './EvidenceScrubber';

const SOURCE_LABEL = { upload: 'Uploaded file', clip: 'Recorded clip', live: 'Live listening', sample: 'Labelled sample', saved: 'Saved report' } as const;

export default function ReportView({ record, focus = true }: { record: CheckRecord; focus?: boolean }) {
  const { data } = record;
  const band = displayBand(data);
  const copy = BANDS[band];
  const sample = record.source === 'sample';
  const insufficient = band === 'insufficient';
  const evidence = useEvidence(record.audio);
  const root = useRef<HTMLElement>(null);
  const heading = useRef<HTMLHeadingElement>(null);
  const actions = insufficient
    ? ['Record more clear speech in a quiet place, then check again.']
    : data.fusion.recommended_actions.length
      ? data.fusion.recommended_actions.map(calm)
      : ['Verify unexpected requests through a phone number you already trust.'];

  useEffect(() => { if (focus) heading.current?.focus({ preventScroll: true }); }, [focus]);

  useGSAP(() => {
    if (reducedMotion()) return;
    // The verdict arrives first and fast: words rise from a mask, the wash blooms behind them.
    const words = SplitText.create('.verdict h1', { type: 'words', mask: 'words' });
    const tl = gsap.timeline({ defaults: { ease: EASE.out } });
    tl.from('.verdict-wash', { opacity: 0, scale: 1.08, duration: 1.4 }, 0)
      .from('.verdict .tone-chip', { y: 10, duration: 0.6 }, 0.05)
      .from(words.words, { yPercent: 110, duration: 0.9, stagger: 0.06 }, 0.1)
      .from('.verdict-summary, .verdict-meta', { y: 14, duration: 0.8, stagger: 0.08 }, 0.35)
      .from('.plan-steps li', { x: -14, duration: 0.7, stagger: 0.07 }, 0.45);

    // Later sections slide up as they enter. Opacity is never touched: content is always visible.
    ScrollTrigger.batch('.report .block', {
      start: 'top 92%',
      once: true,
      onEnter: batch => gsap.from(batch, { y: 36, duration: 1, stagger: 0.1, ease: EASE.out }),
    });
    return () => words.revert();
  }, { scope: root, dependencies: [data.session_id] });

  return (
    <article ref={root} className={`report tone-${copy.tone}`} aria-labelledby="verdict">
      {sample && <Notice>Labelled sample. This demonstrates a result type and does not describe your audio.</Notice>}

      <header className="bezel verdict-bezel">
        <div className="verdict">
          <div className="verdict-wash" aria-hidden="true" />
          <div className="verdict-main">
            <ToneChip tone={copy.tone} size="lg">{copy.label}</ToneChip>
            <h1 id="verdict" ref={heading} tabIndex={-1}>{copy.headline}</h1>
            <p className="verdict-summary">{insufficient ? data.quality.reason || copy.summary : copy.summary}</p>
            <dl className="verdict-meta">
              <div><dt>Recording</dt><dd className="ellipsis" title={record.name}>{record.name}</dd></div>
              <div><dt>Source</dt><dd>{data.caller_context?.channel_type === 'telephony' ? 'Phone call' : SOURCE_LABEL[record.source]}</dd></div>
              {(data.caller_context?.claimed_number || data.caller_context?.claimed_name) && (
                <div><dt>Caller ID</dt><dd className="num">{data.caller_context.claimed_number || data.caller_context.claimed_name}</dd></div>
              )}
              <div><dt>Received</dt><dd>{when(data.timestamp)}</dd></div>
              <div><dt>Language</dt><dd>{languageName(data.transcript.detected_language)}</dd></div>
            </dl>
          </div>
          <div className="verdict-score">
            {insufficient ? (
              <div className="no-score">
                <span className="no-score-mark num">—</span>
                <p><strong>No score given.</strong> A number on too little speech would be a guess, so SatyaCheck refuses to give one.</p>
              </div>
            ) : (
              <TrustScale score={data.fusion.trust_score} verified={verifiable(data)} />
            )}
          </div>
        </div>
      </header>

      <section className="plan" aria-label="What to do now">
        <ol className="plan-steps">
          {actions.map((action, i) => <li key={i} className={i === 0 ? 'plan-first' : undefined}>{action}</li>)}
        </ol>
        <div className="plan-side">
          {data.fusion.challenge_question?.question_text && (
            <div className="challenge">
              <p><Question size={22} weight="light" aria-hidden="true" />{data.fusion.challenge_question.question_text}</p>
              <small>A question only they would know. Pair it with a call back on a saved number.</small>
            </div>
          )}
          {data.fusion.vernacular_warning && <Spoken text={data.fusion.vernacular_warning} language={data.transcript.detected_language} />}
        </div>
      </section>

      <section className="block" aria-labelledby="fusion-title">
        <div className="block-head">
          <h2 id="fusion-title">How the score was formed</h2>
          <p>Three independent checks. Each shows its risk out of 100 and its weight in this check.</p>
        </div>
        <Fusion data={data} />
      </section>

      <section className="block" aria-labelledby="scrub-title">
        <div className="block-head">
          <h2 id="scrub-title">The recording, second by second</h2>
          <p>Every lane shares one timeline. Drag across it, or use the arrow keys, to see what was said and how it scored at each moment.</p>
        </div>
        <EvidenceScrubber data={data} evidence={evidence} />
      </section>

      <div className="block-pair">
        <section className="block" aria-labelledby="transcript-title">
          <div className="block-head">
            <h2 id="transcript-title">What was said</h2>
            <p>Transcribed automatically, so it can contain mistakes. Compare it with the recording.</p>
          </div>
          <Transcript data={data} />
        </section>

        <section className="block" aria-labelledby="measure-title">
          <div className="block-head">
            <h2 id="measure-title">Measurements</h2>
            <p>Each value against its reference. Below either quality minimum, no score is given.</p>
          </div>
          <table className="ref-table">
            <thead><tr><th scope="col">Measure</th><th scope="col">Result</th><th scope="col">Reference</th><th scope="col"><span className="sr-only">Flag</span></th></tr></thead>
            <tbody>
              {measurements(data).map(row => (
                <tr key={row.name}>
                  <th scope="row">{row.name}</th>
                  <td className="num">{row.value}</td>
                  <td className="muted">{row.reference}</td>
                  <td><FlagBadge flag={row.flag} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      </div>

      <section className="block" aria-labelledby="evidence-title">
        <div className="block-head">
          <h2 id="evidence-title">Evidence and sources</h2>
          <p>Each finding, the value observed, the threshold it was measured against, and where the rule comes from.</p>
        </div>
        {data.fusion.reason_codes.length ? (
          <ol className="evidence-list">
            {data.fusion.reason_codes.map(reason => {
              const link = safeLink(reason.citation_url);
              return (
                <li key={reason.code} className={`sev-${reason.severity}`}>
                  <div className="evidence-meta">
                    <span className="evidence-signal">{reason.signal}</span>
                    <span className="evidence-sev">{reason.severity}</span>
                  </div>
                  <div className="evidence-body">
                    <p>{reason.explanation}</p>
                    <dl className="evidence-values">
                      <div><dt>Observed</dt><dd>{reason.value || 'not supplied'}</dd></div>
                      {reason.threshold && <div><dt>Threshold</dt><dd>{reason.threshold}</dd></div>}
                    </dl>
                    {link && (
                      <a className="link" href={link} target="_blank" rel="noreferrer">
                        {reason.citation_title || 'Source'}<ArrowSquareOut size={15} aria-hidden="true" /><span className="sr-only"> (opens in a new tab)</span>
                      </a>
                    )}
                  </div>
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="empty-line">No evidence items were returned. Treat this result with extra caution.</p>
        )}
        {data.fusion.threat_label && (
          <p className="threat-line">
            This call resembles <strong>{data.fusion.threat_label.threat}</strong>
            <span className="muted"> · {data.fusion.threat_label.sector.replace(/_/g, ' ')}. A pattern, not a finding of fraud.</span>
          </p>
        )}
        {data.script.playbooks.length > 0 && (
          <div className="playbooks">
            <h3>Resembles these published scam patterns</h3>
            <ul>
              {data.script.playbooks.map(pb => {
                const link = safeLink(pb.source_url);
                return (
                  <li key={pb.playbook_id}>
                    <span className="playbook-sim num">{Math.round(pb.similarity_score * 100)}%</span>
                    <div><strong>{pb.title}</strong><span>{pb.source_agency}</span></div>
                    {link && <a className="link" href={link} target="_blank" rel="noreferrer">Read<ArrowSquareOut size={15} aria-hidden="true" /><span className="sr-only"> (opens in a new tab)</span></a>}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </section>

      <footer className="report-foot">
        <p>This is a record of returned signals and evidence. It is not an official complaint and not a determination of fraud.</p>
        <dl>
          <div><dt>Session</dt><dd className="mono">{data.session_id}</dd></div>
          <div><dt>Audio SHA-256</dt><dd className="mono">{sample ? 'sample digest, not a real recording' : data.audio_sha256 || 'not supplied'}</dd></div>
          <div><dt>Analysis time</dt><dd className="num">{fixed(data.processing_time_ms / 1000, 2)} s</dd></div>
          {(data.caller_context?.claimed_number || data.caller_context?.claimed_name) && (
            <div><dt>Caller ID</dt><dd className="mono">{data.caller_context.claimed_number || data.caller_context.claimed_name} (as received, not verified, never scored)</dd></div>
          )}
        </dl>
        {!sample && <EvidenceRecord sessionId={data.session_id} />}
      </footer>
    </article>
  );
}

/** The tamper-evident log anchor for this session's latest alert, when the service keeps an evidence log. */
function EvidenceRecord({ sessionId }: { sessionId: string }) {
  const [anchor, setAnchor] = useState<EvidenceAnchor | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    getReportPacket(sessionId, controller.signal).then(packet => {
      if (!controller.signal.aborted) setAnchor(packet?.evidence ?? null);
    });
    return () => controller.abort();
  }, [sessionId]);
  if (!anchor) return null;
  return (
    <details className="anchor">
      <summary>Tamper-evident record: alert logged as entry {anchor.leaf_index + 1} of {anchor.tree_size}</summary>
      <p className="muted small">
        Recomputing the root from the leaf hash and audit path (RFC 9162, section 2.1.3.2) proves the alert was logged and not
        altered. The log holds no audio or transcript.
      </p>
      <dl>
        <div><dt>Root</dt><dd className="mono">{anchor.root_hash}</dd></div>
        <div><dt>Leaf</dt><dd className="mono">{anchor.leaf_hash}</dd></div>
        {anchor.audit_path.map((hash, i) => <div key={i}><dt>Path {i + 1}</dt><dd className="mono">{hash}</dd></div>)}
      </dl>
    </details>
  );
}

function Transcript({ data }: { data: ScreeningResponse }) {
  const runs = markPhrases(data.transcript.text, data);
  if (!runs.length) return <p className="empty-line">No transcript is available for this recording.</p>;
  return (
    <>
      <blockquote className="transcript" dir="auto" lang={isDevanagari(data.transcript.text) ? 'hi' : undefined}>
        {runs.map((run, i) => run.kind ? (
          <mark key={i} className={`m-${run.kind}`} title={run.note}>
            {run.text}<span className="sr-only"> ({run.kind === 'concern' ? 'concerning' : 'reassuring'}: {run.note})</span>
          </mark>
        ) : <span key={i}>{run.text}</span>)}
      </blockquote>
      <ul className="marker-notes">
        {data.script.incriminating_markers.map(m => <li key={m.marker_id} className="m-concern"><b>Concerning</b>{m.description || m.category}</li>)}
        {data.script.exculpatory_markers.map(m => <li key={m.marker_id} className="m-reassure"><b>Reassuring</b>{m.description || m.category}</li>)}
      </ul>
    </>
  );
}

function Spoken({ text, language }: { text: string; language: string }) {
  const [speaking, setSpeaking] = useState(false);
  const [problem, setProblem] = useState('');
  useEffect(() => () => { if ('speechSynthesis' in window) window.speechSynthesis.cancel(); }, []);

  function speak() {
    if (!('speechSynthesis' in window)) { setProblem('Spoken guidance is not available in this browser.'); return; }
    if (speaking) { window.speechSynthesis.cancel(); setSpeaking(false); return; }
    const lang = isDevanagari(text) || language.startsWith('hi') ? 'hi' : 'en';
    const voice = window.speechSynthesis.getVoices().find(v => v.localService && v.lang.startsWith(lang));
    if (!voice) { setProblem('No offline voice for this language is installed on this device.'); return; }
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = 0.9;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => { setSpeaking(false); setProblem('Could not play the spoken guidance.'); };
    setProblem('');
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  }

  return (
    <div className="spoken">
      <p lang={isDevanagari(text) ? 'hi' : undefined}>{text}</p>
      <Button size="sm" onClick={speak}>
        {speaking ? <Stop size={15} weight="fill" aria-hidden="true" /> : <SpeakerHigh size={16} weight="light" aria-hidden="true" />}
        {speaking ? 'Stop' : 'Read aloud'}
      </Button>
      {problem && <small role="status">{problem}</small>}
    </div>
  );
}

export function ReportActions({ record }: { record: CheckRecord }) {
  const [copied, setCopied] = useState(false);
  const [downloading, setDownloading] = useState(false);
  const [problem, setProblem] = useState('');
  const timer = useRef<number | undefined>(undefined);
  const sample = record.source === 'sample';
  useEffect(() => () => window.clearTimeout(timer.current), []);

  async function copySummary() {
    setProblem('');
    try {
      await navigator.clipboard.writeText(reportText(record.data, sample));
      setCopied(true);
      window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => setCopied(false), 2400);
    } catch {
      setProblem('Clipboard access is unavailable here. Use Print instead.');
    }
  }

  async function download() {
    setDownloading(true);
    setProblem('');
    try { await downloadReportPdf(record.data.session_id); }
    catch (error) { setProblem(error instanceof Error ? error.message : 'Could not download the PDF. Use Print instead.'); }
    finally { setDownloading(false); }
  }

  return (
    <div className="report-actions">
      <Button size="sm" onClick={copySummary}>
        {copied ? <Check size={16} weight="bold" aria-hidden="true" /> : <CopySimple size={16} weight="light" aria-hidden="true" />}
        {copied ? 'Copied' : 'Copy summary'}
      </Button>
      <Button size="sm" onClick={() => window.print()}><Printer size={16} weight="light" aria-hidden="true" />Print</Button>
      {!sample && (
        <Button size="sm" busy={downloading} onClick={download}>
          {!downloading && <DownloadSimple size={16} weight="light" aria-hidden="true" />}PDF from service
        </Button>
      )}
      <span className="sr-only" role="status">{copied ? 'Summary copied' : ''}</span>
      {problem && <div className="report-actions-problem"><Notice tone="danger">{problem}</Notice></div>}
    </div>
  );
}
