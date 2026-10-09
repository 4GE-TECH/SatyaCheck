import { Link } from 'react-router-dom';
import { ArrowRight, Phone, ExternalLink } from 'lucide-react';
import { PageHeading } from '../components/Primitives';

const results = [
  { label: 'Voice verified', tone: 'success', text: 'The voice matched someone you enrolled. It does not make the request safe: still verify anything unexpected.' },
  { label: 'Caution', tone: 'warning', text: 'Something deserves a closer look. Confirm the request through a number you trust before acting.' },
  { label: 'Suspicious / High risk', tone: 'danger', text: 'Several signals raise concern. Do not send money or share codes. Call the person back on their saved number.' },
  { label: 'Unverified', tone: 'neutral', text: 'No enrolled voice matched. That is normal for banks, delivery agents and doctors, and is not a sign of fraud on its own.' },
  { label: 'Insufficient audio', tone: 'neutral', text: 'Too little clear speech to report. No score is given. Record longer, closer, in a quieter place.' },
] as const;

export default function HelpPage() {
  return (
    <div className="page-stack help-page">
      <PageHeading title="How to read a report" description="What a check can tell you, what it cannot, and what to do next." />
      <div className="help-grid">
        <article className="panel help-article">
          <section>
            <h2>Results, in plain words</h2>
            <dl className="help-results">
              {results.map(r => (
                <div key={r.label}>
                  <dt><span className={`band-badge tone-${r.tone}`}>{r.label}</span></dt>
                  <dd>{r.text}</dd>
                </div>
              ))}
            </dl>
          </section>
          <section>
            <h2>Flags in the results table</h2>
            <p><strong>H</strong> marks a signal that raised concern. <strong>L</strong> marks a quality measure below the minimum. <strong>OK</strong> is within what is expected, and <strong>—</strong> means the signal was not assessed, for example when no one is enrolled.</p>
            <p>Synthetic speech alone is not treated as fraud. Banks use automated voices legitimately, so it only counts when the request is also concerning.</p>
          </section>
          <section>
            <h2>Getting audio in</h2>
            <p>Upload a saved recording or voice note, record a clip, or listen live from a second device placed near a phone on speaker. A phone that is in a cellular call cannot hear that call: Android gives other apps silence.</p>
            <Link className="text-link" to="/">Check a recording<ArrowRight size={16} aria-hidden="true" /></Link>
          </section>
          <section>
            <h2>Your recordings and known voices</h2>
            <p>Audio is sent to your configured screening service for analysis, and enrolled voiceprints are stored there. Ask the service operator about access, retention and deletion. This interface does not set those policies.</p>
            <p>Reports listed under “This session” live in memory until the page is closed. Keep the session ID to retrieve a stored report later.</p>
          </section>
        </article>
        <aside className="help-aside">
          <h2>If something feels wrong</h2>
          <ol>
            <li>Pause. Don’t send money or share an OTP.</li>
            <li>Hang up and call back on a number you already trust.</li>
            <li>Ask something only the real person would know.</li>
          </ol>
          <a className="button button-primary" href="tel:1930"><Phone size={17} aria-hidden="true" />Call 1930</a>
          <a className="text-link" href="https://cybercrime.gov.in" target="_blank" rel="noreferrer">
            Report at cybercrime.gov.in<ExternalLink size={15} aria-hidden="true" /><span className="visually-hidden"> (opens a new tab)</span>
          </a>
        </aside>
      </div>
    </div>
  );
}
