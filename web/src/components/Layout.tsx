import { type ReactNode } from "react";
import Navbar from "./Navbar";

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="flex flex-col min-h-dvh bg-[#000000] text-white font-sans cyber-grid">
      <Navbar />

      <main className="flex-1 w-full max-w-[1440px] mx-auto p-4 sm:p-6 lg:p-8">
        {children}
      </main>

      <footer className="border-t border-white/10 bg-[#050505] px-4 sm:px-8 py-3 text-xs font-mono text-zinc-500 select-none">
        <div className="max-w-[1440px] mx-auto flex flex-col sm:flex-row items-center justify-between gap-2 text-center sm:text-left">
          <div className="flex items-center gap-3">
            <span className="text-zinc-300">SATYACHECK v1.0</span>
            <span>/</span>
            <span>THREE-BRANCH VOICE DEFENSE ARCHITECTURE</span>
          </div>
          <div className="flex items-center gap-4">
            <span>NATIONAL PORTAL: 1930 / CYBERCRIME.GOV.IN</span>
          </div>
        </div>
      </footer>
    </div>
  );
}
