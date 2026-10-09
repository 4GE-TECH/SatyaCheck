import { forwardRef, type AnchorHTMLAttributes, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { Link, type LinkProps } from 'react-router-dom';
import { CheckCircle, Info, WarningCircle, CircleNotch } from '@phosphor-icons/react';
import type { Flag, Tone } from '../lib/verdict';

type Variant = 'primary' | 'secondary' | 'ghost' | 'danger';
type Size = 'md' | 'lg' | 'sm';

function classes(variant: Variant, size: Size, extra = '') {
  return `btn btn-${variant} btn-${size} ${extra}`.trim();
}

/** A trailing icon sits in its own circle inside the pill, and nudges on hover. */
function Trail({ children }: { children: ReactNode }) {
  return <span className="btn-trail" aria-hidden="true">{children}</span>;
}

export const Button = forwardRef<HTMLButtonElement, ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant; size?: Size; busy?: boolean; trail?: ReactNode;
}>(function Button({ variant = 'secondary', size = 'md', busy = false, trail, className = '', children, ...props }, ref) {
  return (
    <button ref={ref} type="button" {...props} disabled={props.disabled || busy} aria-busy={busy || undefined} className={classes(variant, size, `${trail ? 'has-trail ' : ''}${className}`)}>
      {busy && <CircleNotch size={16} weight="bold" className="spin" aria-hidden="true" />}
      {children}
      {trail && !busy && <Trail>{trail}</Trail>}
    </button>
  );
});

export function ButtonLink({ variant = 'secondary', size = 'md', className = '', trail, children, ...props }: LinkProps & { variant?: Variant; size?: Size; trail?: ReactNode }) {
  return (
    <Link {...props} className={classes(variant, size, `${trail ? 'has-trail ' : ''}${className}`)}>
      {children}
      {trail && <Trail>{trail}</Trail>}
    </Link>
  );
}

export function ButtonAnchor({ variant = 'secondary', size = 'md', className = '', ...props }: AnchorHTMLAttributes<HTMLAnchorElement> & { variant?: Variant; size?: Size }) {
  return <a {...props} className={classes(variant, size, className)} />;
}

export function IconButton({ label, children, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return (
    <button type="button" {...props} aria-label={label} title={label} className={`icon-btn ${className}`.trim()}>
      {children}
    </button>
  );
}

export function ToneChip({ tone, children, size = 'md' }: { tone: Tone; children: ReactNode; size?: 'md' | 'lg' }) {
  return <span className={`tone-chip tone-${tone} chip-${size}`}><span className="chip-dot" aria-hidden="true" />{children}</span>;
}

export function FlagBadge({ flag }: { flag: Flag }) {
  return (
    <span className={`flag tone-${flag.tone}`}>
      {flag.label}
    </span>
  );
}

const NOTICE_ICONS = { danger: WarningCircle, caution: WarningCircle, safe: CheckCircle, neutral: Info };

export function Notice({ tone = 'neutral', children, action }: { tone?: Tone; children: ReactNode; action?: ReactNode }) {
  const Icon = NOTICE_ICONS[tone];
  return (
    <div className={`notice tone-${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon size={20} weight="fill" aria-hidden="true" />
      <div className="notice-body">{children}</div>
      {action}
    </div>
  );
}

export function Kbd({ children }: { children: ReactNode }) {
  return <kbd className="kbd">{children}</kbd>;
}

export function SectionTitle({ title, note, id, action }: { title: string; note?: string; id?: string; action?: ReactNode }) {
  return (
    <div className="section-title">
      <div>
        <h2 id={id}>{title}</h2>
        {note && <p>{note}</p>}
      </div>
      {action}
    </div>
  );
}

export function Skeleton({ lines = 3 }: { lines?: number }) {
  return (
    <div className="skeleton" aria-hidden="true">
      {Array.from({ length: lines }, (_, i) => <span key={i} style={{ width: `${92 - i * 14}%` }} />)}
    </div>
  );
}
