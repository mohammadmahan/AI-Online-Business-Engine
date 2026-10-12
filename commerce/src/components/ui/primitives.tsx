import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

/**
 * D-172 §2 — shared primitives.
 *
 * Same token-only approach as the control plane: no raw hex (ESLint-enforced),
 * logical CSS properties so RTL is the default rather than an afterthought,
 * visible focus outlines from `globals.css`, and state conveyed by icon + Persian
 * label + a Latin status code so it never depends on colour alone (D-171 §3.5).
 */

export type Tone = 'neutral' | 'primary' | 'success' | 'warning' | 'danger';

const TONE_CLASS: Record<Tone, string> = {
  neutral: 'border-edge bg-surface-muted text-ink',
  primary: 'border-primary bg-primary text-on-primary',
  success: 'border-success bg-success text-on-success',
  warning: 'border-warning bg-warning text-on-warning',
  danger: 'border-danger bg-danger text-on-danger',
};

export function Badge({
  tone = 'neutral',
  children,
  className,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-[--radius-cp] border px-2 py-0.5 text-cp-caption font-medium',
        TONE_CLASS[tone],
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Card({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <section className={cn('rounded-[--radius-cp] border border-edge bg-surface p-4 sm:p-6', className)}>
      {children}
    </section>
  );
}

export function CardHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="mb-4 flex flex-wrap items-start justify-between gap-3">
      <div>
        <h2 className="text-cp-heading font-semibold text-ink">{title}</h2>
        {description ? <p className="mt-1 text-cp-label text-ink-muted">{description}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}

export function PageHeader({
  title,
  description,
  action,
}: {
  title: string;
  description?: string;
  action?: ReactNode;
}) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div>
        <h1 className="text-cp-display font-bold text-ink">{title}</h1>
        {description ? <p className="mt-1 text-cp-label text-ink-muted">{description}</p> : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}

/**
 * Fail-closed banner. Used for "not connected", "not configured" and error
 * states: the panel states the truth instead of rendering empty tables that
 * read as real (zero) data.
 */
export function Banner({
  tone = 'warning',
  title,
  children,
}: {
  tone?: Tone;
  title: string;
  children?: ReactNode;
}) {
  return (
    <div className={cn('rounded-[--radius-cp] border p-4', TONE_CLASS[tone])} role="status">
      <p className="text-cp-label font-semibold">{title}</p>
      {children ? <div className="mt-1 text-cp-label">{children}</div> : null}
    </div>
  );
}

export function Placeholder({ children }: { children: ReactNode }) {
  return (
    <div className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-4 text-cp-label text-ink-muted">
      {children}
    </div>
  );
}

export function Field({
  label,
  hint,
  error,
  htmlFor,
  children,
  required,
}: {
  label: string;
  hint?: string;
  error?: string;
  htmlFor?: string;
  children: ReactNode;
  required?: boolean;
}) {
  return (
    <div className="flex flex-col gap-1">
      <label htmlFor={htmlFor} className="text-cp-label font-medium text-ink">
        {label}
        {required ? <span aria-hidden="true"> *</span> : null}
      </label>
      {children}
      {hint ? <p className="text-cp-caption text-ink-muted">{hint}</p> : null}
      {error ? (
        <p className="text-cp-caption font-medium text-danger" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  );
}

export const inputClass =
  'cp-target w-full rounded-[--radius-cp] border border-edge-strong bg-surface px-3 py-2 text-cp-body text-ink placeholder:text-ink-muted';

export const buttonClass = {
  primary:
    'cp-target inline-flex items-center gap-2 rounded-[--radius-cp] border border-primary bg-primary px-4 py-2 text-cp-label font-medium text-on-primary disabled:opacity-60',
  neutral:
    'cp-target inline-flex items-center gap-2 rounded-[--radius-cp] border border-edge-strong bg-surface px-3 py-2 text-cp-label text-ink disabled:opacity-60',
  danger:
    'cp-target inline-flex items-center gap-2 rounded-[--radius-cp] border border-danger bg-danger px-3 py-2 text-cp-label font-medium text-on-danger disabled:opacity-60',
} as const;

export function Table({
  caption,
  head,
  children,
}: {
  caption: string;
  head: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="w-full overflow-x-auto">
      <table className="w-full min-w-[48rem] border-collapse text-cp-label">
        <caption className="sr-only">{caption}</caption>
        <thead className="bg-surface-muted text-ink">{head}</thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}

export function Th({ children, scope = 'col' }: { children: ReactNode; scope?: 'col' | 'row' }) {
  return (
    <th scope={scope} className="border-b border-edge px-3 py-2 text-start font-semibold">
      {children}
    </th>
  );
}

export function Td({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <td className={cn('border-b border-edge px-3 py-2 align-middle', className)}>{children}</td>
  );
}

/** Machine identifiers stay Latin and isolated inside RTL text. */
export function Code({ children }: { children: ReactNode }) {
  return <span className="cp-code text-cp-caption">{children}</span>;
}

/**
 * A loading placeholder (§3.3). Token-only and `aria-hidden`, so a screen reader
 * hears the page's real landmarks rather than a row of invisible boxes; the pulse
 * is switched off by the global `prefers-reduced-motion` rule in `globals.css`.
 */
export function Skeleton({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cn('block animate-pulse rounded-[--radius-cp] bg-surface-muted', className)}
    />
  );
}
