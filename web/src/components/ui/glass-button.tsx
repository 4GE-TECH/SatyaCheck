import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

function cn(...inputs: (string | undefined | null | false)[]): string {
  return inputs.filter(Boolean).join(" ");
}

const glassButtonVariants = cva(
  "glass-btn-base relative cursor-pointer rounded-lg transition-all duration-150 border inline-flex items-center justify-center font-semibold select-none disabled:opacity-50 disabled:cursor-not-allowed active:scale-[0.98]",
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
        default: "px-5 py-2.5",
        sm: "px-3 py-1.5",
        lg: "px-6 py-3",
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
            font-family: "Montserrat", "Plus Jakarta Sans", -apple-system, sans-serif;
            letter-spacing: -0.01em;
            border-radius: 8px;
          }
          .glass-btn-base:hover {
            transform: translateY(-1px);
          }
          .glass-btn-base:active {
            transform: translateY(1px);
          }

          /* ── 1. Flat & Solid Default Variant ── */
          .glass-btn-default {
            background-color: var(--accent);
            color: var(--accent-text);
            border: 1px solid var(--accent);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
          }
          .glass-btn-default:hover {
            background-color: var(--accent-hover);
            border-color: var(--accent-hover);
          }

          /* ── 2. Flat & Solid Danger Variant ── */
          .glass-btn-danger {
            background-color: var(--danger);
            color: #FFFFFF;
            border: 1px solid var(--danger);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
          }
          .glass-btn-danger:hover {
            filter: brightness(1.1);
          }

          /* ── 3. Flat & Solid Success Variant ── */
          .glass-btn-success {
            background-color: var(--success);
            color: #FFFFFF;
            border: 1px solid var(--success);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
          }
          .glass-btn-success:hover {
            filter: brightness(1.1);
          }

          /* ── 4. Flat & Solid Warning Variant ── */
          .glass-btn-warning {
            background-color: var(--warning);
            color: #000000;
            border: 1px solid var(--warning);
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
          }
          .glass-btn-warning:hover {
            filter: brightness(1.1);
          }

          /* ── 5. Flat & Solid Secondary Variant ── */
          .glass-btn-secondary {
            background-color: var(--bg-surface);
            color: var(--text-primary);
            border: 1px solid var(--border-default);
            box-shadow: 0 1px 2px rgba(0, 0, 0, 0.05);
          }
          .glass-btn-secondary:hover {
            background-color: var(--bg-hover);
            border-color: var(--border-strong);
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
