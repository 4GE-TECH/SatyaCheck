import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { UsersThree } from '@phosphor-icons/react';
import { getUsers, whoLabel, type UserRow } from '../../lib/admin';
import { when } from '../../lib/verdict';
import { Notice, Skeleton, ToneChip } from '../../components/ui';

export default function UsersPage() {
  const [users, setUsers] = useState<UserRow[] | null>(null);
  const [error, setError] = useState('');

  useEffect(() => {
    const controller = new AbortController();
    getUsers(controller.signal).then(setUsers).catch(e => { if (!controller.signal.aborted) setError(e.message); });
    return () => controller.abort();
  }, []);

  return (
    <div className="page admin-page">
      <header className="page-head">
        <h1>Accounts</h1>
        <p>Everyone with a username or a screened call. Emails are never stored here; accounts show by username or id.</p>
      </header>
      {error && <Notice tone="danger">{error}</Notice>}
      <section className="panel" aria-label="Accounts">
        {!users ? <div className="panel-pad"><Skeleton lines={5} /></div> : users.length === 0 ? (
          <div className="people-empty"><UsersThree size={36} weight="duotone" aria-hidden="true" /><p>No accounts yet.</p></div>
        ) : (
          <div className="table-wrap">
            <table className="report-table admin-table">
              <thead><tr><th scope="col">Account</th><th scope="col">Name</th><th scope="col" className="right">Calls</th><th scope="col" className="right">Saved voices</th><th scope="col" className="right">Connections</th><th scope="col">Last call</th></tr></thead>
              <tbody>
                {users.map(u => (
                  <tr key={u.user_id ?? ''}>
                    <th scope="row">
                      <Link className="row-link" to={`/calls?owner=${encodeURIComponent(u.user_id ?? '')}`}>{whoLabel(u)}</Link>
                      {u.admin && <> <ToneChip tone="neutral" size="md">Admin</ToneChip></>}
                    </th>
                    <td>{u.display_name ?? <span className="muted">—</span>}</td>
                    <td className="right num">{u.calls}</td>
                    <td className="right num">{u.enrolled_voices}</td>
                    <td className="right num">{u.connections}</td>
                    <td>{u.last_call_at ? when(u.last_call_at) : <span className="muted">never</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}
