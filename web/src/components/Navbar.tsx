import { NavLink } from "react-router-dom";
import ThemeToggle from "./ThemeToggle";

export default function Navbar() {
  return (
    <header className="border-b border-[var(--border-default)] bg-[var(--bg-primary)] px-4 sm:px-8 py-3 select-none transition-colors">
      <div className="max-w-4xl mx-auto flex items-center justify-between gap-4">
        {/* Brand */}
        <NavLink to="/" className="flex items-center gap-3 text-inherit no-underline">
          <div className="w-8 h-8 rounded-lg bg-[var(--accent)] flex items-center justify-center font-bold text-base text-[var(--accent-text)] shadow-sm">
            S
          </div>
          <div>
            <span className="font-bold text-base tracking-tight text-[var(--text-primary)] block leading-tight">
              SatyaCheck
            </span>
            <span className="text-xs text-[var(--text-muted)] font-medium">
              Voice Fraud Defense
            </span>
          </div>
        </NavLink>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-1.5 sm:gap-2">
          <NavLink
            to="/"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-md text-sm font-semibold transition-colors no-underline flex items-center gap-1.5 cursor-pointer ${
                isActive
                  ? "bg-[var(--accent)] text-[var(--accent-text)]"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]"
              }`
            }
          >
            Check a Call
          </NavLink>

          <NavLink
            to="/enroll"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-md text-sm font-semibold transition-colors no-underline flex items-center gap-1.5 cursor-pointer ${
                isActive
                  ? "bg-[var(--accent)] text-[var(--accent-text)]"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]"
              }`
            }
          >
            Family Vault
          </NavLink>

          <NavLink
            to="/report"
            className={({ isActive }) =>
              `px-3 py-1.5 rounded-md text-sm font-semibold transition-colors no-underline flex items-center gap-1.5 cursor-pointer ${
                isActive
                  ? "bg-[var(--accent)] text-[var(--accent-text)]"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]"
              }`
            }
          >
            Report Fraud
          </NavLink>
        </nav>

        {/* Right Controls: Helpline + Theme Toggle */}
        <div className="flex items-center gap-2.5">
          <a
            href="tel:1930"
            className="hidden md:flex px-3 py-1.5 rounded-md bg-[var(--danger-bg)] text-[var(--danger-text)] border border-[var(--danger-border)] hover:opacity-90 text-xs font-bold no-underline items-center gap-1.5 transition-all"
          >
            Helpline: 1930
          </a>

          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
