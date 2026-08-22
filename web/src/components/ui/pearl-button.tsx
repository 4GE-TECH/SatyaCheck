import React from "react";

export type PearlButtonVariant = "default" | "danger" | "success" | "warning" | "secondary" | "outline";
export type PearlButtonSize = "sm" | "md" | "lg";

export type PearlButtonProps = React.ButtonHTMLAttributes<HTMLButtonElement> & {
  label?: string;
  children?: React.ReactNode;
  variant?: PearlButtonVariant;
  size?: PearlButtonSize;
  icon?: React.ReactNode;
};

export const PearlButton: React.FC<PearlButtonProps> = ({
  label,
  children,
  variant = "default",
  size = "md",
  icon,
  className = "",
  ...props
}) => {
  return (
    <>
      <style>{`
        .pearl-btn-base {
          outline: none;
          cursor: pointer;
          border: 0;
          position: relative;
          border-radius: 9999px;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
          font-family: inherit;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          user-select: none;
          text-decoration: none;
        }

        /* ── Size Variants ── */
        .pearl-btn-sm {
          font-size: 12px;
          border-radius: 9999px;
        }
        .pearl-btn-sm .pearl-wrap {
          padding: 6px 14px;
          gap: 6px;
        }

        .pearl-btn-md {
          font-size: 14px;
          border-radius: 9999px;
        }
        .pearl-btn-md .pearl-wrap {
          padding: 10px 20px;
          gap: 8px;
        }

        .pearl-btn-lg {
          font-size: 16px;
          border-radius: 9999px;
        }
        .pearl-btn-lg .pearl-wrap {
          padding: 14px 28px;
          gap: 10px;
        }

        /* ── Default / Neutral Pearl ── */
        .pearl-variant-default {
          --bg: #0A0D14;
          --text: #FFFFFF;
          --rim: rgba(255, 255, 255, 0.35);
          background-color: var(--bg);
          color: var(--text);
          box-shadow:
            inset 0 0.2rem 0.6rem var(--rim),
            inset 0 -0.1rem 0.3rem rgba(0, 0, 0, 0.8),
            0 0.8rem 1.2rem -0.4rem rgba(0, 0, 0, 0.6);
        }
        html:not(.dark) .pearl-variant-default {
          --bg: #FFFFFF;
          --text: #0F172A;
          --rim: rgba(255, 255, 255, 0.95);
          border: 1px solid rgba(0, 0, 0, 0.12);
          box-shadow:
            inset 0 0.2rem 0.5rem var(--rim),
            inset 0 -0.1rem 0.2rem rgba(0, 0, 0, 0.06),
            0 0.4rem 0.8rem -0.2rem rgba(0, 0, 0, 0.12);
        }

        /* ── Danger Pearl ── */
        .pearl-variant-danger {
          --bg: #1A0507;
          --text: #FFA3A8;
          --rim: rgba(255, 59, 48, 0.5);
          background-color: var(--bg);
          color: var(--text);
          border: 1px solid rgba(255, 59, 48, 0.3);
          box-shadow:
            inset 0 0.2rem 0.6rem var(--rim),
            inset 0 -0.1rem 0.3rem rgba(0, 0, 0, 0.9),
            0 0.8rem 1.2rem -0.4rem rgba(255, 59, 48, 0.3);
        }
        html:not(.dark) .pearl-variant-danger {
          --bg: #FEF2F2;
          --text: #991B1B;
          --rim: rgba(255, 255, 255, 0.9);
          border: 1px solid #FCA5A5;
          box-shadow:
            inset 0 0.2rem 0.5rem var(--rim),
            inset 0 -0.1rem 0.2rem rgba(220, 38, 38, 0.1),
            0 0.4rem 0.8rem -0.2rem rgba(220, 38, 38, 0.15);
        }

        /* ── Success Pearl ── */
        .pearl-variant-success {
          --bg: #04170A;
          --text: #86EFAC;
          --rim: rgba(48, 209, 88, 0.45);
          background-color: var(--bg);
          color: var(--text);
          border: 1px solid rgba(48, 209, 88, 0.3);
          box-shadow:
            inset 0 0.2rem 0.6rem var(--rim),
            inset 0 -0.1rem 0.3rem rgba(0, 0, 0, 0.9),
            0 0.8rem 1.2rem -0.4rem rgba(48, 209, 88, 0.25);
        }
        html:not(.dark) .pearl-variant-success {
          --bg: #F0FDF4;
          --text: #166534;
          --rim: rgba(255, 255, 255, 0.9);
          border: 1px solid #86EFAC;
          box-shadow:
            inset 0 0.2rem 0.5rem var(--rim),
            inset 0 -0.1rem 0.2rem rgba(22, 163, 74, 0.1),
            0 0.4rem 0.8rem -0.2rem rgba(22, 163, 74, 0.15);
        }

        /* ── Secondary / Subtle Pearl ── */
        .pearl-variant-secondary {
          --bg: #0D0F15;
          --text: #D1D5DB;
          --rim: rgba(255, 255, 255, 0.15);
          background-color: var(--bg);
          color: var(--text);
          border: 1px solid rgba(255, 255, 255, 0.1);
          box-shadow:
            inset 0 0.15rem 0.4rem var(--rim),
            0 0.4rem 0.8rem -0.2rem rgba(0, 0, 0, 0.5);
        }
        html:not(.dark) .pearl-variant-secondary {
          --bg: #F1F5F9;
          --text: #475569;
          --rim: rgba(255, 255, 255, 0.9);
          border: 1px solid #CBD5E1;
          box-shadow:
            inset 0 0.15rem 0.4rem var(--rim),
            0 0.2rem 0.4rem -0.1rem rgba(0, 0, 0, 0.08);
        }

        /* ── Pearl Inner Wrap & Highlights ── */
        .pearl-btn-base .pearl-wrap {
          border-radius: inherit;
          position: relative;
          overflow: hidden;
          display: flex;
          align-items: center;
          justify-content: center;
          font-weight: 600;
          width: 100%;
          letter-spacing: -0.01em;
        }

        .pearl-btn-base .pearl-wrap::before {
          content: "";
          position: absolute;
          left: -15%;
          right: -15%;
          bottom: 30%;
          top: -100%;
          border-radius: 50%;
          background-color: rgba(255, 255, 255, 0.08);
          pointer-events: none;
          transition: transform 0.2s ease;
        }

        .pearl-btn-base .pearl-wrap::after {
          content: "";
          position: absolute;
          left: 8%;
          right: 8%;
          top: 8%;
          bottom: 45%;
          border-radius: 9999px;
          box-shadow: inset 0 6px 6px -6px rgba(255, 255, 255, 0.6);
          background: linear-gradient(180deg, rgba(255, 255, 255, 0.2) 0%, transparent 100%);
          pointer-events: none;
          transition: opacity 0.2s ease;
        }

        /* ── Hover & Active ── */
        .pearl-btn-base:hover {
          transform: translateY(-1px);
          filter: brightness(1.06);
        }
        .pearl-btn-base:hover .pearl-wrap::before {
          transform: translateY(-4%);
        }
        .pearl-btn-base:hover .pearl-wrap::after {
          opacity: 0.7;
        }
        .pearl-btn-base:active {
          transform: translateY(1px);
          filter: brightness(0.96);
        }
        .pearl-btn-base:disabled {
          opacity: 0.5;
          cursor: not-allowed;
          transform: none;
          filter: none;
        }
      `}</style>

      <button
        className={`pearl-btn-base pearl-variant-${variant} pearl-btn-${size} ${className}`}
        {...props}
      >
        <span className="pearl-wrap">
          {icon && <span className="shrink-0">{icon}</span>}
          {children || label}
        </span>
      </button>
    </>
  );
};

export default PearlButton;
