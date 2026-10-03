'use client';

import { Filter, ListFilter, X } from 'lucide-react';
import { useMemo, useState } from 'react';

import { SEVERITY_META, STATUS_META } from '@/components/hitl/status-meta';
import { cn } from '@/lib/utils';
import type { HitlSeverity, HitlTicket, ResolutionStatus } from '@/types/hitl';

const SEVERITIES: HitlSeverity[] = ['critical', 'high', 'medium', 'low'];
const STATUSES: ResolutionStatus[] = [
  'PENDING_REVIEW',
  'CLAIMED',
  'APPROVED',
  'REJECTED',
  'MODIFIED',
  'ESCALATED',
  'EXPIRED',
];

/** Filters are a client concern: they never change what the server rendered. */
export interface QueueFilterState {
  severities: HitlSeverity[];
  statuses: ResolutionStatus[];
  /** Free-text query matched against ticket id, category and summary. */
  query: string;
}

export const EMPTY_FILTERS: QueueFilterState = {
  severities: [],
  statuses: [],
  query: '',
};

/** Apply the filter state to a ticket list. Exported so the page can show counts. */
export function applyFilters(
  tickets: HitlTicket[],
  filters: QueueFilterState,
): HitlTicket[] {
  const needle = filters.query.trim().toLowerCase();
  return tickets.filter((ticket) => {
    if (filters.severities.length > 0 && !filters.severities.includes(ticket.severity)) {
      return false;
    }
    if (filters.statuses.length > 0 && !filters.statuses.includes(ticket.resolution_status)) {
      return false;
    }
    if (needle.length > 0) {
      const haystack = [
        ticket.ticket_id,
        ticket.category,
        ticket.categoryLabel,
        ticket.summary,
        ticket.source,
      ]
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(needle)) return false;
    }
    return true;
  });
}

/**
 * Severity / status / text filters (D-171 §5.2).
 *
 * Filtering is purely presentational and never changes a ticket's state: it
 * cannot approve, claim or expire anything. The active-filter count is stated
 * in words as well as visually, so the operator always knows what is hidden.
 */
export function QueueFilters({
  filters,
  onChange,
  shown,
  total,
}: {
  filters: QueueFilterState;
  onChange: (next: QueueFilterState) => void;
  shown: number;
  total: number;
}) {
  const [open, setOpen] = useState(false);

  const activeCount =
    filters.severities.length + filters.statuses.length + (filters.query.trim() ? 1 : 0);

  const severityOptions = useMemo(
    () => SEVERITIES.map((severity) => ({ value: severity, ...SEVERITY_META[severity] })),
    [],
  );

  const toggleSeverity = (severity: HitlSeverity) => {
    const next = filters.severities.includes(severity)
      ? filters.severities.filter((value) => value !== severity)
      : [...filters.severities, severity];
    onChange({ ...filters, severities: next });
  };

  const toggleStatus = (status: ResolutionStatus) => {
    const next = filters.statuses.includes(status)
      ? filters.statuses.filter((value) => value !== status)
      : [...filters.statuses, status];
    onChange({ ...filters, statuses: next });
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls="hitl-filter-panel"
          className={cn(
            'cp-target inline-flex items-center gap-2 rounded-[--radius-cp]',
            'border border-edge-strong bg-surface px-3 py-2',
            'text-cp-label font-medium text-ink hover:bg-surface-muted',
          )}
        >
          <Filter aria-hidden="true" className="size-4" />
          فیلترها
          {activeCount > 0 ? (
            <span className="rounded-full bg-primary px-2 text-cp-caption font-semibold text-on-primary tabular-nums">
              {activeCount}
            </span>
          ) : null}
        </button>

        <label className="flex items-center gap-2">
          <span className="sr-only">جست‌وجو در تیکت‌ها</span>
          <input
            type="search"
            value={filters.query}
            onChange={(event) => onChange({ ...filters, query: event.target.value })}
            placeholder="جست‌وجو در شناسه، دسته یا خلاصه…"
            className={cn(
              'cp-target w-64 max-w-full rounded-[--radius-cp] border border-edge-strong',
              'bg-surface px-3 py-2 text-cp-label text-ink placeholder:text-ink-muted',
            )}
          />
        </label>

        <p className="text-cp-caption text-ink-muted" role="status">
          نمایش <span className="tabular-nums">{shown}</span> از{' '}
          <span className="tabular-nums">{total}</span> تیکت
        </p>

        {activeCount > 0 ? (
          <button
            type="button"
            onClick={() => onChange(EMPTY_FILTERS)}
            className="cp-target inline-flex items-center gap-1 rounded-[--radius-cp] px-2 py-1 text-cp-caption font-medium text-primary hover:underline"
          >
            <X aria-hidden="true" className="size-4" />
            پاک‌کردن فیلترها
          </button>
        ) : null}
      </div>

      {open ? (
        <div
          id="hitl-filter-panel"
          className="flex flex-col gap-3 rounded-[--radius-cp] border border-edge bg-surface-muted p-3"
        >
          <fieldset className="flex flex-col gap-2">
            <legend className="flex items-center gap-2 text-cp-label font-semibold text-ink">
              <ListFilter aria-hidden="true" className="size-4" />
              شدت
            </legend>
            <div className="flex flex-wrap gap-2">
              {severityOptions.map((option) => {
                const active = filters.severities.includes(option.value);
                return (
                  <button
                    key={option.value}
                    type="button"
                    onClick={() => toggleSeverity(option.value)}
                    aria-pressed={active}
                    className={cn(
                      'cp-target rounded-full border px-3 py-1 text-cp-caption font-medium',
                      active
                        ? 'border-primary bg-primary text-on-primary'
                        : 'border-edge-strong bg-surface text-ink hover:bg-surface-muted',
                    )}
                  >
                    {option.label} ({option.code})
                  </button>
                );
              })}
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-cp-label font-semibold text-ink">وضعیت</legend>
            <div className="flex flex-wrap gap-2">
              {STATUSES.map((status) => {
                const meta = STATUS_META[status];
                const active = filters.statuses.includes(status);
                return (
                  <button
                    key={status}
                    type="button"
                    onClick={() => toggleStatus(status)}
                    aria-pressed={active}
                    className={cn(
                      'cp-target rounded-full border px-3 py-1 text-cp-caption font-medium',
                      active
                        ? 'border-primary bg-primary text-on-primary'
                        : 'border-edge-strong bg-surface text-ink hover:bg-surface-muted',
                    )}
                  >
                    {meta.label} ({meta.code})
                  </button>
                );
              })}
            </div>
          </fieldset>
        </div>
      ) : null}
    </div>
  );
}
