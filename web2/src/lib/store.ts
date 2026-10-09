import { createContext, useContext } from 'react';
import type { Check } from './api';
export const LabContext = createContext<{ checks: Check[]; save: (check: Check) => void }>({ checks: [], save: () => {} });
export const useLab = () => useContext(LabContext);
