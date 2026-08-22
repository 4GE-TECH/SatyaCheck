import { NavLink } from "react-router-dom";

export default function Navbar() {
  return (
    <header className="border-b border-[var(--color-border-default)] bg-[#000000] px-4 sm:px-8 py-3 select-none">
      <div className="max-w-[1440px] mx-auto flex items-center justify-between">
        {/* Left Brand */}
        <NavLink to="/" className="flex items-center gap-3 text-inherit no-underline">
          <div className="w-6 h-6 rounded border border-white/20 bg-white/5 flex items-center justify-center font-mono font-bold text-xs text-white">
            S
          </div>
          <div className="flex items-center gap-2.5">
            <span className="font-bold text-sm tracking-wider uppercase text-white font-mono">
              SATYACHECK
            </span>
            <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-white/5 text-zinc-400 border border-white/10">
              VOICE.DEFENSE
            </span>
          </div>
        </NavLink>

        {/* Center: Futuristic HUD Tabs */}
        <nav className="flex items-center gap-1 bg-[#080808] p-1 rounded border border-white/10">
          <NavItem to="/" code="01" label="SCREENING" />
          <NavItem to="/enroll" code="02" label="FAMILY VAULT" />
          <NavItem to="/report" code="03" label="INCIDENT DOSSIER" />
        </nav>

        {/* Right: Telemetry & Helpline */}
        <div className="flex items-center gap-3 font-mono text-xs">
          <div className="hidden md:flex items-center gap-2 text-zinc-500 text-[11px]">
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
            <span>AIR-GAPPED INFERENCE</span>
          </div>
          <a
            href="tel:1930"
            className="px-2.5 py-1 rounded bg-rose-950/40 text-rose-300 border border-rose-800/40 hover:bg-rose-900/40 transition-colors text-[11px] font-medium no-underline"
          >
            HELPLINE: 1930
          </a>
        </div>
      </div>
    </header>
  );
}

function NavItem({ to, code, label }: { to: string; code: string; label: string }) {
  return (
    <NavLink
      to={to}
      className={({ isActive }) =>
        `px-3 py-1 rounded text-xs font-mono tracking-wide transition-all no-underline flex items-center gap-1.5 cursor-pointer ${
          isActive
            ? "bg-white/10 text-white border border-white/20 font-semibold shadow-sm"
            : "text-zinc-400 hover:text-white hover:bg-white/5"
        }`
      }
    >
      <span className="text-zinc-500 text-[10px]">{code}</span>
      <span>{label}</span>
    </NavLink>
  );
}
