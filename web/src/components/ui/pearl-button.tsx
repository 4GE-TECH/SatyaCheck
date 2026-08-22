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
          position: relative;
          border-radius: 9999px;
          transition: all 0.2s cubic-bezier(0.16, 1, 0.3, 1);
          font-family: inherit;
          display: inline-flex;
          align-items: center;
          justify-content: center;
          user-select: none;
          text-decoration: none;
          font-weight: 600;
        }

        /* ── Size Variants ── */
        .pearl-btn-sm {
          font-size: 13px;
          border-radius: 9999px;
        }
        .pearl-btn-sm .pearl-wrap {
          padding: 6px 16px;
          gap: 6px;
        }

        .pearl-btn-md {
          font-size: 14px;
          border-radius: 9999px;
        }
        .pearl-btn-md .pearl-wrap {
          padding: 10px 22px;
          gap: 8px;
        }

        .pearl-btn-lg {
          font-size: 16px;
          border-radius: 9999px;
        }
        .pearl-btn-lg .pearl-wrap {
          padding: 14px 30px;
          gap: 10px;
        }

        /* ── Pearl White Pill Styling (Consistent in Light & Dark Mode) ── */

        /* 1. Default & Secondary Pearl Pill */
        .pearl-variant-default,
        .pearl-variant-secondary {
          background-color: #FFFFFF;
          color: #0F172A;
          border: 1.5px solid #CBD5E1;
          box-shadow:
            inset 0 0.2rem 0.5rem rgba(255, 255, 255, 0.95),
            inset 0 -0.1rem 0.2rem rgba(0, 0, 0, 0.06),
            0 0.4rem 0.9rem -0.2rem rgba(0, 0, 0, 0.35);
        }

        /* 2. Danger Pearl Pill (Ruby Border & Text) */
        .pearl-variant-danger {
          background-color: #FFF8F8;
          color: #991B1B;
          border: 1.5px solid #FCA5A5;
          box-shadow:
            inset 0 0.2rem 0.5rem rgba(255, 255, 255, 0.95),
            inset 0 -0.1rem 0.2rem rgba(220, 38, 38, 0.08),
            0 0.4rem 0.9rem -0.2rem rgba(0, 0, 0, 0.35);
        }

        /* 3. Success Pearl Pill (Emerald Border & Text) */
        .pearl-variant-success {
          background-color: #F6FEF8;
          color: #166534;
          border: 1.5px solid #86EFAC;
          box-shadow:
            inset 0 0.2rem 0.5rem rgba(255, 255, 255, 0.95),
            inset 0 -0.1rem 0.2rem rgba(22, 163, 74, 0.08),
            0 0.4rem 0.9rem -0.2rem rgba(0, 0, 0, 0.35);
        }

        /* 4. Warning Pearl Pill (Amber Border & Text) */
        .pearl-variant-warning {
          background-color: #FFFEFA;
          color: #92400E;
          border: 1.5px solid #FDE68A;
          box-shadow:
            inset 0 0.2rem 0.5rem rgba(255, 255, 255, 0.95),
            inset 0 -0.1rem 0.2rem rgba(217, 119, 6, 0.08),
            0 0.4rem 0.9rem -0.2rem rgba(0, 0, 0, 0.35);
        }

        /* ── Pearl Inner Wrap & Specular Highlight ── */
        .pearl-btn-base .pearl-wrap {
          border-radius: inherit;
          position: relative;
          overflow: hidden;
          display: flex;
          align-items: center;
          justify-content: center;
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
          background-color: rgba(255, 255, 255, 0.3);
          pointer-events: none;
          transition: transform 0.2s ease;
        }

        .pearl-btn-base .pearl-wrap::after {
          content: "";
          position: absolute;
          left: 8%;
          right: 8%;
          top: 6%;
          bottom: 50%;
          border-radius: 9999px;
          box-shadow: inset 0 4px 4px -3px rgba(255, 255, 255, 0.9);
          background: linear-gradient(180deg, rgba(255, 255, 255, 0.5) 0%, transparent 100%);
          pointer-events: none;
          transition: opacity 0.2s ease;
        }

        /* ── Hover & Active Micro-Interactions ── */
        .pearl-btn-base:hover {
          transform: translateY(-1.5px);
          filter: brightness(1.03);
          box-shadow:
            inset 0 0.2rem 0.5rem rgba(255, 255, 255, 0.95),
            0 0.6rem 1.1rem -0.2rem rgba(0, 0, 0, 0.45);
        }
        .pearl-btn-base:active {
          transform: translateY(1px);
          filter: brightness(0.97);
          box-shadow:
            inset 0 0.15rem 0.3rem rgba(0, 0, 0, 0.1),
            0 0.2rem 0.4rem -0.1rem rgba(0, 0, 0, 0.2);
        }
        .pearl-btn-base:disabled {
          opacity: 0.6;
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
