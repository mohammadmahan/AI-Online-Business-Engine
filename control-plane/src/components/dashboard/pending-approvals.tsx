import { AlertTriangle, ArrowUpRight, BellRing, Inbox } from 'lucide-react';
import Link from 'next/link';

import { ToneBadge, type Tone } from '@/components/ui/tone-badge';
import type { PendingApproval, Severity } from '@/types/dashboard';

const SEVERITY_META: Record<Severity, { label: string; code: string; tone: Tone; Icon: typeof AlertTriangle }> = {
  critical: { label: 'بحرانی', code: 'CRITICAL', tone: 'danger', Icon: AlertTriangle },
  high: { label: 'بالا', code: 'HIGH', tone: 'danger', Icon: AlertTriangle },
  medium: { label: 'متوسط', code: 'MEDIUM', tone: 'warning', Icon: BellRing },
  low: { label: 'پایین', code: 'LOW', tone: 'neutral', Icon: Inbox },
};

/**
 * Top pending human-review items with a direct link into `/hitl-queue`.
 *
 * The list is a PREVIEW: no action is offered here, because acting on a review
 * requires the real HITL engine and a single-use owner token (D-068 / D-146),
 * which this phase does not have. The card routes to the queue instead of
 * pretending to decide.
 */
export function PendingApprovalsCard({
  approvals,
  total,
}: {
  approvals: PendingApproval[];
  total: number;
}) {
  return (
    <section className="flex flex-col gap-3" aria-label="تأییدهای در انتظار">
      <header className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <h2 className="text-cp-heading font-semibold text-ink">تأییدهای در انتظار</h2>
          <ToneBadge
            tone={total > 0 ? 'warning' : 'neutral'}
            label="در صف"
            code="PENDING"
            detail={`${total}`}
          />
        </div>
        <Link
          href="/hitl-queue"
          className="cp-target inline-flex items-center gap-1 rounded-[--radius-cp] px-2 py-1 text-cp-label font-medium text-primary hover:underline"
        >
          صف کامل
          <ArrowUpRight aria-hidden="true" className="size-4" />
        </Link>
      </header>

      {approvals.length === 0 ? (
        <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
          موردی برای بازبینی وجود ندارد — و نبود داده هرگز «تأییدشده» معنا نمی‌شود.
        </p>
      ) : (
        <ul className="flex flex-col divide-y divide-edge">
          {approvals.map((item) => {
            const meta = SEVERITY_META[item.severity];
            return (
              <li key={item.id} className="flex flex-col gap-1 py-3 first:pt-0 last:pb-0">
                <div className="flex flex-wrap items-center gap-2">
                  <ToneBadge
                    tone={meta.tone}
                    label={meta.label}
                    code={meta.code}
                    Icon={meta.Icon}
                  />
                  <span className="font-mono text-cp-caption text-ink-muted">{item.id}</span>
                  <span className="text-cp-caption text-ink-muted">{item.category}</span>
                  <span className="text-cp-caption text-ink-muted">· {item.age}</span>
                </div>
                <p className="text-cp-label text-ink">{item.summary}</p>
                <p className="font-mono text-cp-caption text-ink-muted">{item.source}</p>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
