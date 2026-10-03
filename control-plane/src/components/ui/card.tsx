import type { ReactNode } from 'react';

import { cn } from '@/lib/utils';

export function Card({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <section
      className={cn(
        'rounded-[--radius-cp] border border-edge bg-surface',
        'p-4 sm:p-6',
        className,
      )}
    >
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
    <header className="mb-4 flex items-start justify-between gap-4">
      <div>
        <h2 className="text-cp-heading font-semibold text-ink">{title}</h2>
        {description ? (
          <p className="mt-1 text-cp-label text-ink-muted">{description}</p>
        ) : null}
      </div>
      {action ? <div className="shrink-0">{action}</div> : null}
    </header>
  );
}

/**
 * Fail-closed placeholder used by every route until its real data source is
 * wired. It states the truth (nothing is connected) rather than showing zeros,
 * which would read as a real measurement (D-171 §2.2).
 */
export function Placeholder({ children }: { children: ReactNode }) {
  return (
    <div
      className={cn(
        'rounded-[--radius-cp] border border-dashed border-edge-strong',
        'bg-surface-muted p-4 text-cp-label text-ink-muted',
      )}
    >
      {children}
    </div>
  );
}
