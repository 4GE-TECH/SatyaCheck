import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

function cn(...inputs: (string | undefined | null | false)[]): string {
  return inputs.filter(Boolean).join(" ");
}

const glassButtonVariants = cva(
  "glass-btn-base relative cursor-pointer rounded-full transition-all duration-150 border inline-flex items-center justify-center font-mono font-semibold select-none disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]",
  {
    variants: {
      variant: {
        default: "glass-btn-default",
        danger: "glass-btn-danger",
        success: "glass-btn-success",
        warning: "glass-btn-warning",
        secondary: "glass-btn-secondary",
      },
      size: {
        default: "text-sm",
        sm: "text-xs",
        lg: "text-base",
        icon: "h-10 w-10 p-0 flex items-center justify-center",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
    },
  }
);

const glassButtonTextVariants = cva(
  "glass-btn-text relative flex items-center justify-center gap-2 select-none tracking-tight w-full",
  {
    variants: {
      size: {
        default: "px-6 py-2.5",
        sm: "px-3.5 py-1.5",
        lg: "px-8 py-3.5",
        icon: "flex h-10 w-10 items-center justify-center p-0",
      },
    },
    defaultVariants: {
      size: "default",
    },
  }
);

export interface GlassButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
    VariantProps<typeof glassButtonVariants> {
  contentClassName?: string;
  icon?: React.ReactNode;
  label?: string;
}

const GlassButton = React.forwardRef<HTMLButtonElement, GlassButtonProps>(
  (
    {
      className,
      children,
      variant = "default",
      size = "default",
      contentClassName,
      icon,
      label,
      ...props
    },
    ref
  ) => {
    return (
      <>
        <style>{`
          .glass-btn-base {
            outline: none;
            text-decoration: none;
          }
          .glass-btn-base:hover {
            transform: translateY(-1px);
          }
          .glass-btn-base:active {
            transform: translateY(1px);
          }

          /* ── Default / Neutral Glass ── */
          .glass-btn-default {
            background-color: #FFFFFF;
            color: #0F172A;
            border: 1.5px solid #CBD5E1;
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.9),
              0 3px 10px -2px rgba(0, 0, 0, 0.08);
          }
          html.dark .glass-btn-default {
            background-color: rgba(255, 255, 255, 0.08);
            color: #FFFFFF;
            border: 1.5px solid rgba(255, 255, 255, 0.22);
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.25),
              0 4px 14px -2px rgba(0, 0, 0, 0.6);
          }
          .glass-btn-default:hover {
            background-color: #F8FAFC;
            border-color: #94A3B8;
          }
          html.dark .glass-btn-default:hover {
            background-color: rgba(255, 255, 255, 0.14);
            border-color: rgba(255, 255, 255, 0.35);
          }

          /* ── Danger Glass (Red) ── */
          .glass-btn-danger {
            background-color: #FEF2F2;
            color: #991B1B;
            border: 1.5px solid #FCA5A5;
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.9),
              0 3px 10px -2px rgba(220, 38, 38, 0.1);
          }
          html.dark .glass-btn-danger {
            background-color: rgba(255, 59, 48, 0.12);
            color: #FFA3A8;
            border: 1.5px solid rgba(255, 59, 48, 0.4);
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.2),
              0 4px 14px -2px rgba(255, 59, 48, 0.3);
          }
          .glass-btn-danger:hover {
            background-color: #FEE2E2;
            border-color: #F87171;
          }
          html.dark .glass-btn-danger:hover {
            background-color: rgba(255, 59, 48, 0.2);
            border-color: rgba(255, 59, 48, 0.6);
          }

          /* ── Success Glass (Emerald) ── */
          .glass-btn-success {
            background-color: #F0FDF4;
            color: #166534;
            border: 1.5px solid #86EFAC;
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.9),
              0 3px 10px -2px rgba(22, 163, 74, 0.1);
          }
          html.dark .glass-btn-success {
            background-color: rgba(48, 209, 88, 0.12);
            color: #86EFAC;
            border: 1.5px solid rgba(48, 209, 88, 0.4);
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.2),
              0 4px 14px -2px rgba(48, 209, 88, 0.25);
          }
          .glass-btn-success:hover {
            background-color: #DCFCE7;
            border-color: #4ADE80;
          }
          html.dark .glass-btn-success:hover {
            background-color: rgba(48, 209, 88, 0.2);
            border-color: rgba(48, 209, 88, 0.6);
          }

          /* ── Warning Glass (Amber) ── */
          .glass-btn-warning {
            background-color: #FFFBEB;
            color: #92400E;
            border: 1.5px solid #FDE68A;
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.9),
              0 3px 10px -2px rgba(217, 119, 6, 0.1);
          }
          html.dark .glass-btn-warning {
            background-color: rgba(255, 159, 10, 0.12);
            color: #FDE68A;
            border: 1.5px solid rgba(255, 159, 10, 0.4);
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.2),
              0 4px 14px -2px rgba(255, 159, 10, 0.25);
          }
          .glass-btn-warning:hover {
            background-color: #FEF3C7;
            border-color: #FCD34D;
          }
          html.dark .glass-btn-warning:hover {
            background-color: rgba(255, 159, 10, 0.2);
            border-color: rgba(255, 159, 10, 0.6);
          }

          /* ── Secondary Glass (Slate) ── */
          .glass-btn-secondary {
            background-color: #F1F5F9;
            color: #475569;
            border: 1.5px solid #CBD5E1;
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.9),
              0 2px 6px -2px rgba(0, 0, 0, 0.06);
          }
          html.dark .glass-btn-secondary {
            background-color: rgba(255, 255, 255, 0.05);
            color: #D1D5DB;
            border: 1.5px solid rgba(255, 255, 255, 0.14);
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.15),
              0 4px 12px -2px rgba(0, 0, 0, 0.5);
          }
          .glass-btn-secondary:hover {
            background-color: #E2E8F0;
            border-color: #94A3B8;
          }
          html.dark .glass-btn-secondary:hover {
            background-color: rgba(255, 255, 255, 0.1);
            border-color: rgba(255, 255, 255, 0.25);
          }
        `}</style>

        <button
          ref={ref}
          className={cn(
            glassButtonVariants({ variant, size }),
            className
          )}
          {...props}
        >
          <span
            className={cn(
              glassButtonTextVariants({ size }),
              contentClassName
            )}
          >
            {icon && <span className="shrink-0">{icon}</span>}
            {children || label}
          </span>
        </button>
      </>
    );
  }
);
GlassButton.displayName = "GlassButton";

export { GlassButton, glassButtonVariants };
