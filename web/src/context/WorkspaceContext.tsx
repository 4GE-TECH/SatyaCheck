import { useCallback, useState, type ReactNode } from 'react';
import { WorkspaceContext, type CheckRecord } from './workspace-state';
export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const [records, setRecords] = useState<CheckRecord[]>([]);
  const add = useCallback((record: CheckRecord) => setRecords(previous => [record, ...previous.filter(r => r.data.session_id !== record.data.session_id)].slice(0, 30)), []);
  return <WorkspaceContext.Provider value={{ records, add }}>{children}</WorkspaceContext.Provider>;
}

