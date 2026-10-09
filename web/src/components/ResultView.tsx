import { Link } from 'react-router-dom';
import { ArrowLeft, FileText } from 'lucide-react';
import type { ScreeningResponse } from '../types/contracts';
import { Button, Notice } from './Primitives';
import ReportSheet, { type ReportStatus } from './ReportSheet';
import ReportActions from './ReportActions';

interface Props {
  data: ScreeningResponse;
  demo?: boolean;
  name?: string;
  audioUrl?: string | null;
  status?: ReportStatus;
  onReset?: () => void;
}

export default function ResultView({ data, demo = false, name, audioUrl, status, onReset }: Props) {
  const sheetStatus: ReportStatus = status ?? (demo ? 'sample' : 'final');
  return (
    <div className="result-view">
      <div className="result-toolbar">
        {onReset ? (
          <Button variant="quiet" onClick={onReset}><ArrowLeft size={17} aria-hidden="true" />New check</Button>
        ) : (
          <Link className="text-link" to="/"><ArrowLeft size={17} aria-hidden="true" />New check</Link>
        )}
        <div className="toolbar-end">
          {sheetStatus !== 'provisional' && <ReportActions data={data} demo={demo} />}
          {sheetStatus !== 'provisional' && (
            <Link className="button button-quiet" to={`/report?session=${encodeURIComponent(data.session_id)}`}>
              <FileText size={17} aria-hidden="true" />Open in reports
            </Link>
          )}
        </div>
      </div>
      {demo && <Notice>Sample result. This is a demonstration and does not describe your recording.</Notice>}
      <ReportSheet data={data} status={sheetStatus} name={name} audioUrl={audioUrl} focusHeading={sheetStatus !== 'provisional'} />
    </div>
  );
}
