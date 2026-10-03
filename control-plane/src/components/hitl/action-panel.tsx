import { Lock, ShieldAlert } from 'lucide-react';

import { ToneBadge } from '@/components/ui/tone-badge';
import { DECISION_META } from '@/components/hitl/status-meta';
import type { HitlActionSpec, HitlTicket } from '@/types/hitl';

/**
 * One-click decisions: approve / modify / reject / escalate (D-171 §5.2).
 *
 * Every action is DISABLED, and each carries its own Persian reason. The UI
 * neither mints nor holds a single-use owner token and has no signing key
 * (D-146 / D-168), so an enabled control here would look live while being
 * unable to authorise anything — the anti-pattern D-171 §6 forbids. The reason
 * is rendered as text, not only as a `title`, so it is available to screen
 * readers and on touch devices.
 *
 * The token state is stated explicitly (`tokenPresent`), because "why is this
 * disabled" is the first question an operator asks.
 */
export function ActionPanel({
  actions,
  tokenPresent,
  selected,
}: {
  actions: HitlActionSpec[];
  tokenPresent: boolean;
  selected: HitlTicket | null;
}) {
  return (
    <section className="flex flex-col gap-3" aria-label="کنش‌های تصمیم">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-cp-heading font-semibold text-ink">کنش‌ها</h2>
        <ToneBadge
          tone={tokenPresent ? 'warning' : 'neutral'}
          label={tokenPresent ? 'توکن موجود' : 'بدون توکن'}
          code={tokenPresent ? 'TOKEN_PRESENT' : 'NO_TOKEN'}
          Icon={tokenPresent ? ShieldAlert : Lock}
        />
      </header>

      <p className="text-cp-label text-ink-muted">
        {selected ? (
          <>
            تیکت انتخاب‌شده:{' '}
            <span className="font-mono text-ink">{selected.ticket_id}</span>
          </>
        ) : (
          'برای دیدن جزئیات، تیکتی را از جدول انتخاب کنید. کنش‌ها تا آن زمان غیرفعال می‌مانند.'
        )}
      </p>

      <ul className="flex flex-col gap-3">
        {actions.map((action) => {
          const meta = DECISION_META[action.decision];
          const Icon = meta.Icon;
          const disabled = !action.enabled || selected === null;
          const reason = selected === null
            ? 'هیچ تیکتی انتخاب نشده است؛ ابتدا یک تیکت را از جدول باز کنید'
            : action.blockedReason;

          return (
            <li
              key={action.decision}
              className="flex flex-col gap-2 rounded-[--radius-cp] border border-edge bg-surface p-3"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-ink-muted">
                  <Icon aria-hidden="true" className="size-5" />
                </span>
                <h3 className="text-cp-label font-semibold text-ink">
                  {action.title}{' '}
                  <span className="font-mono text-cp-caption text-ink-muted">
                    ({meta.code})
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

              <p className="text-cp-caption text-ink-muted">{action.description}</p>

              <button
                type="button"
                disabled={disabled}
                aria-disabled="true"
                className="cp-target inline-flex w-fit items-center gap-2 rounded-[--radius-cp] border border-edge-strong bg-surface px-3 py-2 text-cp-label font-medium text-ink-muted disabled:cursor-not-allowed disabled:opacity-60"
              >
                <Lock aria-hidden="true" className="size-4" />
                {action.title} (غیرفعال)
              </button>

              <p className="text-cp-caption text-ink-muted">{reason}</p>
            </li>
          );
        })}
      </ul>

      <p className="rounded-[--radius-cp] border border-edge-strong bg-surface-muted p-2 text-cp-caption text-ink-muted">
        قیدهای موتور: بدون توکن، کنش غیرفعال است؛ در رقابت دو بازبین هم‌زمان
        تنها یکی برنده می‌شود (D-168)؛ هر کنش یک رکورد قابل ردیابی در لجر
        تولید می‌کند (D-121).
      </p>
    </section>
  );
}
