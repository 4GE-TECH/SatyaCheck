import { useEffect, useRef, useState } from 'react';
import { ExternalLink, Square, Volume2 } from 'lucide-react';
import type { ScreeningResponse } from '../types/contracts';
import {
  bands, date, displayBand, highlightTranscript, isDevanagari, language, number, percent,
  qualityRows, safeLink, signalRows, reportIntervals,
} from '../lib/presentation';
import { BandBadge, Button, FlagMark, RangeBar } from './Primitives';

export type ReportStatus = 'final' | 'provisional' | 'sample' | 'interrupted';

interface Props {
  data: ScreeningResponse;
  status: ReportStatus;
  name?: string;
  audioUrl?: string | null;
  /** Focus the interpretation heading on mount, so screen readers land on the verdict. */
  focusHeading?: boolean;
}

const statusText: Record<ReportStatus, string> = {
  final: 'Final',
  provisional: 'Provisional · updating',
  sample: 'Sample · demonstration',
  interrupted: 'Provisional · interrupted',
};

export default function ReportSheet({ data, status, name, audioUrl, focusHeading = false }: Props) {
  const band = displayBand(data);
  const config = bands[band];
  const insufficient = band === 'insufficient';
  const heading = useRef<HTMLHeadingElement>(null);
  const [first, ...otherActions] = data.fusion.recommended_actions;

  useEffect(() => {
    if (focusHeading) heading.current?.focus();
  }, [focusHeading]);

  return (
    <article className={`report-sheet status-${status}`} aria-labelledby="report-verdict">
      <header className="sheet-head">
        <div className="sheet-title">
          <h2>Screening report</h2>
          <span className={`sheet-status ${status}`}>{statusText[status]}</span>
        </div>
        <dl className="sheet-details">
          <div><dt>Recording</dt><dd className="truncate" title={name}>{name || 'Screened audio'}</dd></div>
          <div><dt>Received</dt><dd>{date(data.timestamp)}</dd></div>
          <div><dt>Check type</dt><dd>{data.fusion.mode === 'authority_check' ? 'Authority check' : 'Identity check'}</dd></div>
          <div><dt>Language</dt><dd>{language(data.transcript.detected_language)}</dd></div>
          <div className="wide"><dt>Session ID</dt><dd className="mono">{data.session_id}</dd></div>
        </dl>
      </header>

      <section className={`interpretation tone-${config.tone}`} aria-live={status === 'provisional' ? 'polite' : undefined}>
        <div className="interpretation-text">
          <BandBadge tone={config.tone}>{config.label}</BandBadge>
          <h1 id="report-verdict" ref={heading} tabIndex={-1}>{config.title}</h1>
          <p>{insufficient ? data.quality.reason || config.description : config.description}</p>
          {band === 'verified' && data.speaker.matched_person_name && (
            <p className="matched-name">Matched voice: <strong>{data.speaker.matched_person_name}</strong></p>
          )}
        </div>
        <div className="trust-readout">
          {insufficient ? (
            <>
              <span className="readout-label">Trust score</span>
              <strong className="readout-qns">Not reported</strong>
              <span className="readout-note">Quantity of speech not sufficient. No score is given.</span>
            </>
          ) : (
            <>
              <span className="readout-label">Trust score</span>
              <strong className="readout-value">
                {Math.round(data.fusion.trust_score)}<small>/100</small>
              </strong>
              <RangeBar
                value={data.fusion.trust_score}
                zones={reportIntervals(data)}
                label={`Trust score ${Math.round(data.fusion.trust_score)} on a 0 to 100 scale`}
              />
              <div className="range-scale" aria-hidden="true">
                <span>0</span><span style={{ left: '35%' }}>35</span><span style={{ left: '60%' }}>60</span><span style={{ left: '85%' }}>85</span><span>100</span>
              </div>
              <span className="readout-note">Higher means more trust. Not a probability or a guarantee.</span>
            </>
          )}
        </div>
      </section>

      <section className="next-step" aria-labelledby="next-step-heading">
        <h3 id="next-step-heading">Your next step</h3>
        {insufficient ? (
          <h4 className="next-primary">Record more clear speech in a quiet place, then check again.</h4>
        ) : first ? (
          <>
            <h4 className="next-primary">{first}</h4>
            {otherActions.length > 0 && (
              <ol className="next-list" start={2}>
                {otherActions.map((action, index) => <li key={index}>{action}</li>)}
              </ol>
            )}
          </>
        ) : (
          <h4 className="next-primary">Verify unexpected requests through a phone number you already trust.</h4>
        )}
        {data.fusion.challenge_question?.question_text && (
          <div className="challenge">
            <span className="challenge-label">Ask a verification question</span>
            <p>{data.fusion.challenge_question.question_text}</p>
            <small>Use it as one check, alongside an independent callback.</small>
          </div>
        )}
      </section>

      {data.fusion.vernacular_warning && <SpokenGuidance data={data} />}

      <section className="sheet-section" aria-labelledby="results-heading">
        <div className="section-head">
          <h3 id="results-heading">Results</h3>
          <span className="section-note">Risk is 0–100; lower is better. Weight is each signal’s share of the trust score.</span>
        </div>
        {insufficient ? (
          <p className="not-reported">Signal results are not reported because the recording did not pass the quality check.</p>
        ) : (
          <div className="table-scroll">
            <table className="results-table">
              <thead>
                <tr><th scope="col">Test</th><th scope="col">Result</th><th scope="col" className="signal-reference">Reference</th><th scope="col" className="col-risk">Risk</th><th scope="col" className="col-num">Weight</th><th scope="col" className="col-flag">Flag</th></tr>
              </thead>
              <tbody>
                {signalRows(data).map(row => (
                  <tr key={row.key} className={`flag-${row.flag.tone}`}>
                    <th scope="row">
                      <span className="test-name">{row.test}</span>
                      <span className="test-question">{row.question}</span>
                    </th>
                    <td>
                      <span className="result-value" key={row.result}>{row.result}</span>
                      <span className="result-detail">{row.detail}</span>
                    </td>
                    <td className="signal-reference">
                      <span className="reference-label">Reference</span>
                      {row.reference ? <>
                        <span className="reference-threshold">{row.reference.threshold}</span>
                        <span className="result-detail">Observed: {row.reference.observed}</span>
                        {row.reference.interval && <div className="evidence-interval" role="img" aria-label={`Observed ${row.reference.interval.value} percent; supplied reference ${row.reference.threshold}`}>
                          <span className="evidence-above" style={{ left: `${row.reference.interval.threshold}%` }} />
                          <span className="evidence-limit" style={{ left: `${row.reference.interval.threshold}%` }} />
                          <span className="evidence-value" style={{ left: `${row.reference.interval.value}%` }} />
                        </div>}
                      </> : <span className="result-detail">Reference not supplied</span>}
                    </td>
                    <td className="col-risk">
                      <span className="risk-number" key={percent(row.risk)}>{percent(row.risk)}</span>
                      <RangeBar value={row.risk == null ? null : row.risk * 100} label={`${row.test} risk ${percent(row.risk)} of 100`} invert />
                    </td>
                    <td className="col-num">{percent(row.weight)}%</td>
                    <td className="col-flag" key={row.flag.mark}><FlagMark flag={row.flag} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      <section className="sheet-section" aria-labelledby="quality-heading">
        <div className="section-head"><h3 id="quality-heading">Recording quality</h3></div>
        <div className="table-scroll">
          <table className="results-table compact">
            <thead><tr><th scope="col">Test</th><th scope="col" className="col-num">Result</th><th scope="col" className="col-num col-ref">Reference</th><th scope="col" className="col-flag">Flag</th></tr></thead>
            <tbody>
              {qualityRows(data).map(row => (
                <tr key={row.test}>
                  <th scope="row"><span className="test-name">{row.test}</span></th>
                  <td className="col-num">{row.result}<span className="inline-ref">{row.reference}</span></td>
                  <td className="col-num col-ref muted">{row.reference}</td>
                  <td className="col-flag"><FlagMark flag={row.flag} /></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <AuthenticityStrip data={data} audioUrl={audioUrl} />

      <section className="sheet-section" aria-labelledby="transcript-heading">
        <div className="section-head">
          <h3 id="transcript-heading">Transcript</h3>
          <span className="section-note">Automatic, and can contain errors. Compare it with the recording.</span>
        </div>
        <Transcript data={data} />
      </section>

      <section className="sheet-section" aria-labelledby="remarks-heading">
        <div className="section-head"><h3 id="remarks-heading">Remarks</h3></div>
        {data.fusion.reason_codes.length ? (
          <ol className="remarks">
            {data.fusion.reason_codes.map(reason => {
              const link = safeLink(reason.citation_url);
              return (
                <li key={reason.code}>
                  <div className="remark-meta">
                    <span className="remark-signal">{reason.signal}</span>
                    <span className={`remark-severity sev-${reason.severity}`}>{reason.severity}</span>
                  </div>
                  <p>{reason.explanation}</p>
                  <dl className="remark-values">
                    <div><dt>Observed</dt><dd>{reason.value || 'Not supplied'}</dd></div>
                    {reason.threshold != null && <div><dt>Threshold</dt><dd>{reason.threshold}</dd></div>}
                  </dl>
                  {link && (
                    <a className="text-link" href={link} target="_blank" rel="noreferrer">
                      {reason.citation_title || 'Read source'}<ExternalLink size={14} aria-hidden="true" />
                      <span className="visually-hidden"> (opens a new tab)</span>
                    </a>
                  )}
                </li>
              );
            })}
          </ol>
        ) : (
          <p className="not-reported">No reason codes were returned. Treat this result with caution.</p>
        )}
        {data.script.playbooks.length > 0 && (
          <div className="advisories">
            <h4>Similar published advisories</h4>
            <ul>
              {data.script.playbooks.map(playbook => {
                const link = safeLink(playbook.source_url);
                return (
                  <li key={playbook.playbook_id}>
                    <div>
                      <strong>{playbook.title}</strong>
                      <span>{playbook.source_agency} · similarity {percent(playbook.similarity_score)}%</span>
                    </div>
                    {link && (
                      <a className="text-link" href={link} target="_blank" rel="noreferrer">
                        Source<ExternalLink size={14} aria-hidden="true" /><span className="visually-hidden"> (opens a new tab)</span>
                      </a>
                    )}
                  </li>
                );
              })}
            </ul>
          </div>
        )}
      </section>

      <footer className="sheet-foot">
        <p>A record of returned signals and evidence. This is not an official complaint or a determination of fraud.</p>
        <dl>
          <div><dt>Audio SHA-256</dt><dd className="mono">{status === 'sample' ? 'Sample digest, not a real recording' : data.audio_sha256 || 'Not supplied'}</dd></div>
          <div><dt>Processing time</dt><dd>{number(data.processing_time_ms / 1000, ' s', 2)}</dd></div>
        </dl>
        <span className="end-mark">End of report</span>
      </footer>
    </article>
  );
}

function Transcript({ data }: { data: ScreeningResponse }) {
  const runs = highlightTranscript(data);
  if (!runs.length) return <p className="not-reported">No transcript is available for this recording.</p>;
  const hasConcern = runs.some(run => run.kind === 'concern');
  const hasReassure = runs.some(run => run.kind === 'reassure');
  return (
    <>
      <blockquote className="transcript" dir="auto" lang={isDevanagari(data.transcript.text) ? 'hi' : undefined}>
        {runs.map((run, index) => run.kind ? (
          <mark key={index} className={run.kind} title={run.note}>
            {run.text}
            <span className="visually-hidden"> ({run.kind === 'concern' ? 'concerning phrase' : 'reassuring phrase'}: {run.note})</span>
          </mark>
        ) : <span key={index}>{run.text}</span>)}
      </blockquote>
      {(hasConcern || hasReassure) && (
        <ul className="transcript-legend" aria-hidden="true">
          {hasConcern && <li><mark className="concern">Concerning</mark> pressure, isolation or payment demands</li>}
          {hasReassure && <li><mark className="reassure">Reassuring</mark> invitations to verify</li>}
        </ul>
      )}
    </>
  );
}

function AuthenticityStrip({ data, audioUrl }: { data: ScreeningResponse; audioUrl?: string | null }) {
  const [time, setTime] = useState<number | null>(null);
  const segments = [...data.spoof.timeline].sort((a, b) => a.start_s - b.start_s);
  const total = Math.max(0, ...segments.map(segment => segment.end_s));
  return (
    <section className="sheet-section" aria-labelledby="authenticity-heading">
      <div className="section-head">
        <h3 id="authenticity-heading">Authenticity over time</h3>
        <span className="section-note">Bar height is the model’s segment score, not a probability of fraud.</span>
      </div>
      {total > 0 ? (
        <>
          <div className="strip" role="img" aria-label={`${segments.filter(s => s.is_synthetic).length} of ${segments.length} segments carry a synthetic signal`}>
            <span className="strip-threshold" style={{ bottom: '40%' }} />
            {segments.map((segment, index) => {
              const end = segments[index + 1] ? Math.min(segments[index + 1].start_s, segment.end_s) : segment.end_s;
              return (
                <span
                  key={index}
                  className={`strip-bar ${segment.is_synthetic ? 'synthetic' : 'ordinary'}`}
                  style={{
                    left: `${(segment.start_s / total) * 100}%`,
                    width: `calc(${(Math.max(0, end - segment.start_s) / total) * 100}% - 2px)`,
                    transform: `scaleY(${Math.max(.04, Math.min(1, segment.score))})`,
                  }}
                  title={`${number(segment.start_s)}–${number(segment.end_s, ' s')} · score ${number(segment.score, '', 2)}`}
                />
              );
            })}
            {time != null && (
              <span className="strip-position" style={{ transform: `translateX(${Math.min(100, (time / total) * 100)}%)` }}>
                <span className="strip-playhead" />
              </span>
            )}
          </div>
          <div className="strip-scale" aria-hidden="true"><span>0 s</span><span>{number(total, ' s')}</span></div>
          {audioUrl && (
            <audio
              className="strip-audio"
              src={audioUrl}
              controls
              preload="metadata"
              aria-label="Play the recording against the authenticity timeline"
              onTimeUpdate={event => setTime(event.currentTarget.currentTime)}
              onEnded={() => setTime(null)}
            />
          )}
          <dl className="metric-row">
            <div><dt>Median</dt><dd>{number(data.spoof.median_score, '', 2)}</dd></div>
            <div><dt>Peak</dt><dd>{number(data.spoof.peak_score, '', 2)}</dd></div>
            <div><dt>Longest synthetic run</dt><dd>{number(data.spoof.max_synth_run_s, ' s')}</dd></div>
          </dl>
        </>
      ) : (
        <p className="not-reported">No segment timeline was returned. Authenticity may be unavailable for this recording.</p>
      )}
    </section>
  );
}

function SpokenGuidance({ data }: { data: ScreeningResponse }) {
  const [speaking, setSpeaking] = useState(false);
  const [problem, setProblem] = useState('');
  const warning = data.fusion.vernacular_warning!;
  useEffect(() => () => { if ('speechSynthesis' in window) window.speechSynthesis.cancel(); }, []);

  function speak() {
    if (!('speechSynthesis' in window)) { setProblem('Spoken guidance is not available in this browser.'); return; }
    if (speaking) { window.speechSynthesis.cancel(); setSpeaking(false); return; }
    const lang = isDevanagari(warning) || data.transcript.detected_language.startsWith('hi') ? 'hi' : 'en';
    const voice = window.speechSynthesis.getVoices().find(v => v.localService && v.lang.startsWith(lang));
    if (!voice) { setProblem('A matching offline voice is not installed on this device.'); return; }
    const utterance = new SpeechSynthesisUtterance(warning);
    utterance.voice = voice;
    utterance.lang = voice.lang;
    utterance.rate = 0.9;
    utterance.onend = () => setSpeaking(false);
    utterance.onerror = () => { setSpeaking(false); setProblem('Could not play spoken guidance.'); };
    setProblem('');
    setSpeaking(true);
    window.speechSynthesis.speak(utterance);
  }

  return (
    <section className="guidance" aria-labelledby="guidance-heading">
      <div>
        <h3 id="guidance-heading">Guidance to read aloud</h3>
        <p lang={isDevanagari(warning) ? 'hi' : undefined}>{warning}</p>
        {problem && <p className="guidance-problem" role="status">{problem}</p>}
      </div>
      <Button variant="secondary" onClick={speak}>
        {speaking ? <Square size={16} aria-hidden="true" /> : <Volume2 size={18} aria-hidden="true" />}
        {speaking ? 'Stop' : 'Listen'}
      </Button>
    </section>
  );
}
