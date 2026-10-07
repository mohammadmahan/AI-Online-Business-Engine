'use client';

import { Eye, ShieldQuestion } from 'lucide-react';

import { ToneBadge } from '@/components/ui/tone-badge';
import { VIEW_GATE_CLASS } from '@/components/ui/view-gate';
import { SEVERITY_META, STATUS_META } from '@/components/hitl/status-meta';

/** Taxonomy code and engine source — machine identifiers (Phase 27.13). */
const IDENTIFIER = VIEW_GATE_CLASS.technical;
import { cn } from '@/lib/utils';
import type { HitlTicket } from '@/types/hitl';

/**
 * The card-table over AI decisions (D-171 §5.2).
 *
 * Ordered severity-first (the caller sorts; this component preserves the given
 * order). Each row is a real `<button>`, so the detail drawer is reachable by
 * click AND by keyboard — never by hover alone (D-171 §3.2). The table is
 * read-only: it renders what the engine holds and decides nothing.
 *
 * The table is scrollable on narrow screens rather than reflowed into cards,
 * because column alignment is what makes a dense queue scannable; the wrapper
 * keeps the page itself from scrolling sideways.
 */
export function TicketTable({
  tickets,
  onSelect,
}: {
  tickets: HitlTicket[];
  onSelect: (ticket: HitlTicket) => void;
}) {
  if (tickets.length === 0) {
    return (
      <p className="flex items-center gap-2 rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
        <ShieldQuestion aria-hidden="true" className="size-4 shrink-0" />
        هیچ تیکتی با این فیلترها وجود ندارد — و صف خالی هرگز «تأییدشده» معنا
        نمی‌شود.
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-[--radius-cp] border border-edge">
      <table className="w-full border-collapse text-cp-label">
        <caption className="sr-only">
          فهرست تیکت‌های تأیید انسانی، مرتب‌شده بر پایهٔ شدت
        </caption>
        <thead>
          <tr className="bg-surface-muted text-cp-caption text-ink-muted">
            <th scope="col" className="p-2 text-start font-medium">
              شناسه
            </th>
            <th scope="col" className="p-2 text-start font-medium">
              شدت
            </th>
            <th scope="col" className="p-2 text-start font-medium">
              دسته
            </th>
            <th
              scope="col"
              data-view-gate="technical"
              data-surface="hitl-table-identifiers"
              className={`p-2 text-start font-medium ${IDENTIFIER}`}
            >
              منبع
            </th>
            <th scope="col" className="p-2 text-start font-medium">
              سن
            </th>
            <th scope="col" className="p-2 text-start font-medium">
              وضعیت
            </th>
            <th scope="col" className="p-2 text-start font-medium">
              جزئیات
            </th>
          </tr>
        </thead>
        <tbody>
          {tickets.map((ticket) => {
            const severity = SEVERITY_META[ticket.severity];
            const status = STATUS_META[ticket.resolution_status];
            return (
              <tr key={ticket.ticket_id} className="border-t border-edge align-top">
                <th scope="row" className="p-2 text-start font-normal">
                  <span className="font-mono text-cp-label text-ink">{ticket.ticket_id}</span>
                  <span className="mt-1 block max-w-xs text-cp-caption text-ink-muted">
                    {ticket.summary}
                  </span>
                </th>
                <td className="p-2">
                  <ToneBadge
                    tone={severity.tone}
                    label={severity.label}
                    code={severity.code}
                    Icon={severity.Icon}
                  />
                </td>
                <td className="p-2 text-cp-label text-ink">
                  {ticket.categoryLabel}
                  <span
                    className={`mt-1 block font-mono text-cp-caption text-ink-muted ${IDENTIFIER}`}
                  >
                    {ticket.category}
                  </span>
                </td>
                <td className={`p-2 font-mono text-cp-caption text-ink-muted ${IDENTIFIER}`}>
                  {ticket.source}
                </td>
                <td className="p-2 text-cp-label text-ink tabular-nums">{ticket.ageLogical}</td>
                <td className="p-2">
                  <ToneBadge
                    tone={status.tone}
                    label={status.label}
                    code={status.code}
                    Icon={status.Icon}
                  />
                </td>
                <td className="p-2">
                  <button
                    type="button"
                    onClick={() => onSelect(ticket)}
                    aria-label={`نمایش جزئیات تیکت ${ticket.ticket_id}`}
                    className={cn(
                      'cp-target inline-flex items-center gap-1 rounded-[--radius-cp]',
                      'border border-edge-strong bg-surface px-2 py-1',
                      'text-cp-caption font-medium text-ink hover:bg-surface-muted',
                    )}
                  >
                    <Eye aria-hidden="true" className="size-4" />
                    نمایش
                  </button>
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
