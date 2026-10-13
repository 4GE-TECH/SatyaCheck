import { useEffect, useState } from 'react';
import { ArrowRight, Broadcast, Cpu, PhoneCall, UsersThree } from '@phosphor-icons/react';
import { getOverview, type Overview } from '../../lib/admin';
import { BANDS } from '../../lib/verdict';
import type { TrustBand } from '../../types/contracts';
import { ButtonLink, Notice, Skeleton, ToneChip } from '../../components/ui';

const BAND_ORDER: TrustBand[] = ['high_risk', 'suspicious', 'caution', 'unverified', 'verified', 'insufficient'] as TrustBand[];

export default function OverviewPage() {
  const [data, setData] = useState<Overview | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    let stop = false;
    const controller = new AbortController();
    const load = () => getOverview(controller.signal)
      .then(d => { if (!stop) { setData(d); setError(''); } })
      .catch(e => { if (!stop && !controller.signal.aborted) setError(e.message); });
    void load();
    const timer = window.setInterval(load, 5000);
    return () => { stop = true; controller.abort(); window.clearInterval(timer); };
  }, []);

  const total = data ? Object.values(data.bands_24h).reduce((a, b) => a + b, 0) : 0;

  return (
    <div className="page admin-page">
      <header className="page-head">
        <h1>Overview</h1>
        <p>Every account’s calls, as the screening service sees them. Read-only: nothing here changes a call.</p>
      </header>

      {error && <Notice tone="danger">{error}</Notice>}
      {!data ? <div className="panel panel-pad"><Skeleton lines={4} /></div> : (
        <>
          <section className="admin-tiles" aria-label="Right now">
            <Tile icon={<PhoneCall size={22} weight="duotone" />} label="App calls in progress" value={data.calls.active}
              note={data.calls.ringing ? `${data.calls.ringing} ringing` : data.webrtc_enabled ? 'none ringing' : 'app calls are off on this server'} />
            <Tile icon={<Broadcast size={22} weight="duotone" />} label="Voices being screened"
              value={data.live_sessions ?? 0} note={data.max_live_sessions != null ? `of ${data.max_live_sessions} at once` : ''} />
            <Tile icon={<UsersThree size={22} weight="duotone" />} label="Accounts with calls" value={data.accounts_with_calls}
              note={`${data.accounts_with_username} with a username`} />
            <Tile icon={<Cpu size={22} weight="duotone" />} label="Models on" value={data.device ?? '—'}
              note={data.ready ? 'ready' : data.problems.length ? data.problems[0] : 'not ready'} tone={data.ready ? undefined : 'caution'} />
          </section>

          <section className="panel" aria-labelledby="last-day">
            <div className="panel-head"><h2 id="last-day">Last 24 hours</h2><span className="muted small num">{data.screenings_24h} screened</span></div>
            <div className="panel-pad">
              {total === 0 ? <p className="muted">No calls screened in the last 24 hours.</p> : (
                <ul className="band-bars">
                  {BAND_ORDER.filter(b => data.bands_24h[b]).map(b => (
                    <li key={b}>
                      <ToneChip tone={BANDS[b].tone}>{BANDS[b].label}</ToneChip>
                      <span className="band-bar" aria-hidden="true">
                        <span className={`band-fill tone-${BANDS[b].tone}`} style={{ width: `${(data.bands_24h[b] / total) * 100}%` }} />
                      </span>
                      <span className="num">{data.bands_24h[b]}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </section>

          <div className="row-gap">
            <ButtonLink to="/live" variant="primary" trail={<ArrowRight size={16} weight="bold" />}>Watch live calls</ButtonLink>
            <ButtonLink to="/calls" trail={<ArrowRight size={16} weight="bold" />}>All calls</ButtonLink>
          </div>
        </>
      )}
    </div>
  );
}

function Tile({ icon, label, value, note, tone }: { icon: React.ReactNode; label: string; value: number | string; note: string; tone?: 'caution' }) {
  return (
    <div className={`panel admin-tile${tone ? ` tone-${tone}` : ''}`}>
      <span className="admin-tile-icon" aria-hidden="true">{icon}</span>
      <span className="admin-tile-label">{label}</span>
      <span className="admin-tile-value num">{value}</span>
      <span className="muted small">{note}</span>
    </div>
  );
}
