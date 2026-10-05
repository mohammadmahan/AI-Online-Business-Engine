import { Lock, ShieldAlert, Unplug } from 'lucide-react';

import { ToneBadge } from '@/components/ui/tone-badge';
import type { TelemetryActionSpec, TelemetryWriteGate } from '@/types/telemetry';

/**
 * Emergency gate override panel (D-171 §5.4/§6).
 *
 * Every action is DISABLED and carries its own Persian reason. Forcing a gate,
 * restarting a container or flushing a queue would bypass the owner gate; the
 * UI neither mints nor holds a single-use owner token (D-146) and has no signed
 * write path (D-171 §6), so an enabled control here would look live while being
 * unable to authorise anything — the anti-pattern the directive forbids.
 *
 * The two gate facts (token, signature path) are stated explicitly, and the
 * reasons are rendered as text, not only as a `title`, so screen readers and
 * touch devices receive them too.
 */
export function OverridePanel({
  actions,
  writeGate,
}: {
  actions: TelemetryActionSpec[];
  writeGate: TelemetryWriteGate;
}) {
  return (
    <section className="flex flex-col gap-3" aria-label="کنش‌های اضطراری گیت‌ها">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-cp-heading font-semibold text-ink">پنل اضطراری گیت (Fail-Closed)</h2>
        <ToneBadge
          tone={writeGate.tokenPresent ? 'warning' : 'neutral'}
          label={writeGate.tokenPresent ? 'توکن مالک موجود' : 'بدون توکن مالک'}
          code={writeGate.tokenPresent ? 'TOKEN_PRESENT' : 'NO_TOKEN'}
          Icon={writeGate.tokenPresent ? ShieldAlert : Lock}
        />
        <ToneBadge
          tone={writeGate.signaturePathConnected ? 'warning' : 'neutral'}
          label={
            writeGate.signaturePathConnected ? 'مسیر نوشتن امضاشده متصل' : 'مسیر نوشتن امضاشده قطع'
          }
          code={writeGate.signaturePathConnected ? 'SIGNATURE_PATH_ON' : 'SIGNATURE_PATH_OFF'}
          Icon={Unplug}
        />
      </header>

      <p className="text-cp-label text-ink-muted">
        در این فاز هیچ کنش اضطراری مجاز نیست: نه توکن یک‌بارمصرف مالک (D-146) صادر شده و نه مسیر
        نوشتن امضاشده متصل است (D-171 §6). دکمه‌ها عمداً غیرفعال‌اند و هر کدام دلیل خود را
        می‌گوید؛ بازکردن گیت بدون شواهد یا دور زدن آن هرگز از این پنل انجام نمی‌شود.
      </p>

      <ul className="grid gap-3 lg:grid-cols-3">
        {actions.map((action) => (
          <li
            key={action.id}
            className="flex flex-col gap-2 rounded-[--radius-cp] border border-edge bg-surface p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-cp-label font-semibold text-ink">
                {action.titleFa}{' '}
                <span className="font-mono text-cp-caption text-ink-muted">
                  (<span dir="ltr">{action.id}</span>)
                </span>
              </h3>
              {action.requiresSecondConfirmation ? (
                <ToneBadge
                  tone="neutral"
                  label="نیازمند تأیید دوم"
                  code="CONFIRM_2X"
                  Icon={ShieldAlert}
                />
              ) : null}
            </div>

            <p className="text-cp-caption text-ink-muted">{action.descriptionFa}</p>

            <button
              type="button"
              disabled
              aria-disabled="true"
              className="cp-target inline-flex w-fit items-center gap-2 rounded-[--radius-cp] border border-edge-strong bg-surface px-3 py-2 text-cp-label font-medium text-ink-muted disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Lock aria-hidden="true" className="size-4" />
              {action.titleFa} (غیرفعال)
            </button>

            <p className="text-cp-caption text-ink-muted">{action.blockedReasonFa}</p>
          </li>
        ))}
      </ul>

      <p className="rounded-[--radius-cp] border border-edge-strong bg-surface-muted p-2 text-cp-caption text-ink-muted">
        قیدهای مسیر اضطراری: هر کنش در حالت واقعی فقط با حکم یک‌بارمصرف مالک و از مسیر امضاشده
        اجرا می‌شود، درخواست تکراری رد می‌شود (D-146/D-147)، و هر تلاش یک رکورد قابل ردیابی در
        لجر تولید می‌کند (D-121).
      </p>
    </section>
  );
}
