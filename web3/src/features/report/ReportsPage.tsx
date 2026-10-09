import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { ArrowRight, Files, MagnifyingGlass } from '@phosphor-icons/react';
import { useWorkspace } from '../../app/workspace';
import { BANDS, displayBand, when } from '../../lib/verdict';
import { Button, ButtonLink, ToneChip } from '../../components/ui';

const SOURCE = { upload: 'Upload', clip: 'Clip', live: 'Live', sample: 'Sample', saved: 'Saved' } as const;

export default function ReportsPage() {
  const { records } = useWorkspace();
  const navigate = useNavigate();
  const [lookup, setLookup] = useState('');

  return (
    <div className="page reports-page">
      <header className="page-head">
        <h1>Reports</h1>
        <p>Reopen a check, copy its summary, or print it as evidence for your bank or the cybercrime helpline.</p>
      </header>

      <div className="reports-grid">
        <section className="panel" aria-labelledby="session-title">
          <div className="panel-head"><h2 id="session-title">This session</h2><span className="muted small">Kept in memory until you close this tab</span></div>
          {records.length ? (
            <div className="table-wrap">
              <table className="report-table">
                <thead><tr><th scope="col">Recording</th><th scope="col">Source</th><th scope="col">Received</th><th scope="col">Result</th><th scope="col" className="right">Trust</th></tr></thead>
                <tbody>
                  {records.map(record => {
                    const band = displayBand(record.data);
                    return (
                      <tr key={record.data.session_id} onClick={() => navigate(`/report/${encodeURIComponent(record.data.session_id)}`)}>
                        <th scope="row"><Link to={`/report/${encodeURIComponent(record.data.session_id)}`} className="row-link ellipsis">{record.name}</Link></th>
                        <td>{SOURCE[record.source]}</td>
                        <td>{when(record.data.timestamp)}</td>
                        <td><ToneChip tone={BANDS[band].tone}>{BANDS[band].label}</ToneChip></td>
                        <td className="right num">{band === 'insufficient' ? '—' : Math.round(record.data.fusion.trust_score)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <div className="people-empty">
              <Files size={36} weight="duotone" aria-hidden="true" />
              <h3>No reports yet</h3>
              <p>Each check you run in this tab appears here.</p>
              <ButtonLink to="/" variant="primary">Check a recording<ArrowRight size={16} weight="bold" aria-hidden="true" /></ButtonLink>
            </div>
          )}
        </section>

        <section className="panel lookup" aria-labelledby="lookup-title">
          <div className="panel-head"><h2 id="lookup-title">Open a saved report</h2></div>
          <form className="panel-pad lookup-form" onSubmit={event => { event.preventDefault(); if (lookup.trim()) navigate(`/report/${encodeURIComponent(lookup.trim())}`); }}>
            <div className="field">
              <label htmlFor="session-id">Session ID</label>
              <input id="session-id" className="input mono" required spellCheck={false} value={lookup} onChange={e => setLookup(e.target.value)} placeholder="session_…" />
              <span className="hint">Fetched from the same screening service that ran the check. Saved reports don’t include the audio.</span>
            </div>
            <Button type="submit" variant="primary"><MagnifyingGlass size={16} weight="bold" aria-hidden="true" />Open report</Button>
          </form>
        </section>
      </div>
    </div>
  );
}
