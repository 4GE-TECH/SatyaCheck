import { useEffect, useRef, type ButtonHTMLAttributes, type ReactNode } from 'react';
import { AlertCircle, ArrowUpRight, LoaderCircle, X } from 'lucide-react';
import { motion, useReducedMotion } from 'motion/react';
export const ease = [.23, 1, .32, 1] as const;
export function Button({ children, variant = 'solid', busy = false, className = '', ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'solid'|'outline'|'ghost'; busy?: boolean }) {
  return <button {...props} disabled={props.disabled || busy} aria-busy={busy || undefined} className={`button ${variant} ${className}`}>{busy && <LoaderCircle className="spinner" size={17} aria-hidden="true" />}{children}</button>;
}
export function ErrorNote({ children }: { children: ReactNode }) { return <div className="error-note" role="alert"><AlertCircle size={19} aria-hidden="true"/><div>{children}</div></div>; }
export function PageIntro({ eyebrow, title, description, action }: { eyebrow: string; title: string; description: string; action?: ReactNode }) {
  return <header className="page-intro"><div><p className="eyebrow">{eyebrow}</p><h1 tabIndex={-1}>{title}</h1><p className="intro-description">{description}</p></div>{action}</header>;
}
export function Reveal({ children, className = '', delay = 0 }: { children: ReactNode; className?: string; delay?: number }) {
  const reduced = useReducedMotion();
  if (reduced) return <div className={className}>{children}</div>;
  return <motion.div className={className} initial={{ opacity: 0, transform: reduced ? 'none' : 'translateY(16px)' }} whileInView={{ opacity: 1, transform: 'translateY(0)' }} viewport={{ once: true, amount: .05 }} transition={{ duration: reduced ? .1 : .55, delay: reduced ? 0 : delay, ease }}>{children}</motion.div>;
}
export function Modal({ children, title, close, wide = false }: { children: ReactNode; title: string; close: () => void; wide?: boolean }) {
  const dialog = useRef<HTMLDialogElement>(null);
  const previous = useRef(document.activeElement as HTMLElement | null);
  useEffect(() => {
    const element = dialog.current!;
    element.showModal();
    (element.querySelector<HTMLElement>('input:not([type="file"]), textarea') || element.querySelector<HTMLElement>('button'))?.focus();
    const overflow = document.body.style.overflow; document.body.style.overflow = 'hidden';
    return () => { element.close(); document.body.style.overflow = overflow; previous.current?.focus(); };
  }, []);
  return <dialog ref={dialog} className={`modal ${wide ? 'wide' : ''}`} aria-labelledby="modal-heading" onCancel={event => { event.preventDefault(); close(); }} onClick={event => { if (event.target === event.currentTarget) { const bounds = event.currentTarget.getBoundingClientRect(); if (event.clientX < bounds.left || event.clientX > bounds.right || event.clientY < bounds.top || event.clientY > bounds.bottom) close(); } }}><div className="modal-top"><h2 id="modal-heading">{title}</h2><button className="icon-button" onClick={close} aria-label="Close dialog"><X size={20}/></button></div>{children}</dialog>;
}
export function External({ href, children }: { href: string; children: ReactNode }) { return <a className="text-link" href={href} target="_blank" rel="noreferrer">{children}<ArrowUpRight size={15} aria-hidden="true"/><span className="sr-only"> (opens a new tab)</span></a>; }
