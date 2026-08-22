import { type ReactNode } from "react";
import Navbar from "./Navbar";

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {
  return (
    <div className="flex flex-col min-h-dvh bg-[#0B0F17] text-white font-sans">
      <Navbar />

      <main className="flex-1 w-full max-w-4xl mx-auto p-4 sm:p-6 md:p-8">
        {children}
      </main>

      <footer className="border-t border-slate-800 bg-[#0F172A] px-4 sm:px-8 py-5 text-sm text-slate-400 select-none">
        <div className="max-w-4xl mx-auto flex flex-col sm:flex-row items-center justify-between gap-3 text-center sm:text-left">
          <div>
            <span className="font-bold text-slate-200">SatyaCheck</span>
            <span> — Safe AI Voice Protection for Indian Families.</span>
          </div>
          <div className="flex items-center gap-3 text-slate-300 font-medium">
            <span>National Cyber Helpline: <strong className="text-red-400 font-bold">1930</strong></span>
          </div>
        </div>
      </footer>
    </div>
  );
}
