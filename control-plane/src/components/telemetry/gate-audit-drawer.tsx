'use client';

import { ScrollText, ShieldAlert, X } from 'lucide-react';
import { useEffect, useRef } from 'react';

import { GATE_STATUS_META } from '@/components/telemetry/status-meta';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatTimeUtc } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { PipelineGate } from '@/types/telemetry';

/**
 * Audit rationale drawer for a non-PASS gate (D-171 §5.4).
 *
 * A native `<dialog>` is used rather than a hand-rolled overlay: focus
 * trapping, Escape-to-close and background inertness come from the platform, so
 * keyboard and screen-reader behaviour does not depend on our JavaScript
 * (same precedent as the HITL ticket drawer).
 *
 * The drawer is READ-ONLY and says so: it shows WHY a gate is blocked or why a
 * bypass was refused, and states that this plane holds no path to force the
 * gate. The record is the verifier's audit entry (D-121 trace id, D-093 logical
 * instant), never a credential.
 */
export function GateAuditDrawer({
  gate,
  onClose,
}: {
  gate: PipelineGate | null;
  onClose: () => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (gate && !dialog.open) dialog.showModal();
    if (!gate && dialog.open) dialog.close();
  }, [gate]);

  if (!gate) return null;

  const meta = GATE_STATUS_META[gate.status];
  const audit = gate.audit;

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      onCancel={onClose}
      aria-labelledby="gate-audit-title"
      className={cn(
        'm-0 h-dvh max-h-none w-full max-w-xl bg-surface text-ink',
        'ms-auto me-0 p-0 backdrop:bg-canvas/80',
        'border-s border-edge',
      )}
    >
      <div className="flex h-full flex-col">
        <header className="flex items-start justify-between gap-3 border-b border-edge p-4">
          <div className="flex flex-col gap-2">
            <ToneBadge tone={meta.tone} label={meta.label} code={meta.code} Icon={meta.Icon} />
            <h2 id="gate-audit-title" className="text-cp-heading font-semibold text-ink">
              <span dir="ltr" className="font-mono">
                {gate.id}
              </span>{' '}
              · {gate.titleFa}
            </h2>
            <p className="text-cp-label text-ink-muted">{gate.descriptionFa}</p>
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
          {audit !== null ? (
            <>
              <section className="flex flex-col gap-2" aria-label="رکورد حسابرسی">
                <h3 className="flex items-center gap-2 text-cp-label font-semibold text-ink">
                  <ScrollText aria-hidden="true" className="size-4" />
                  رکورد حسابرسی (D-121)
                </h3>
                <p
                  className={cn(
                    'rounded-[--radius-cp] border border-edge bg-surface-muted p-3',
                    'border-s-4 text-cp-label text-ink',
                    gate.status === 'BLOCKED' ? 'border-s-danger' : 'border-s-warning',
                  )}
                >
                  {audit.reasonFa}
                </p>
                <dl className="grid grid-cols-1 gap-2 text-cp-label sm:grid-cols-2">
                  <div>
                    <dt className="text-cp-caption text-ink-muted">شناسه‌ی ردیابی</dt>
                    <dd className="font-mono text-cp-caption text-ink">
                      <span dir="ltr">{audit.traceId}</span>
                    </dd>
                  </div>
                  <div>
                    <dt className="text-cp-caption text-ink-muted">لحظه‌ی منطقی (D-093)</dt>
                    <dd className="font-mono text-cp-caption text-ink">
                      <span dir="ltr">{audit.atLogical}</span>
                    </dd>
                  </div>
                </dl>
              </section>

              <p className="flex items-start gap-2 rounded-[--radius-cp] border border-edge-strong bg-surface-muted p-2 text-cp-caption text-ink-muted">
                <ShieldAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                {gate.status === 'BYPASS_PREVENTED' ? (
                  <>
                    تلاش برای عبور اجباری رد شده است: توکن یک‌بارمصرف مالک دقیقاً یک‌بار مصرف
                    می‌شود و درخواست تکراری یا منقضی پذیرفته نمی‌شود (D-146/D-147).
                  </>
                ) : (
                  <>
                    گیت تا رفع علت مسدود می‌ماند؛ این رابط هیچ مسیری برای بازکردن اجباری گیت
                    ندارد و کنش اضطراری آن غیرفعال است (fail-closed).
                  </>
                )}
              </p>
            </>
          ) : (
            <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
              برای این گیت رکورد شکستی ثبت نشده است؛ حکم آن «{meta.label}» است و شواهد
              تأییدشده‌ای ندارد.
            </p>
          )}

          <dl className="flex flex-col gap-1 text-cp-caption">
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-ink-muted">شواهد</dt>
              <dd className={cn('font-mono', gate.evidence === null ? 'text-ink-muted' : 'text-ink')}>
                {gate.evidence !== null ? (
                  <span dir="ltr">
                    {gate.evidence.reference} · {gate.evidence.staleness}
                  </span>
                ) : (
                  'بدون شواهد'
                )}
              </dd>
            </div>
            <div className="flex items-baseline justify-between gap-2">
              <dt className="text-ink-muted">آخرین ارزیابی</dt>
              <dd className={cn('tabular-nums', gate.lastEvaluatedUtc === null ? 'text-ink-muted' : 'text-ink')}>
                {gate.lastEvaluatedUtc !== null ? (
                  <>
                    <time dateTime={gate.lastEvaluatedUtc}>
                      {formatTimeUtc(gate.lastEvaluatedUtc)}
                    </time>{' '}
                    UTC
                  </>
                ) : (
                  'بدون زمان ارزیابی'
                )}
              </dd>
            </div>
          </dl>
        </div>
      </div>
    </dialog>
  );
}
