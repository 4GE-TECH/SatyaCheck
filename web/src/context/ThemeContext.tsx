import { useEffect, useRef, useState, type ReactNode } from 'react';
import { ThemeContext, type Theme } from './theme-state';

const query = '(prefers-color-scheme: dark)';

/** Follows the system theme until the person chooses one; the choice lasts for this page session only. */
export function ThemeProvider({ children }: { children: ReactNode }) {
  const [theme, setThemeState] = useState<Theme>(() => (window.matchMedia(query).matches ? 'dark' : 'light'));
  const chosen = useRef(false);

  useEffect(() => {
    const media = window.matchMedia(query);
    const follow = (event: MediaQueryListEvent) => { if (!chosen.current) setThemeState(event.matches ? 'dark' : 'light'); };
    media.addEventListener('change', follow);
    return () => media.removeEventListener('change', follow);
  }, []);

  useEffect(() => {
    document.documentElement.dataset.theme = theme;
    document.documentElement.classList.toggle('dark', theme === 'dark');
    document.querySelector('meta[name="theme-color"]')?.setAttribute('content', theme === 'dark' ? '#121815' : '#202725');
  }, [theme]);

  function setTheme(next: Theme) {
    chosen.current = true;
    setThemeState(next);
  }

  return (
    <ThemeContext.Provider value={{ theme, setTheme, toggleTheme: () => setTheme(theme === 'light' ? 'dark' : 'light') }}>
      {children}
    </ThemeContext.Provider>
  );
}
