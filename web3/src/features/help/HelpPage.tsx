import { ArrowSquareOut, Phone } from '@phosphor-icons/react';
import { ButtonAnchor, ToneChip } from '../../components/ui';
import type { Tone } from '../../lib/verdict';

const RESULTS: { label: string; tone: Tone; text: string }[] = [
  { label: 'Voice verified', tone: 'safe', text: 'The voice matched someone you enrolled. That doesn’t make the request safe: still verify anything unexpected.' },
  { label: 'Caution', tone: 'caution', text: 'Something deserves a closer look. Confirm through a number you trust before acting.' },
  { label: 'Suspicious', tone: 'danger', text: 'Concerning signals were found. Call the person back on their saved number before doing anything.' },
  { label: 'High risk', tone: 'danger', text: 'Several signals agree. Don’t send money or share an OTP. Hang up and verify independently.' },
  { label: 'Unverified', tone: 'neutral', text: 'No enrolled voice matched. That is normal for banks, couriers and doctors, and is not a warning on its own.' },
  { label: 'Not enough audio', tone: 'neutral', text: 'Too little clear speech to judge, so no score is given. Record longer, closer, somewhere quieter.' },
];

export default function HelpPage() {
  return (
    <div className="page help-page">
      <header className="page-head">
        <h1>How to read a report</h1>
        <p>What a check can tell you, what it can’t, and what to do next.</p>
      </header>
      <div className="help-grid">
        <article className="help-body">
          <section>
            <h2>The six results</h2>
            <dl className="result-key">
              {RESULTS.map(r => (
                <div key={r.label}><dt><ToneChip tone={r.tone}>{r.label}</ToneChip></dt><dd>{r.text}</dd></div>
              ))}
            </dl>
          </section>
          <section>
            <h2>Flags</h2>
            <p><b>Concern</b> marks a finding that raised concern. <b>Below minimum</b> marks a quality measure under its threshold. <b>Expected</b> means as expected. <b>Not assessed</b> means the check did not apply, for example when no one is enrolled. <b>Not trusted</b> means the voice resembles someone you enrolled, but it was flagged as synthetic or replayed, so the match is not treated as verification.</p>
          </section>
          <section>
            <h2>Why a synthetic voice isn’t automatically bad</h2>
            <p>Banks and delivery services use automated voices every day. SatyaCheck only lets a synthetic voice count in proportion to what is being asked. A robotic “your parcel is arriving” stays calm; a cloned “send money now and tell no one” does not.</p>
          </section>
          <section>
            <h2>Getting audio in</h2>
            <p>Upload a recording or voice note, record a clip, or listen live from a second device near a phone on speaker. A phone that is in a cellular call cannot hear that call: Android hands other apps silence.</p>
          </section>
          <section>
            <h2>Your audio and known voices</h2>
            <p>Audio goes to your configured screening service, and voiceprints are stored there. Ask whoever runs it about retention and deletion. Reports listed in this tab live in memory only, so keep the session ID if you need one later.</p>
          </section>
        </article>
        <aside className="help-aside">
          <h2>If a call feels wrong</h2>
          <ol>
            <li>Pause. Don’t send money or share an OTP.</li>
            <li>Hang up and call back on a number you already have.</li>
            <li>Ask something only the real person would know.</li>
            <li>Report it. You are not the first, and it helps the next family.</li>
          </ol>
          <ButtonAnchor href="tel:1930" variant="primary" size="lg"><Phone size={18} weight="fill" aria-hidden="true" />Call 1930</ButtonAnchor>
          <a className="link" href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
            Report at cybercrime.gov.in<ArrowSquareOut size={15} aria-hidden="true" /><span className="sr-only"> (opens in a new tab)</span>
          </a>
        </aside>
      </div>
    </div>
  );
}
