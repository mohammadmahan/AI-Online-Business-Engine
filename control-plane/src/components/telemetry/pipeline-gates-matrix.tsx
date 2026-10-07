'use client';

import { CheckCircle2, ScrollText } from 'lucide-react';
import { useState } from 'react';

import { GateAuditDrawer } from '@/components/telemetry/gate-audit-drawer';
import { GATE_STATUS_META } from '@/components/telemetry/status-meta';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatTimeUtc } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { PipelineGate } from '@/types/telemetry';

/**
 * The cutover verification matrix V-01..V-10 (D-145 + Stage F, D-146/D-147).
 *
 * The table is the FAIL-CLOSED surface of the control plane: a gate shows green
 * only when its status is PASS with fresh evidence, and the build-time guard
 * rejects any snapshot where a BLOCKED (or EVALUATING / BYPASS_PREVENTED) gate
 * claims to be passing. Non-PASS gates carry a Persian description and an audit
 * record; the record opens in a native-dialog drawer so keyboard users reach it
 * with no pointer.
 *
 * This component owns only PRESENTATION state (which audit row is open). It
 * never evaluates a gate, never marks one as passed and never writes anything —
 * it renders the verifier's verdict.
 */
export function PipelineGatesMatrix({ gates }: { gates: PipelineGate[] }) {
  const [selected, setSelected] = useState<PipelineGate | null>(null);

  return (
    <section className="flex flex-col gap-3" aria-label="ماتریس گیت‌های انتقال">
      <header className="flex flex-col gap-1">
        <h2 className="text-cp-heading font-semibold text-ink">ماتریس گیت‌های انتقال (V-01..V-10)</h2>
        <p className="text-cp-label text-ink-muted">
          گیت‌های V-01 تا V-09 ماتریس راستی‌آزمایی انتقال (D-145) و V-10 مجوز یک‌بارمصرف مالک
          (D-146/D-147) است. تنها وضعیت «گذر» با شاهد تازه سبز می‌شود؛ FAIL به «مسدود» و
          «قابل‌ارزیابی‌نبودن» (کد خروج ۲) به «در حال ارزیابی» نگاشت می‌شود.
        </p>
      </header>

      <div className="overflow-x-auto rounded-[--radius-cp] border border-edge">
        <table className="w-full border-collapse text-cp-label">
          <caption className="sr-only">
            وضعیت گیت‌های V-01 تا V-10 همراه با شواهد و رکورد حسابرسی
          </caption>
          <thead>
            <tr className="bg-surface-muted text-cp-caption text-ink-muted">
              <th scope="col" className="p-2 text-start font-medium">
                گیت
              </th>
              <th scope="col" className="p-2 text-start font-medium">
                عنوان و شرط
              </th>
              <th scope="col" className="p-2 text-start font-medium">
                وضعیت
              </th>
              <th scope="col" className="p-2 text-start font-medium">
                شواهد
              </th>
              <th scope="col" className="p-2 text-start font-medium">
                آخرین ارزیابی
              </th>
              <th scope="col" className="p-2 text-start font-medium">
                رکورد
              </th>
            </tr>
          </thead>
          <tbody>
            {gates.map((gate) => {
              const meta = GATE_STATUS_META[gate.status];
              const auditLabel = meta.auditLabel;
              return (
                <tr key={gate.id} className="border-t border-edge align-top">
                  <th scope="row" className="p-2 text-start font-mono text-cp-label text-ink">
                    <span dir="ltr">{gate.id}</span>
                  </th>
                  <td className="p-2">
                    <p className="text-ink">
                      {gate.titleFa}{' '}
                      {gate.passes ? (
                        <span className="whitespace-nowrap text-cp-caption font-medium text-success">
                          <CheckCircle2 aria-hidden="true" className="me-1 inline size-4 align-[-2px]" />
                          شاهد تأییدشده
                        </span>
                      ) : null}
                    </p>
                    <p className="mt-1 max-w-prose text-cp-caption text-ink-muted">
                      {gate.descriptionFa}
                    </p>
                  </td>
                  <td className="whitespace-nowrap p-2">
                    <ToneBadge tone={meta.tone} label={meta.label} code={meta.code} Icon={meta.Icon} />
                  </td>
                  <td className="p-2">
                    {gate.evidence !== null ? (
                      <span className="font-mono text-cp-caption text-ink">
                        <span dir="ltr">{gate.evidence.reference}</span>{' '}
                        <span
                          className={cn(
                            'font-sans',
                            gate.evidence.staleness === 'FRESH' ? 'text-success' : 'text-warning',
                          )}
                        >
                          ({gate.evidence.staleness})
                        </span>
                      </span>
                    ) : (
                      <span className="text-cp-caption text-ink-muted">
                        بدون شاهد — شاهد غایب هرگز سبز نیست (fail-closed)
                      </span>
                    )}
                  </td>
                  <td className="whitespace-nowrap p-2 text-cp-caption tabular-nums text-ink-muted">
                    {gate.lastEvaluatedUtc !== null ? (
                      <>
                        <time dateTime={gate.lastEvaluatedUtc}>
                          {formatTimeUtc(gate.lastEvaluatedUtc)}
                        </time>{' '}
                        UTC
                      </>
                    ) : (
                      '—'
                    )}
                  </td>
                  <td className="p-2">
                    {auditLabel !== null ? (
                      <button
                        type="button"
                        onClick={() => setSelected(gate)}
                        aria-haspopup="dialog"
                        className={cn(
                          'cp-target inline-flex items-center gap-1 rounded-[--radius-cp]',
                          'border border-edge-strong bg-surface px-2 py-1',
                          'text-cp-caption font-medium text-ink hover:bg-surface-muted',
                        )}
                      >
                        <ScrollText aria-hidden="true" className="size-4" />
                        {auditLabel}
                      </button>
                    ) : gate.status === 'PASS' ? (
                      <span className="text-cp-caption text-ink-muted">
                        بدون رکورد شکست
                      </span>
                    ) : (
                      <span className="text-cp-caption text-ink-muted">حکمی صادر نشده است</span>
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>

      <p className="text-cp-caption text-ink-muted">
        هر «رکورد مسدودسازی» فقط خواندنی است و دلیل مسدودماندن گیت را با شناسهٔ ردیابی D-121
        نشان می‌دهد؛ هیچ دکمه‌ای در این ماتریس وضعیت گیت را تغییر نمی‌دهد.
      </p>

      <GateAuditDrawer gate={selected} onClose={() => setSelected(null)} />
    </section>
  );
}
