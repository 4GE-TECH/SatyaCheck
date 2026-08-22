import * as React from "react";
import { cva, type VariantProps } from "class-variance-authority";

function cn(...inputs: (string | undefined | null | false)[]): string {
  return inputs.filter(Boolean).join(" ");
}

const glassButtonVariants = cva(
  "relative isolate all-unset cursor-pointer rounded-full transition-all duration-200 border backdrop-blur-md inline-flex items-center justify-center font-medium font-mono select-none disabled:opacity-50 disabled:cursor-not-allowed",
  {
    variants: {
      variant: {
        default:
          "glass-btn-default bg-white/80 dark:bg-white/[0.07] text-slate-900 dark:text-white border-slate-300 dark:border-white/20 hover:bg-white/95 dark:hover:bg-white/[0.12] hover:border-slate-400 dark:hover:border-white/30 shadow-sm",
        danger:
          "glass-btn-danger bg-red-50/90 dark:bg-red-950/40 text-red-700 dark:text-red-300 border-red-300 dark:border-red-500/40 hover:bg-red-100 dark:hover:bg-red-900/50 hover:border-red-400 dark:hover:border-red-500/60 shadow-sm",
        success:
          "glass-btn-success bg-emerald-50/90 dark:bg-emerald-950/40 text-emerald-700 dark:text-emerald-300 border-emerald-300 dark:border-emerald-500/40 hover:bg-emerald-100 dark:hover:bg-emerald-900/50 hover:border-emerald-400 dark:hover:border-emerald-500/60 shadow-sm",
        warning:
          "glass-btn-warning bg-amber-50/90 dark:bg-amber-950/40 text-amber-800 dark:text-amber-300 border-amber-300 dark:border-amber-500/40 hover:bg-amber-100 dark:hover:bg-amber-900/50 hover:border-amber-400 dark:hover:border-amber-500/60 shadow-sm",
        secondary:
          "glass-btn-secondary bg-slate-100/80 dark:bg-slate-900/50 text-slate-700 dark:text-slate-300 border-slate-300 dark:border-slate-700 hover:bg-slate-200/90 dark:hover:bg-slate-800/70 hover:border-slate-400 dark:hover:border-slate-600 shadow-sm",
      },
      size: {
        default: "text-sm font-semibold",
        sm: "text-xs font-semibold",
        lg: "text-base font-bold",
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
  "glass-button-text relative flex items-center justify-center gap-2 select-none tracking-tight w-full",
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
          .glass-button-wrap {
            position: relative;
            display: inline-flex;
            border-radius: 9999px;
            transition: transform 0.15s ease, filter 0.15s ease;
          }
          .glass-button-wrap:hover {
            transform: translateY(-1px);
          }
          .glass-button-wrap:active {
            transform: translateY(1px);
          }
          .glass-button {
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.45),
              0 4px 12px -2px rgba(0, 0, 0, 0.12);
          }
          html.dark .glass-button {
            box-shadow:
              inset 0 1px 1px 0 rgba(255, 255, 255, 0.2),
              0 6px 16px -2px rgba(0, 0, 0, 0.6);
          }
          .glass-button-shadow {
            position: absolute;
            inset: 0;
            border-radius: 9999px;
            pointer-events: none;
            opacity: 0;
            transition: opacity 0.2s ease;
          }
          .glass-button-wrap:hover .glass-button-shadow {
            opacity: 1;
          }
        `}</style>

        <div
          className={cn(
            "glass-button-wrap cursor-pointer rounded-full",
            className
          )}
        >
          <button
            className={cn("glass-button", glassButtonVariants({ variant, size }))}
            ref={ref}
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
          <div className="glass-button-shadow rounded-full"></div>
        </div>
      </>
    );
  }
);
GlassButton.displayName = "GlassButton";

export { GlassButton, glassButtonVariants };
