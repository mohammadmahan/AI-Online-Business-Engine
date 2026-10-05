import { Lock, ShieldAlert, Unplug } from 'lucide-react';

import { ToneBadge } from '@/components/ui/tone-badge';
import type { InventoryActionSpec, InventoryGate } from '@/types/inventory';

/**
 * Manual sync / override gate (D-171 §5.3/§6).
 *
 * Every action is DISABLED and carries its own Persian reason. The UI neither
 * mints nor holds a single-use owner token (D-146) and does not own the
 * canonical/webhook write path, so an enabled control here would look live
 * while being unable to authorise anything — the anti-pattern D-171 §6 forbids.
 * The reasons are rendered as text, not only as `title`, so screen readers and
 * touch devices get them too.
 *
 * The two gate facts (token, write path) are stated explicitly, because "why is
 * this disabled" is the first question an operator asks.
 */
export function SyncOverrideGate({
  actions,
  gate,
}: {
  actions: InventoryActionSpec[];
  gate: InventoryGate;
}) {
  return (
    <section className="flex flex-col gap-3" aria-label="کنش‌های نوشتن موجودی">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-cp-heading font-semibold text-ink">کنش‌های نوشتن (گیت Fail-Closed)</h2>
        <ToneBadge
          tone={gate.tokenPresent ? 'warning' : 'neutral'}
          label={gate.tokenPresent ? 'توکن مالک موجود' : 'بدون توکن مالک'}
          code={gate.tokenPresent ? 'TOKEN_PRESENT' : 'NO_TOKEN'}
          Icon={gate.tokenPresent ? ShieldAlert : Lock}
        />
        <ToneBadge
          tone={gate.writePathConnected ? 'warning' : 'neutral'}
          label={gate.writePathConnected ? 'مسیر نوشتن متصل' : 'مسیر نوشتن قطع'}
          code={gate.writePathConnected ? 'WRITE_PATH_ON' : 'WRITE_PATH_OFF'}
          Icon={Unplug}
        />
      </header>

      <p className="text-cp-label text-ink-muted">
        در این فاز هیچ نوشتنی مجاز نیست: نه توکن یک‌بارمصرف مالک صادر شده و نه مسیر
        canonical/وب‌هوک امضاشده متصل است (D-146 / D-171 §6). دکمه‌ها عمداً غیرفعال‌اند و هر
        کدام دلیل خود را می‌گوید.
      </p>

      <ul className="grid gap-3 lg:grid-cols-3">
        {actions.map((action) => (
          <li
            key={action.id}
            className="flex flex-col gap-2 rounded-[--radius-cp] border border-edge bg-surface p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <h3 className="text-cp-label font-semibold text-ink">
                {action.title}{' '}
                <span className="font-mono text-cp-caption text-ink-muted">({action.id})</span>
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

            <p className="text-cp-caption text-ink-muted">{action.description}</p>

            <button
              type="button"
              disabled
              aria-disabled="true"
              className="cp-target inline-flex w-fit items-center gap-2 rounded-[--radius-cp] border border-edge-strong bg-surface px-3 py-2 text-cp-label font-medium text-ink-muted disabled:cursor-not-allowed disabled:opacity-60"
            >
              <Lock aria-hidden="true" className="size-4" />
              {action.title} (غیرفعال)
            </button>

            <p className="text-cp-caption text-ink-muted">{action.blockedReason}</p>
          </li>
        ))}
      </ul>

      <p className="rounded-[--radius-cp] border border-edge-strong bg-surface-muted p-2 text-cp-caption text-ink-muted">
        قیدهای مسیر نوشتن: هر تغییر فقط از سرویس canonical یا وب‌هوک امضاشده عبور می‌کند و
        هر کنش یک رکورد قابل ردیابی در لجر تولید می‌کند (D-121)؛ قفل قیمت و بازنویسی موجودی
        کنش‌های برگشت‌ناپذیرند و تأیید دوم می‌خواهند.
      </p>
    </section>
  );
}
