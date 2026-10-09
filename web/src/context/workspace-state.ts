import { createContext, useContext } from 'react';
import type { ScreeningResponse } from '../types/contracts';
export interface CheckRecord { data: ScreeningResponse; name: string; demo: boolean; }
export const WorkspaceContext = createContext<{ records: CheckRecord[]; add: (record: CheckRecord) => void } | null>(null);
export function useWorkspace() { const value = useContext(WorkspaceContext); if (!value) throw new Error('WorkspaceProvider is required.'); return value; }

