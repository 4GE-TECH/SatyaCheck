import { useEffect, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { Files } from '@phosphor-icons/react';
import { CHANNELS, getCalls, whoLabel, type CallRow } from '../../lib/admin';
import { BANDS, when } from '../../lib/verdict';
import { Button, Notice, Skeleton, ToneChip } from '../../components/ui';

export default function CallHistoryPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const owner = params.get('owner');
  const channel = params.get('channel');
  const [items, setItems] = useState<CallRow[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [state, setState] = useState<'loading' | 'ready' | 'more' | 'error'>('loading');
  const [error, setError] = useState('');

  async function load(after: string | null, signal?: AbortSignal) {
    setState(after ? 'more' : 'loading');
    try {
      const page = await getCalls({ cursor: after, owner, channel }, signal);
      setItems(list => (after ? [...list, ...page.items] : page.items));
      setCursor(page.nextCursor);
      setState('ready');
    } catch (e) {
      if (signal?.aborted) return;
      setError(e instanceof Error ? e.message : 'The call list could not be read.');
      setState('error');
    }
  }

  useEffect(() => {
    const controller = new AbortController();
    void load(null, controller.signal);
    return () => controller.abort();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [owner, channel]);

  function setFilter(key: 'channel', value: string) {
    const next = new URLSearchParams(params);
    if (value) next.set(key, value); else next.delete(key);
    setParams(next);
  }

  return (
    <div className="page admin-page">
      <header className="page-head">
        <h1>All calls</h1>
        <p>Every screened call from every account, newest first. Open one for its transcript and how the verdict moved.</p>
      </header>

      <div className="admin-filters">
        <div className="field">
          <label htmlFor="channel-filter">Kind</label>
          <select id="channel-filter" className="input" value={channel ?? ''} onChange={e => setFilter('channel', e.target.value)}>
            <option value="">All kinds</option>
            {Object.entries(CHANNELS).filter(([k]) => k !== 'exotel').map(([k, label]) => <option key={k} value={k}>{label}</option>)}
            <option value="exotel">Phone line (Exotel)</option>
          </select>
        </div>
        {owner && (
          <p className="muted">One account only · <Button size="sm" variant="ghost" onClick={() => { const n = new URLSearchParams(params); n.delete('owner'); setParams(n); }}>Show every account</Button></p>
        )}
      </div>

      <section className="panel" aria-label="Calls">
        {state === 'loading' ? <div className="panel-pad"><Skeleton lines={5} /></div>
          : state === 'error' && !items.length ? <div className="panel-pad"><Notice tone="danger">{error}</Notice></div>
          : items.length === 0 ? (
            <div className="people-empty"><Files size={36} weight="duotone" aria-hidden="true" /><p>No calls match.</p></div>
          ) : (
            <div className="table-wrap">
              <table className="report-table admin-table">
                <thead><tr><th scope="col">When</th><th scope="col">Account</th><th scope="col">Kind</th><th scope="col">Result</th><th scope="col" className="right">Trust</th><th scope="col">What was said</th></tr></thead>
                <tbody>
                  {items.map(row => {
                    const band = row.band && row.band in BANDS ? BANDS[row.band] : null;
                    const open = `/calls/${encodeURIComponent(row.session_id)}`;
                    return (
                      <tr key={row.session_id} onClick={() => navigate(open)}>
                        <th scope="row"><Link to={open} className="row-link">{row.created_at ? when(row.created_at) : '—'}</Link></th>
                        <td>{whoLabel(row.owner)}</td>
                        <td>{CHANNELS[row.channel_type ?? ''] ?? row.channel_type ?? '—'}</td>
                        <td>{band ? <ToneChip tone={band.tone}>{band.label}</ToneChip> : <span className="muted">{row.status === 'streaming' ? 'In progress' : 'No result'}</span>}</td>
                        <td className="right num">{row.trust_score == null || row.band === 'insufficient' ? '—' : Math.round(row.trust_score)}</td>
                        <td className="admin-preview">{row.transcript_preview || <span className="muted">—</span>}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
              {cursor && <div className="panel-pad"><Button onClick={() => void load(cursor)} busy={state === 'more'}>Show older calls</Button></div>}
              {state === 'error' && <div className="panel-pad"><Notice tone="danger">{error}</Notice></div>}
            </div>
          )}
      </section>
    </div>
  );
}
