'use client';

import {
  Activity,
  AlertTriangle,
  ArrowLeftRight,
  CheckCircle2,
  FlaskConical,
  HelpCircle,
  PlugZap,
  XCircle,
  type LucideIcon,
} from 'lucide-react';

import { ToneBadge } from '@/components/ui/tone-badge';
import { Tooltip } from '@/components/ui/tooltip';
import type { BusinessCardModel, BusinessTone } from '@/lib/business-summary';
import { useViewMode } from '@/lib/context/view-mode-context';
import { cn } from '@/lib/utils';

/**
 * D-171 §2.3 الف / §10 — Phase 27.12 aggregated Business card.
 *
 * The plain-Persian, jargon-free summary a shop owner reads at the top of a
 * page. It renders an already-computed model (see `lib/business-summary.ts`)
 * and owns exactly two behaviours:
 *
 *   1. every metric carries a keyboard-focusable explanation (the 27.11
 *      `Tooltip`: hover + `aria-describedby`, no client state);
 *   2. the drill-down action switches the ACTIVE VIEW to the technical console
 *      on the same page — `setMode()` writes one attribute, so the URL, the
 *      scroll position and the page itself are untouched (no reload, no
 *      navigation, no refetch).
 *
 * Visibility is gated by CSS on the pre-paint `data-view-mode` attribute, the
 * exact mechanism the 27.10 sidebar uses and the owner approved: a Business
 * card exists in the Business view only, and the technical console never shows
 * it — not even for a frame before hydration. Because the card leaves the DOM
 * flow when the console opens (its whole purpose), the drill-down moves focus
 * to the main region instead of letting focus fall to `<body>`, and it does so
 * with `preventScroll` so the reader's place is kept.
 *
 * Colours are gate-enforced token pairs only (`bg-surface`, `text-ink`,
 * `text-ink-muted`, `border-edge`, `border-edge-strong` + the filled chip
 * pairs inside `ToneBadge`); every state carries an icon, a Persian label and
 * an English code, so meaning never depends on colour (§3.5).
 */

const STATUS_ICON: Record<BusinessTone, LucideIcon> = {
  neutral: HelpCircle,
  success: CheckCircle2,
  warning: AlertTriangle,
  danger: XCircle,
};

const PROVENANCE_ICON: Record<BusinessTone, LucideIcon> = {
  neutral: HelpCircle,
  success: Activity,
  warning: FlaskConical,
  danger: PlugZap,
};

export function BusinessStatusCard({ model }: { model: BusinessCardModel }) {
  const { setMode } = useViewMode();
  const titleId = `bc-${model.id}-title`;
  const drillId = `bc-${model.id}-drill`;

  function openTechnicalConsole() {
    setMode('technical');
    // The card is Business-only by design, so the control that was just used
    // is no longer rendered: hand focus to the content region rather than
    // dropping it to <body>. `preventScroll` keeps the reader's position.
    document.getElementById('main-content')?.focus({ preventScroll: true });
  }

  return (
    <section
      aria-labelledby={titleId}
      data-business-card={model.id}
      className={cn(
        'flex flex-col gap-3 rounded-[--radius-cp] border border-edge bg-surface p-4',
        // Business view only — decided before first paint, exactly like the
        // 27.10 sidebar gate (mirrored, never reimplemented in JS).
        '[[data-view-mode=technical]_&]:hidden',
      )}
    >
      <header className="flex flex-wrap items-center justify-between gap-2">
        <h2 id={titleId} className="text-cp-heading font-semibold text-ink">
          {model.title}
        </h2>
        <div className="flex flex-wrap items-center gap-2">
          <ToneBadge
            tone={model.status.tone}
            label={model.status.label}
            code={model.status.code}
            Icon={STATUS_ICON[model.status.tone]}
          />
          {model.provenance.code === model.status.code ? null : (
            <ToneBadge
              tone={model.provenance.tone}
              label={model.provenance.label}
              code={model.provenance.code}
              Icon={PROVENANCE_ICON[model.provenance.tone]}
            />
          )}
        </div>
      </header>

      <p className="text-cp-body text-ink">{model.headline}</p>

      <ul className="grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
        {model.metrics.map((metric, index) => {
          const id = `bc-${model.id}-m${index}`;
          return (
            <li
              key={metric.label}
              className="flex flex-col gap-1 rounded-[--radius-cp] border border-edge bg-surface-muted p-3"
            >
              <div className="flex items-start justify-between gap-2">
                <p className="text-cp-caption text-ink-muted">{metric.label}</p>
                <Tooltip id={id} text={metric.tip}>
                  <button
                    type="button"
                    aria-label={`راهنمای «${metric.label}»`}
                    aria-describedby={id}
                    className="cp-target shrink-0 text-ink-muted hover:text-ink"
                  >
                    <HelpCircle aria-hidden="true" className="size-4" />
                  </button>
                </Tooltip>
              </div>
              <p className="text-cp-heading font-bold tabular-nums text-ink">
                {metric.value}
              </p>
            </li>
          );
        })}
      </ul>

      <div>
        <Tooltip id={drillId} text={model.drillDown.tip}>
          <button
            type="button"
            aria-describedby={drillId}
            onClick={openTechnicalConsole}
            className={cn(
              'cp-target inline-flex items-center gap-2 rounded-[--radius-cp]',
              'bg-primary px-3 py-2 text-cp-label font-medium text-surface transition-colors',
            )}
          >
            <ArrowLeftRight aria-hidden="true" className="size-4 shrink-0" />
            {model.drillDown.label}
          </button>
        </Tooltip>
      </div>
    </section>
  );
}
