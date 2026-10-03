import { Lock, OctagonAlert, ShieldAlert } from 'lucide-react';

import { ToneBadge } from '@/components/ui/tone-badge';
import type { EmergencyAction } from '@/types/dashboard';

/**
 * Emergency action cards — preview only.
 *
 * Every action is disabled with an explicit Persian reason, because the signed
 * webhook path is not connected and the UI may not activate anything (D-171 §6,
 * D-139). A control that looks live but does nothing is the anti-pattern the
 * design rules call out, so the disabled state is stated rather than implied.
 */
export function EmergencyActionsCard({ actions }: { actions: EmergencyAction[] }) {
  return (
    <section className="flex flex-col gap-3" aria-label="کنش‌های اضطراری">
      <header className="flex flex-wrap items-center gap-2">
        <h2 className="text-cp-heading font-semibold text-ink">کنش‌های اضطراری</h2>
        <ToneBadge
          tone="neutral"
          label="فقط پیش‌نمایش"
          code="PREVIEW_ONLY"
          Icon={Lock}
        />
      </header>

      <ul className="flex flex-col gap-3">
        {actions.map((action) => (
          <li
            key={action.id}
            className="flex flex-col gap-2 rounded-[--radius-cp] border border-danger bg-surface p-3"
          >
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-danger">
                <OctagonAlert aria-hidden="true" className="size-5" />
              </span>
              <h3 className="text-cp-label font-semibold text-ink">{action.title}</h3>
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
            <p className="text-cp-caption text-ink-muted">
              <strong className="text-ink">اثر:</strong> {action.effect}
            </p>

            <button
              type="button"
              disabled
              aria-disabled="true"
              title={action.blockedReason}
              className="cp-target inline-flex w-fit items-center gap-2 rounded-[--radius-cp] border border-danger bg-surface px-3 py-2 text-cp-label font-medium text-danger disabled:cursor-not-allowed disabled:opacity-60"
            >
              <OctagonAlert aria-hidden="true" className="size-4" />
              اجرا (غیرفعال)
            </button>
            <p className="text-cp-caption text-danger">{action.blockedReason}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
