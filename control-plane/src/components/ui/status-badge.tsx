import { AlertTriangle, CheckCircle2, HelpCircle, XCircle } from 'lucide-react';

import { ToneBadge, type Tone } from '@/components/ui/tone-badge';
import { cn } from '@/lib/utils';

/**
 * Status states. `unknown` is a first-class state: absent evidence is never
 * rendered as success (D-171 §2.2, fail-closed).
 */
export type StatusState = 'pass' | 'fail' | 'warn' | 'unknown';

interface StatusMeta {
  /** Persian label — the primary carrier of meaning. */
  label: string;
  /** English code, kept for traceability. */
  code: string;
  /** Icon — meaning must never depend on colour alone (color-not-only). */
  Icon: typeof CheckCircle2;
  /** Filled-chip tone, resolved through the contrast-enforced token pairs. */
  tone: Tone;
  /** Token-backed text colour for icon-only / outline usage. */
  ink: string;
}

const STATUS: Record<StatusState, StatusMeta> = {
  pass: {
    label: 'تأییدشده',
    code: 'PASS',
    Icon: CheckCircle2,
    tone: 'success',
    ink: 'text-success',
  },
  fail: {
    label: 'شکست',
    code: 'FAIL',
    Icon: XCircle,
    tone: 'danger',
    ink: 'text-danger',
  },
  warn: {
    label: 'هشدار',
    code: 'WARN',
    Icon: AlertTriangle,
    tone: 'warning',
    ink: 'text-warning',
  },
  unknown: {
    label: 'نامشخص',
    code: 'UNKNOWN',
    Icon: HelpCircle,
    tone: 'neutral',
    ink: 'text-ink-muted',
  },
};

export function StatusBadge({
  state,
  detail,
}: {
  state: StatusState;
  detail?: string;
}) {
  const meta = STATUS[state];
  return (
    <ToneBadge
      tone={meta.tone}
      label={meta.label}
      code={meta.code}
      Icon={meta.Icon}
      detail={detail}
    />
  );
}

/** Icon-only variant; always carries an accessible name (aria-labels). */
export function StatusDot({ state, srLabel }: { state: StatusState; srLabel: string }) {
  const meta = STATUS[state];
  return (
    <span className={cn('inline-flex items-center gap-2', meta.ink)}>
      <meta.Icon aria-hidden="true" className="size-4" />
      <span className="sr-only">{srLabel}</span>
    </span>
  );
}
