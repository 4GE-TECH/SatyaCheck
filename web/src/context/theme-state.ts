import { createContext, useContext } from 'react';
export type Theme = 'light' | 'dark';
export const ThemeContext = createContext<{ theme: Theme; toggleTheme: () => void; setTheme: (theme: Theme) => void } | null>(null);
export function useTheme() { const value = useContext(ThemeContext); if (!value) throw new Error('ThemeProvider is required.'); return value; }

