import { Ban, ShieldOff } from 'lucide-react';

import type { AiOpsControlSpec, AiOpsProviderGate } from '@/types/ai-ops';
import { cn } from '@/lib/utils';

/**
 * Gated controls (D-171 §5.5 constraints / §6).
 *
 * Every control is rendered DISABLED with its own stated reason, exactly like
 * the telemetry override panel: running a route would call a provider, querying
 * the memory layer needs the external connection D-045 gates, and connecting
 * that layer is the owner decision itself. The interface therefore owns no
 * provider call path and holds no credential, and the fail-closed guard refuses
 * an enabled control unless BOTH preconditions are present.
 */
export function AiOpsControls({
  controls,
  providerGate,
}: {
  controls: AiOpsControlSpec[];
  providerGate: AiOpsProviderGate;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div
        className="flex flex-wrap items-center gap-2 rounded-[--radius-cp] border border-warning bg-surface p-3"
        role="note"
      >
        <Ban aria-hidden="true" className="size-4 shrink-0 text-warning" />
        <p className="text-cp-label text-ink">
          هیچ کنشی از این صفحه اجرا نمی‌شود: نه فراخوانی ارائه‌دهنده، نه پرس‌وجوی حافظه، نه برقراری
          اتصال. وضعیت‌ها فقط نمایش داده می‌شوند (D-171 §5.5).
        </p>
      </div>

      <dl className="grid gap-2 sm:grid-cols-2">
        <div className="flex items-baseline justify-between gap-2 rounded-[--radius-cp] border border-edge bg-surface-muted p-2 text-cp-caption">
          <dt className="text-ink-muted">مسیر فراخوانی ارائه‌دهنده</dt>
          <dd className="font-mono text-ink" dir="ltr">
            {providerGate.providerCallPathConnected ? 'CONNECTED' : 'ABSENT'}
          </dd>
        </div>
        <div className="flex items-baseline justify-between gap-2 rounded-[--radius-cp] border border-edge bg-surface-muted p-2 text-cp-caption">
          <dt className="text-ink-muted">اعتبارنامهٔ نگهداری‌شده در رابط</dt>
          <dd className="font-mono text-ink" dir="ltr">
            {providerGate.credentialPresent ? 'PRESENT' : 'NONE'}
          </dd>
        </div>
      </dl>

      <ul className="flex flex-col gap-2">
        {controls.map((control) => (
          <li
            key={control.id}
            className={cn(
              'flex flex-col gap-1 rounded-[--radius-cp] border border-edge bg-surface p-3',
              control.enabled ? 'border-success' : 'border-edge',
            )}
          >
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-cp-label font-semibold text-ink">{control.titleFa}</h3>
              <span className="inline-flex items-center gap-1 text-cp-caption text-ink-muted">
                <ShieldOff aria-hidden="true" className="size-3.5 shrink-0" />
                <span className="font-mono" dir="ltr">
                  {control.id}
                </span>
              </span>
            </div>
            <p className="text-cp-caption text-ink-muted">{control.descriptionFa}</p>
            <p className="text-cp-caption text-ink">
              <span className="font-medium">دلیل غیرفعال بودن:</span> {control.blockedReasonFa}
            </p>
            <button
              type="button"
              disabled
              aria-disabled="true"
              className={cn(
                'cp-target mt-1 inline-flex w-fit items-center gap-2 rounded-[--radius-cp]',
                'border border-edge-strong bg-surface-muted px-3 py-2 text-cp-label text-ink-muted',
                'cursor-not-allowed',
              )}
            >
              <ShieldOff aria-hidden="true" className="size-4 shrink-0" />
              {control.enabled ? 'اجرا' : 'غیرفعال'}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
