'use client';

import { useMemo, useState } from 'react';

import { ActionPanel } from '@/components/hitl/action-panel';
import { QueueFilters, applyFilters, EMPTY_FILTERS, type QueueFilterState } from '@/components/hitl/queue-filters';
import { TicketDrawer } from '@/components/hitl/ticket-drawer';
import { TicketTable } from '@/components/hitl/ticket-table';
import { Card } from '@/components/ui/card';
import type { HitlQueueSnapshot, HitlTicket } from '@/types/hitl';

/**
 * Client coordinator for the queue.
 *
 * The server renders the snapshot; this component owns only PRESENTATION state
 * (which filters are active, which ticket's drawer is open). It never mutates a
 * ticket and never calls a network endpoint: the queue is read-only in this
 * phase, and every decision path is rendered disabled with its reason.
 *
 * Keeping this boundary means live wiring replaces the data source, not the
 * interaction model.
 */
export function QueueWorkspace({ snapshot }: { snapshot: HitlQueueSnapshot }) {
  const [filters, setFilters] = useState<QueueFilterState>(EMPTY_FILTERS);
  const [selected, setSelected] = useState<HitlTicket | null>(null);

  const visible = useMemo(
    () => applyFilters(snapshot.tickets, filters),
    [snapshot.tickets, filters],
  );

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <QueueFilters
          filters={filters}
          onChange={setFilters}
          shown={visible.length}
          total={snapshot.tickets.length}
        />
      </Card>

      <Card>
        <TicketTable tickets={visible} onSelect={setSelected} />
      </Card>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card>
          <ActionPanel
            actions={snapshot.actions}
            tokenPresent={snapshot.tokenPresent}
            selected={selected}
          />
        </Card>
        <Card>
          <section className="flex flex-col gap-3" aria-label="خلاصه‌ی صف">
            <h2 className="text-cp-heading font-semibold text-ink">خلاصه‌ی صف</h2>
            <dl className="grid grid-cols-2 gap-3 text-cp-label">
              <div>
                <dt className="text-cp-caption text-ink-muted">کل تیکت‌ها</dt>
                <dd className="text-cp-heading font-semibold tabular-nums text-ink">
                  {snapshot.summary.total}
                </dd>
              </div>
              <div>
                <dt className="text-cp-caption text-ink-muted">در انتظار بازبینی</dt>
                <dd className="text-cp-heading font-semibold tabular-nums text-warning">
                  {snapshot.summary.byStatus.PENDING_REVIEW}
                </dd>
              </div>
              <div>
                <dt className="text-cp-caption text-ink-muted">بحرانی</dt>
                <dd className="text-cp-heading font-semibold tabular-nums text-danger">
                  {snapshot.summary.bySeverity.critical}
                </dd>
              </div>
              <div>
                <dt className="text-cp-caption text-ink-muted">قفل‌شده</dt>
                <dd className="text-cp-heading font-semibold tabular-nums text-ink">
                  {snapshot.summary.byStatus.CLAIMED}
                </dd>
              </div>
            </dl>

            {snapshot.summary.hasCriticalPending ? (
              <p
                className="rounded-[--radius-cp] border border-danger bg-surface p-2 text-cp-label text-danger"
                role="alert"
              >
                موردی با شدت بحرانی در انتظار تصمیم انسانی است — تا تصمیم مالک،
                هیچ کنش خودکاری مجاز نیست (D-104).
              </p>
            ) : (
              <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-2 text-cp-label text-ink-muted">
                موردی با شدت بحرانی در انتظار نیست. این وضعیت «تأییدشده» معنا
                نمی‌دهد؛ صف همچنان نیازمند بازبینی است.
              </p>
            )}
          </section>
        </Card>
      </div>

      <TicketDrawer ticket={selected} onClose={() => setSelected(null)} />
    </div>
  );
}
