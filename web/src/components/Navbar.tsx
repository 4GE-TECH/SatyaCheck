import { NavLink } from "react-router-dom";
import ThemeToggle from "./ThemeToggle";
import { GlassButton } from "@/components/ui/glass-button";

export default function Navbar() {
  return (
    <header className="border-b border-[var(--border-default)] bg-[var(--bg-primary)] px-4 sm:px-8 py-3 select-none transition-colors">
      <div className="max-w-[1600px] mx-auto flex items-center justify-between gap-4">
        {/* Brand */}
        <NavLink to="/" className="flex items-center gap-3 text-inherit no-underline">
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
              `px-3.5 py-1.5 rounded-full text-sm font-semibold transition-all no-underline flex items-center gap-1.5 cursor-pointer ${
                isActive
                  ? "bg-[var(--text-primary)] text-[var(--bg-primary)] font-mono shadow-sm"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]"
              }`
            }
          >
            Check a Call
          </NavLink>

          <NavLink
            to="/enroll"
            className={({ isActive }) =>
              `px-3.5 py-1.5 rounded-full text-sm font-semibold transition-all no-underline flex items-center gap-1.5 cursor-pointer ${
                isActive
                  ? "bg-[var(--text-primary)] text-[var(--bg-primary)] font-mono shadow-sm"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]"
              }`
            }
          >
            Family Vault
          </NavLink>

          <NavLink
            to="/report"
            className={({ isActive }) =>
              `px-3.5 py-1.5 rounded-full text-sm font-semibold transition-all no-underline flex items-center gap-1.5 cursor-pointer ${
                isActive
                  ? "bg-[var(--text-primary)] text-[var(--bg-primary)] font-mono shadow-sm"
                  : "text-[var(--text-secondary)] hover:text-[var(--text-primary)] hover:bg-[var(--bg-secondary)]"
              }`
            }
          >
            Report Fraud
          </NavLink>
        </nav>

        {/* Right Controls: Helpline + Theme Toggle */}
        <div className="flex items-center gap-2 sm:gap-2.5">
          <a
            href="tel:1930"
            className="inline-block no-underline"
            title="National Cybercrime Helpline: 1930"
          >
            <GlassButton
              variant="danger"
              size="sm"
              icon={<span className="w-2 h-2 rounded-full bg-white animate-pulse" />}
            >
              <span className="hidden sm:inline">Helpline: </span>
              <span>1930</span>
            </GlassButton>
          </a>

          <ThemeToggle />
        </div>
      </div>
    </header>
  );
}
