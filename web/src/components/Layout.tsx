import { type ReactNode } from "react";
import Navbar from "./Navbar";

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="flex flex-col min-h-dvh bg-[var(--bg-root)] text-[var(--text-primary)] font-sans transition-colors">
      <Navbar />

      <main className="flex-1 w-full max-w-[1600px] mx-auto p-4 sm:p-6 md:p-8">
        {children}
      </main>

      <footer className="border-t border-[var(--border-subtle)] bg-[var(--bg-primary)] px-4 sm:px-8 py-4 text-xs text-[var(--text-muted)] select-none transition-colors">
        <div className="max-w-[1600px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-center sm:text-left">
          <div>
            <span className="font-bold text-[var(--text-primary)]">SatyaCheck</span>
            <span> — Voice Fraud Defense. Air-gapped on device.</span>
          </div>
          <div className="flex items-center gap-3 text-[var(--text-secondary)] font-medium font-mono">
            <span>National Cyber Helpline: <strong className="text-[var(--danger-text)] font-bold">1930</strong></span>
            <span>•</span>
            <a href="https://cybercrime.gov.in" target="_blank" rel="noreferrer" className="text-[var(--accent)] hover:underline">
              cybercrime.gov.in
            </a>
          </div>
        </div>
      </footer>
    </div>
  );
}
