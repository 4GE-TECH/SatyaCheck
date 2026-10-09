import { useEffect, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ArrowLeft, FileText, Search } from 'lucide-react';
import { useWorkspace, type CheckRecord } from '../context/workspace-state';
import { getScreening } from '../api/client';
import { bands, date, displayBand } from '../lib/presentation';
import { PageHeading, Button, Notice, EmptyState, BandBadge } from '../components/Primitives';
import ReportSheet from '../components/ReportSheet';
import ReportActions from '../components/ReportActions';

export default function ReportPage() {
  const [params] = useSearchParams();
  return <ReportContent key={params.get('session') || 'list'} />;
}

function ReportContent() {
  const [params, setParams] = useSearchParams();
  const session = params.get('session');
  const { records } = useWorkspace();
  const cached = records.find(r => r.data.session_id === session);
  const [fetched, setFetched] = useState<CheckRecord | null>(null);
  const [loading, setLoading] = useState(Boolean(session && !cached));
  const [error, setError] = useState('');
  const [lookup, setLookup] = useState('');
  const [retry, setRetry] = useState(0);
  const record = cached || fetched;

  useEffect(() => {
    if (!session || cached) return;
    const controller = new AbortController();
    getScreening(session, controller.signal)
      .then(data => setFetched({ data, name: 'Saved screening', demo: false }))
      .catch(problem => { if (!controller.signal.aborted) setError(problem.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [session, cached, retry]);

  if (session) {
    return (
      <div className="page-stack">
        <div className="result-toolbar">
          <Link className="text-link" to="/report"><ArrowLeft size={17} aria-hidden="true" />All reports</Link>
          {record && <div className="toolbar-end"><ReportActions data={record.data} demo={record.demo} /></div>}
        </div>
        {loading && (
          <div className="report-sheet skeleton-sheet" role="status" aria-label="Retrieving the saved report">
            <span /><span /><span /><span />
          </div>
        )}
        {error && (
          <Notice tone="danger">
            {error}
            <div className="button-row">
              <Button variant="secondary" onClick={() => { setError(''); setLoading(true); setRetry(n => n + 1); }}>Try again</Button>
              <Link className="text-link" to="/report">Choose another report</Link>
            </div>
          </Notice>
        )}
        {record && (
          <>
            {record.demo && <Notice>Sample report. Demonstration data, not evidence of a real incident.</Notice>}
            <ReportSheet data={record.data} status={record.demo ? 'sample' : 'final'} name={record.name} />
          </>
        )}
      </div>
    );
  }

  return (
    <div className="page-stack">
      <PageHeading
        title="Reports"
        description="Reopen a check, copy its summary, or print it as evidence for a bank or the cybercrime helpline."
      />
      <div className="report-index">
        <section className="panel" aria-labelledby="session-reports">
          <div className="panel-head"><h2 id="session-reports">This session</h2></div>
          {records.length ? (
            <div className="table-scroll">
              <table className="data-table">
                <thead><tr><th scope="col">Recording</th><th scope="col">Received</th><th scope="col">Result</th><th scope="col" className="col-num">Trust</th></tr></thead>
                <tbody>
                  {records.map(r => {
                    const band = displayBand(r.data);
                    return (
                      <tr key={r.data.session_id}>
                        <th scope="row">
                          <Link className="row-link" to={`/report?session=${encodeURIComponent(r.data.session_id)}`}><span className="truncate">{r.name}</span></Link>
                        </th>
                        <td>{r.demo ? 'Sample data' : date(r.data.timestamp)}</td>
                        <td><BandBadge tone={bands[band].tone}>{bands[band].label}</BandBadge></td>
                        <td className="col-num">{band === 'insufficient' ? '—' : Math.round(r.data.fusion.trust_score)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ) : (
            <EmptyState icon={<FileText size={24} />} title="A report starts with a check">
              <p>Check a recording first. Its report holds the actual transcript and returned evidence.</p>
              <Link className="text-link" to="/">Check audio</Link>
            </EmptyState>
          )}
        </section>

        <section className="panel" aria-labelledby="lookup-heading">
          <div className="panel-head"><h2 id="lookup-heading">Open a saved report</h2></div>
          <form className="panel-body lookup" onSubmit={event => { event.preventDefault(); if (lookup.trim()) setParams({ session: lookup.trim() }); }}>
            <div className="field">
              <label htmlFor="session-id">Session ID</label>
              <input id="session-id" required value={lookup} onChange={e => setLookup(e.target.value)} placeholder="session_…" className="mono" spellCheck={false} />
              <small>Retrieved from the same screening service that ran the check.</small>
            </div>
            <Button type="submit"><Search size={17} aria-hidden="true" />Find report</Button>
          </form>
        </section>
      </div>
    </div>
  );
}
