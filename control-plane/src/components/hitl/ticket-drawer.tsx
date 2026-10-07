'use client';

import { FileDiff, History, ScrollText, ShieldCheck, X } from 'lucide-react';
import { useEffect, useRef } from 'react';

import { ToneBadge } from '@/components/ui/tone-badge';
import { VIEW_GATE_CLASS } from '@/components/ui/view-gate';
import { ROLE_LABEL, QUEUE_TYPE_LABEL, SEVERITY_META, STATUS_META } from '@/components/hitl/status-meta';

/**
 * Machine identifiers and raw engine artefacts inside the drawer (Phase
 * 27.13): taxonomy/queue/role codes, the engine source, the reviewer actor id,
 * the logical instants, the payload diff and the D-027 reasoning log. The
 * ticket id, summary, severity, status and Persian notes stay readable in both
 * views. The drawer is interaction-revealed, so it is verified in the browser
 * (see `scripts/check-view-isolation.mjs` — on-demand surfaces).
 */
const IDENTIFIER = VIEW_GATE_CLASS.technical;
import { cn } from '@/lib/utils';
import type { HitlTicket } from '@/types/hitl';

/**
 * Detail drawer for one ticket (D-171 §5.2).
 *
 * A native `<dialog>` is used rather than a hand-rolled overlay: it brings
 * focus trapping, Escape-to-close, and background inertness for free, so the
 * keyboard and screen-reader behaviour does not depend on our own JavaScript.
 * The drawer is read-only — the action panel outside it is the only place a
 * decision could ever be submitted, and every action there is disabled with a
 * stated reason.
 *
 * The reasoning log is REBUILT from D-027 events, each carrying its D-121 trace
 * id. It is deliberately not the model's raw chain-of-thought (D-171 §5.2).
 */
