import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft } from '@phosphor-icons/react';
import { CHANNELS, getCallDetail, rtcSession, whoLabel, type CallDetail } from '../../lib/admin';
import { BANDS, when } from '../../lib/verdict';
import { Notice, Skeleton, ToneChip } from '../../components/ui';
import ReportView from '../report/ReportView';

export default function CallDetailPage() {
  const { id = '' } = useParams();
  const [data, setData] = useState<CallDetail | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    setData(null);
    setError('');
    getCallDetail(id, controller.signal)
      .then(setData)
      .catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, [id]);

  const rtc = rtcSession(id);

  return (
    <div className="page report-page admin-page">
      <div className="report-bar">
        <Link className="back" to="/calls"><ArrowLeft size={18} weight="bold" aria-hidden="true" />All calls</Link>
      </div>
      {error && <Notice tone="danger">{error}</Notice>}
      {!data && !error && <div className="panel panel-pad"><Skeleton lines={5} /></div>}
      {data && (
        <>
          <section className="panel admin-call-meta" aria-label="About this call">
            <dl>
              <div><dt>Account</dt><dd>{whoLabel(data.owner)}{data.owner.user_id && <> · <Link to={`/calls?owner=${encodeURIComponent(data.owner.user_id)}`}>its calls</Link></>}</dd></div>
              <div><dt>Kind</dt><dd>{CHANNELS[data.channel_type ?? ''] ?? data.channel_type ?? '—'}{rtc && ` · the ${rtc.role}’s voice`}</dd></div>
              <div><dt>Started</dt><dd>{data.created_at ? when(data.created_at) : '—'}</dd></div>
              <div><dt>Status</dt><dd>{data.status === 'streaming' ? 'In progress' : data.status}</dd></div>
              <div><dt>Session</dt><dd className="mono small">{data.session_id}</dd></div>
            </dl>
          </section>

          {data.timeline.length > 1 && (
            <section className="panel" aria-labelledby="timeline-title">
              <div className="panel-head"><h2 id="timeline-title">How the verdict moved</h2><span className="muted small num">{data.timeline.length} updates</span></div>
              <ol className="verdict-strip">
                {data.timeline.map((t, i) => {
                  const band = t.band && t.band in BANDS ? BANDS[t.band] : null;
                  return (
                    <li key={i} className={`tone-${band?.tone ?? 'neutral'}${t.is_final ? ' is-final' : ''}`}
                      title={`${band?.label ?? 'No result'}${t.trust_score != null ? ` · ${Math.round(t.trust_score)}/100` : ''}${t.is_final ? ' · final' : ''}`}>
                      <span className="sr-only">Update {i + 1}: {band?.label ?? 'no result'}</span>
                    </li>
                  );
                })}
              </ol>
              <div className="panel-pad row-gap">
                {data.timeline.at(-1)?.band && BANDS[data.timeline.at(-1)!.band!] &&
                  <span>Now: <ToneChip tone={BANDS[data.timeline.at(-1)!.band!].tone}>{BANDS[data.timeline.at(-1)!.band!].label}</ToneChip></span>}
              </div>
            </section>
          )}

          {data.response
            ? <ReportView record={{ data: data.response, name: whoLabel(data.owner), source: 'saved' }} focus={false} />
            : <Notice>This call has no verdict yet: not enough speech was screened.</Notice>}
        </>
      )}
    </div>
  );
}
