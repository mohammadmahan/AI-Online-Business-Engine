import { Lock, ShieldAlert, Unplug } from 'lucide-react';

import { ToneBadge } from '@/components/ui/tone-badge';
import type { CommerceActionSpec, CommerceWriteGate } from '@/types/commerce';

/**
 * Manual fulfillment / payment gate (D-171 §5.6/§6).
 *
 * Every action is DISABLED and carries its own Persian reason. The UI neither
 * mints nor holds a single-use owner token (D-146), and no payment provider
 * (open decision 10) or shipping provider (open decision 11) is selected, so an
 * enabled control here would look live while being unable to authorise
 * anything — the anti-pattern D-171 §6 forbids.
 *
 * The reasons are rendered as text, not only as `title`, so screen readers and
 * touch devices receive them too. The two gate facts (owner token, selected
 * provider) are stated explicitly, because "why is this disabled" is the first
 * question an operator asks.
 */
export function FulfillmentOverrideGate({
  actions,
  gate,
}: {
  actions: CommerceActionSpec[];
  gate: CommerceWriteGate;
}) {
  return (
    <section className="flex flex-col gap-3" aria-label="کنش‌های تأمین و پرداخت">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-cp-heading font-semibold text-ink">
          کنش‌های تأمین و صدور (گیت Fail-Closed)
        </h2>
        <ToneBadge
          tone={gate.tokenPresent ? 'warning' : 'neutral'}
          label={gate.tokenPresent ? 'توکن مالک موجود' : 'بدون توکن مالک'}
          code={gate.tokenPresent ? 'TOKEN_PRESENT' : 'NO_TOKEN'}
          Icon={gate.tokenPresent ? ShieldAlert : Lock}
        />
        <ToneBadge
          tone={gate.providerSelected ? 'warning' : 'neutral'}
          label={gate.providerSelected ? 'ارائه‌دهنده انتخاب‌شده' : 'ارائه‌دهنده انتخاب‌نشده'}
          code={gate.providerSelected ? 'PROVIDER_SELECTED' : 'PROVIDER_UNSELECTED'}
          Icon={Unplug}
        />
      </header>

      <p className="text-cp-label text-ink-muted">
        پرداخت و ارسال در حالت تمرینی (DRY-RUN) است: نه درگاه پرداخت انتخاب شده (تصمیم باز ۱۰) و
        نه ارائه‌دهنده‌ی ارسال (تصمیم باز ۱۱). هیچ توکن یک‌بارمصرف مالک (D-146) صادر نشده و مسیر
        نوشتن امضاشده (D-171 §6) متصل نیست؛ بنابراین دکمه‌ها عمداً غیرفعال‌اند و هر کدام دلیل خود را
        می‌گوید.
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
        قیدهای مسیر نوشتن: هر کنش واقعی فقط با حکم یک‌بارمصرف مالک و از مسیر امضاشده اجرا می‌شود
        (D-146/D-147) و هر تلاش یک رکورد قابل ردیابی در لجر تولید می‌کند (D-121). تا انتخاب
        ارائه‌دهنده‌ی پرداخت و ارسال، هیچ مسیر پرداخت یا ارسال واقعی در این نما وجود ندارد.
      </p>
    </section>
  );
}