export function TicketDrawer({
  ticket,
  onClose,
}: {
  ticket: HitlTicket | null;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (ticket && !dialog.open) dialog.showModal();
    if (!ticket && dialog.open) dialog.close();
  }, [ticket]);

  if (!ticket) return null;

  const severity = SEVERITY_META[ticket.severity];
  const status = STATUS_META[ticket.resolution_status];
  const queueType = QUEUE_TYPE_LABEL[ticket.queue_type];
  const role = ROLE_LABEL[ticket.required_role];

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      onCancel={onClose}
      aria-labelledby="hitl-drawer-title"
      className={cn(
        'm-0 h-dvh max-h-none w-full max-w-xl bg-surface text-ink',
        'ms-auto me-0 p-0 backdrop:bg-canvas/80',
        'border-s border-edge',
      )}
    >
      <div className="flex h-full flex-col">
        <header className="flex items-start justify-between gap-3 border-b border-edge p-4">
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <ToneBadge
                tone={severity.tone}
                label={severity.label}
                code={severity.code}
                Icon={severity.Icon}
              />
              <ToneBadge
                tone={status.tone}
                label={status.label}
                code={status.code}
                Icon={status.Icon}
              />
            </div>
            <h2 id="hitl-drawer-title" className="text-cp-heading font-semibold text-ink">
              <span className="font-mono">{ticket.ticket_id}</span>
            </h2>
            <p className="text-cp-label text-ink-muted">{ticket.summary}</p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className={cn(
              'cp-target inline-flex items-center gap-1 rounded-[--radius-cp]',
              'border border-edge-strong bg-surface px-2 py-1',
              'text-cp-caption font-medium text-ink hover:bg-surface-muted',
            )}
          >
            <X aria-hidden="true" className="size-4" />
            بستن
          </button>
        </header>

        <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-4">
          <dl className="grid grid-cols-2 gap-3 text-cp-label">
            <div>
              <dt className="text-cp-caption text-ink-muted">نوع صف</dt>
              <dd className="text-ink">
                {queueType ? queueType.label : ticket.queue_type}{' '}
                <span className={`font-mono text-cp-caption text-ink-muted ${IDENTIFIER}`}>
                  ({ticket.queue_type})
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-cp-caption text-ink-muted">دسته</dt>
              <dd className="text-ink">
                {ticket.categoryLabel}{' '}
                <span className={`font-mono text-cp-caption text-ink-muted ${IDENTIFIER}`}>
                  ({ticket.category})
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-cp-caption text-ink-muted">نقش لازم</dt>
              <dd className="text-ink">
                {role.label}{' '}
                <span className={`font-mono text-cp-caption text-ink-muted ${IDENTIFIER}`}>
                  ({role.code})
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-cp-caption text-ink-muted">منبع</dt>
              <dd
                data-view-gate="technical"
                data-surface="hitl-drawer-identifiers"
                className={`font-mono text-cp-caption text-ink ${IDENTIFIER}`}
              >
                {ticket.source}
              </dd>
            </div>
            <div>
              <dt className="text-cp-caption text-ink-muted">سن (ساعت منطقی)</dt>
              <dd className="text-ink">
                {ticket.ageLogical}{' '}
                <span className={`font-mono text-cp-caption text-ink-muted ${IDENTIFIER}`}>
                  ({ticket.created_at_logical})
                </span>
              </dd>
            </div>
            <div>
              <dt className="text-cp-caption text-ink-muted">بازبین</dt>
              <dd className={`font-mono text-cp-caption text-ink ${IDENTIFIER}`}>
                {ticket.reviewer_actor_id ?? '—'}
              </dd>
              {ticket.reviewer_actor_id === null ? (
                <p className="text-cp-caption text-ink-muted">
                  هنوز بازبینی برای این کار ثبت نشده است.
                </p>
              ) : null}
            </div>
          </dl>

          <section
            className={`flex flex-col gap-2 ${IDENTIFIER}`}
            data-view-gate="technical"
            data-surface="hitl-drawer-payload-diff"
            aria-label="تفاوت بار مفید"
          >
            <h3 className="flex items-center gap-2 text-cp-label font-semibold text-ink">
              <FileDiff aria-hidden="true" className="size-4" />
              تفاوت payload و override
            </h3>
            <div className="overflow-x-auto rounded-[--radius-cp] border border-edge">
              <table className="w-full border-collapse text-cp-label">
                <caption className="sr-only">
                  مقایسهٔ مقدار فعلی و مقدار پیشنهادی برای هر فیلد
                </caption>
                <thead>
                  <tr className="bg-surface-muted text-cp-caption text-ink-muted">
                    <th scope="col" className="p-2 text-start font-medium">
                      فیلد
                    </th>
                    <th scope="col" className="p-2 text-start font-medium">
                      مقدار فعلی
                    </th>
                    <th scope="col" className="p-2 text-start font-medium">
                      مقدار پیشنهادی
                    </th>
                  </tr>
                </thead>
                <tbody>
                  {ticket.payload.map((field) => (
                    <tr key={field.field} className="border-t border-edge">
                      <th
                        scope="row"
                        className="p-2 text-start font-mono text-cp-caption font-normal text-ink"
                      >
                        {field.field}
                      </th>
                      <td className="p-2 font-mono text-cp-caption text-ink-muted tabular-nums">
                        {field.before}
                      </td>
                      <td
                        className={cn(
                          'p-2 font-mono text-cp-caption tabular-nums',
                          field.changed ? 'font-semibold text-ink' : 'text-ink-muted',
                        )}
                      >
                        {field.after}
                        {field.changed ? (
                          <span className="ms-2 font-sans text-cp-caption text-warning">
                            (تغییر)
                          </span>
                        ) : (
                          <span className="ms-2 font-sans text-cp-caption text-ink-muted">
                            (بدون تغییر)
                          </span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="font-mono text-cp-caption text-ink-muted">{ticket.payload_ref}</p>
          </section>

          <section
            className={`flex flex-col gap-2 ${IDENTIFIER}`}
            data-view-gate="technical"
            data-surface="hitl-drawer-reasoning-log"
            aria-label="لاگ استدلال"
          >
            <h3 className="flex items-center gap-2 text-cp-label font-semibold text-ink">
              <History aria-hidden="true" className="size-4" />
              لاگ استدلال (بازسازی از رویدادهای D-027)
            </h3>
            <p className="flex items-start gap-2 rounded-[--radius-cp] border border-edge bg-surface-muted p-2 text-cp-caption text-ink-muted">
              <ScrollText aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              این لاگ از رویدادهای ماندگار بازسازی شده است؛ زنجیرهٔ فکری خام مدل
              هرگز نمایش داده نمی‌شود (D-171 §5.2).
            </p>
            <ol className="flex flex-col divide-y divide-edge">
              {ticket.reasoning.map((entry) => (
                <li key={entry.seq} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="rounded-full border border-edge-strong px-2 text-cp-caption font-mono text-ink-muted tabular-nums">
                      {entry.seq}
                    </span>
                    <span className="font-mono text-cp-caption text-ink">{entry.event}</span>
                    <span className="font-mono text-cp-caption text-ink-muted tabular-nums">
                      {entry.atLogical}
                    </span>
                  </div>
                  <p className="text-cp-label text-ink">{entry.summary}</p>
                  <p className="font-mono text-cp-caption text-ink-muted">{entry.traceId}</p>
                </li>
              ))}
            </ol>
          </section>

          <p className="flex items-start gap-2 rounded-[--radius-cp] border border-edge-strong bg-surface-muted p-2 text-cp-caption text-ink-muted">
            <ShieldCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
            هر کنش روی این تیکت از موتور HITL و با توکن یک‌بارمصرف مالک انجام
            می‌شود (D-068 / D-146)؛ این رابط توکن نمی‌سازد و کلید امضا ندارد.
          </p>
        </div>
      </div>
    </dialog>
  );
}
