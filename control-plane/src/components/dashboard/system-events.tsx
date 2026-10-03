import { Activity } from 'lucide-react';

import { formatTimeUtc } from '@/lib/format';
import type { SystemEvent } from '@/types/dashboard';

/**
 * Recent system transitions.
 *
 * Each row shows the D-121-style trace id so an operator can follow an event
 * into the ledger. Trace ids are opaque references — never credentials, PANs or
 * personal data (D-114 / D-124).
 */
export function SystemEventsCard({ events }: { events: SystemEvent[] }) {
  return (
    <section className="flex flex-col gap-3" aria-label="رویدادهای اخیر سیستم">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 className="text-cp-heading font-semibold text-ink">رویدادهای اخیر</h2>
        <span className="inline-flex items-center gap-1 text-cp-caption text-ink-muted">
          <Activity aria-hidden="true" className="size-4" />
          حداکثر ۵ رکورد · فقط‌خواندنی
        </span>
      </header>

      {events.length === 0 ? (
        <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
          هیچ رویدادی ثبت نشده است — جریان لجر (D-121) هنوز متصل نیست.
        </p>
      ) : (
        <ol className="flex flex-col divide-y divide-edge">
          {events.map((event) => (
            <li key={event.id} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
              <div className="flex flex-wrap items-center gap-2">
                <time
                  dateTime={event.at}
                  className="font-mono text-cp-caption tabular-nums text-ink-muted"
                >
                  {formatTimeUtc(event.at)} UTC
                </time>
                <span className="font-mono text-cp-caption text-ink">{event.kind}</span>
              </div>
              <p className="text-cp-label text-ink">{event.summary}</p>
              <p className="font-mono text-cp-caption text-ink-muted">
                {event.traceId}
              </p>
            </li>
          ))}
        </ol>
      )}
    </section>
  );
}
