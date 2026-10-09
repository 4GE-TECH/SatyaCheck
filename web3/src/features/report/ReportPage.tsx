import { useEffect, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { ArrowLeft } from '@phosphor-icons/react';
import { useWorkspace, type CheckRecord } from '../../app/workspace';
import { getScreening } from '../../lib/api';
import { Button, ButtonLink, Notice, Skeleton } from '../../components/ui';
import ReportView, { ReportActions } from './ReportView';

export default function ReportPage() {
  const { id = '' } = useParams();
  return <ReportLoader key={id} id={id} />;
}

function ReportLoader({ id }: { id: string }) {
  const { findRecord, addRecord } = useWorkspace();
  const cached = findRecord(id);
  const [error, setError] = useState('');
  const [attempt, setAttempt] = useState(0);
  const [loading, setLoading] = useState(!cached);

  useEffect(() => {
    if (cached) return;
    const controller = new AbortController();
    getScreening(id, controller.signal)
      .then(data => addRecord({ data, name: 'Saved report', source: 'saved' }))
      .catch(problem => { if (!controller.signal.aborted) setError(problem.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [id, cached, attempt, addRecord]);

  const record: CheckRecord | undefined = cached;

  return (
    <div className="page report-page">
      <div className="report-bar">
        <Link className="back" to="/"><ArrowLeft size={18} weight="bold" aria-hidden="true" />New check</Link>
        {record && <ReportActions record={record} />}
      </div>
      {record ? (
        <ReportView record={record} />
      ) : loading ? (
        <div className="panel report-loading" role="status" aria-label="Retrieving the saved report">
          <Skeleton lines={2} /><Skeleton lines={4} />
        </div>
      ) : (
        <div className="report-missing">
          <Notice tone="danger" action={<Button size="sm" onClick={() => { setError(''); setLoading(true); setAttempt(n => n + 1); }}>Try again</Button>}>
            {error || 'This report could not be opened.'}
          </Notice>
          <ButtonLink to="/reports" variant="ghost">Choose another report</ButtonLink>
        </div>
      )}
    </div>
  );
}
