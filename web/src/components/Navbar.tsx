import { NavLink } from "react-router-dom";

export default function Navbar() {
  return (
    <header className="border-b border-[var(--color-border-default)] bg-[var(--color-bg-primary)] px-4 sm:px-8 py-3.5 select-none">
      <div className="max-w-4xl mx-auto flex items-center justify-between">
        {/* Brand */}
        <NavLink to="/" className="flex items-center gap-3 text-inherit no-underline">
          <div className="w-9 h-9 rounded-xl bg-blue-600 flex items-center justify-center font-bold text-lg text-white shadow-md">
            S
          </div>
          <div>
            <span className="font-bold text-lg tracking-tight text-white block leading-tight">
              SatyaCheck
            </span>
            <span className="text-xs text-slate-300 font-medium">
              Family Voice Protection
            </span>
          </div>
        </NavLink>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-2">
          <NavLink
            to="/"
            className={({ isActive }) =>
              `px-3.5 py-2 rounded-xl text-sm font-semibold transition-all no-underline flex items-center gap-2 cursor-pointer ${
                isActive
                  ? "bg-white text-black shadow-sm"
                  : "text-slate-200 hover:text-white hover:bg-slate-800"
              }`
            }
          >
            Check a Call
          </NavLink>

          <NavLink
            to="/enroll"
            className={({ isActive }) =>
              `px-3.5 py-2 rounded-xl text-sm font-semibold transition-all no-underline flex items-center gap-2 cursor-pointer ${
                isActive
                  ? "bg-white text-black shadow-sm"
                  : "text-slate-200 hover:text-white hover:bg-slate-800"
              }`
            }
          >
            My Family
          </NavLink>

          <NavLink
            to="/report"
            className={({ isActive }) =>
              `px-3.5 py-2 rounded-xl text-sm font-semibold transition-all no-underline flex items-center gap-2 cursor-pointer ${
                isActive
                  ? "bg-white text-black shadow-sm"
                  : "text-slate-200 hover:text-white hover:bg-slate-800"
              }`
            }
          >
            Help & Report
          </NavLink>
        </nav>

        {/* Emergency Call Helpline */}
        <div className="hidden md:flex items-center">
          <a
            href="tel:1930"
            className="px-4 py-2 rounded-xl bg-red-700 hover:bg-red-600 text-white text-sm font-bold no-underline flex items-center gap-2 transition-colors shadow-md"
          >
            <span>Call Helpline 1930</span>
          </a>
        </div>
      </div>
    </header>
  );
}
