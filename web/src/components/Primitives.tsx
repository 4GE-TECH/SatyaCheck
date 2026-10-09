import { ArrowRight, CircleAlert, CircleCheck, Info, LoaderCircle } from 'lucide-react';
import type { ButtonHTMLAttributes, ReactNode } from 'react';
import type { Flag, Tone } from '../lib/presentation';

export function Brand() {
  return (
    <span className="brand">
      <img className="brand-mark" src="/brand/satyacheck-logo.jpg" alt="" width="36" height="36" />
      <span className="brand-name">SatyaCheck</span>
    </span>
  );
}

type ButtonVariant = 'primary' | 'secondary' | 'quiet' | 'danger';

export function Button({
  children,
  variant = 'primary',
  busy = false,
  className = '',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; busy?: boolean }) {
  return (
    <button
      {...props}
      disabled={props.disabled || busy}
      className={`button button-${variant} ${className}`}
      aria-busy={busy || undefined}
    >
      {busy && <LoaderCircle size={17} className="spin" aria-hidden="true" />}
      {children}
    </button>
  );
}

const noticeIcons = { danger: CircleAlert, warning: CircleAlert, success: CircleCheck, neutral: Info };

export function Notice({ children, tone = 'neutral' }: { children: ReactNode; tone?: Tone }) {
  const Icon = noticeIcons[tone];
  return (
    <div className={`notice tone-${tone}`} role={tone === 'danger' ? 'alert' : 'status'}>
      <Icon size={19} aria-hidden="true" />
      <div>{children}</div>
    </div>
  );
}

export function PageHeading({ title, description, action }: { title: string; description: string; action?: ReactNode }) {
  return (
    <header className="page-heading">
      <div>
        <h1>{title}</h1>
        <p>{description}</p>
      </div>
      {action}
    </header>
  );
}

export function EmptyState({ icon, title, children }: { icon: ReactNode; title: string; children: ReactNode }) {
  return (
    <div className="empty-state">
      <span className="empty-icon" aria-hidden="true">{icon}</span>
      <h3>{title}</h3>
      <div>{children}</div>
    </div>
  );
}

export function FlagMark({ flag }: { flag: Flag }) {
  return (
    <span className={`flag tone-${flag.tone}`} title={flag.label}>
      <span aria-hidden="true">{flag.mark}</span>
      <span className="visually-hidden">{flag.label}</span>
    </span>
  );
}

export function BandBadge({ tone, children }: { tone: Tone; children: ReactNode }) {
  return <span className={`band-badge tone-${tone}`}>{children}</span>;
}

/**
 * A reference-interval bar: tinted zones along a 0–100 scale with a tick at the
 * observed value. Zones are optional; without them the bar is a plain scale.
 */
export function RangeBar({
  value,
  zones = [],
  label,
  invert = false,
}: {
  value: number | null;
  zones?: { from: number; to: number; tone: Tone; label?: string }[];
  label: string;
  invert?: boolean;
}) {
  const position = value == null || !Number.isFinite(value) ? null : Math.max(0, Math.min(100, value));
  return (
    <div className={`range-bar ${invert ? 'invert' : ''}`} role="img" aria-label={label}>
      <div className="range-track">
        {zones.map(zone => (
          <span
            key={`${zone.from}-${zone.to}`}
            className={`range-zone tone-${zone.tone}`}
            style={{ left: `${zone.from}%`, width: `${zone.to - zone.from}%` }}
          />
        ))}
        {position != null && (
          <span className="range-position" style={{ transform: `translateX(${position}%)` }}>
            <span className="range-tick" />
          </span>
        )}
      </div>
    </div>
  );
}

export function NextArrow() {
  return <ArrowRight size={17} aria-hidden="true" />;
}
