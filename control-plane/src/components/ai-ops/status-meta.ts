import {
  AlertTriangle,
  CheckCircle2,
  HelpCircle,
  Hourglass,
  PenLine,
  Unplug,
  XCircle,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type { Tone } from '@/components/ui/tone-badge';
import type {
  BudgetPressure,
  MemoryConnectionState,
  ProposalState,
} from '@/types/ai-ops';

/**
 * AI-ops status vocabulary → presentation (D-171 §3.5).
 *
 * Every state pairs an icon, a Persian label and the English code, so meaning
 * never depends on colour alone. The mapping is DERIVED from the canonical
 * vocabulary — the D-064 lifecycle states, the D-142 layer states and the
 * D-063 soft-ratio reading — and nothing is green unless its canonical meaning
 * is a verified connection or a consumption comfortably inside its allowance.
 */
export interface AiOpsStatusMeta {
  label: string;
  code: string;
  tone: Tone;
  Icon: LucideIcon;
  ink: string;
}

/** Shared-memory layer state (D-142). `NOT_CONNECTED` is a state, not an error. */
export const MEMORY_STATE_META: Record<MemoryConnectionState, AiOpsStatusMeta> = {
  NOT_CONNECTED: {
    label: 'وصل نشده',
    code: 'NOT_CONNECTED',
    tone: 'neutral',
    Icon: Unplug,
    ink: 'text-ink-muted',
  },
  CONNECTED: {
    label: 'متصل',
    code: 'CONNECTED',
    tone: 'success',
    Icon: CheckCircle2,
    ink: 'text-success',
  },
  DEGRADED: {
    label: 'تنزل‌یافته',
    code: 'DEGRADED',
    tone: 'warning',
    Icon: AlertTriangle,
    ink: 'text-warning',
  },
  UNKNOWN: {
    label: 'نامشخص',
    code: 'UNKNOWN',
    tone: 'neutral',
    Icon: HelpCircle,
    ink: 'text-ink-muted',
  },
};

/** Consumption pressure against an allowance (D-063 soft ratio + D-127 windows). */
export const BUDGET_PRESSURE_META: Record<BudgetPressure, AiOpsStatusMeta> = {
  OK: { label: 'عادی', code: 'OK', tone: 'success', Icon: CheckCircle2, ink: 'text-success' },
  WARNING: {
    label: 'نزدیک به سقف',
    code: 'WARNING',
    tone: 'warning',
    Icon: AlertTriangle,
    ink: 'text-warning',
  },
  EXCEEDED: {
    label: 'از سقف گذشته',
    code: 'EXCEEDED',
    tone: 'danger',
    Icon: XCircle,
    ink: 'text-danger',
  },
  UNKNOWN: {
    label: 'نامشخص',
    code: 'UNKNOWN',
    tone: 'neutral',
    Icon: HelpCircle,
    ink: 'text-ink-muted',
  },
};

/** Proposal lifecycle state (D-064). */
export const PROPOSAL_STATE_META: Record<ProposalState, AiOpsStatusMeta> = {
  PROPOSED: {
    label: 'پیشنهادشده',
    code: 'PROPOSED',
    tone: 'neutral',
    Icon: HelpCircle,
    ink: 'text-ink-muted',
  },
  IN_REVIEW: {
    label: 'در حال بررسی',
    code: 'IN_REVIEW',
    tone: 'warning',
    Icon: Hourglass,
    ink: 'text-warning',
  },
  ACCEPTED: {
    label: 'تأییدشده',
    code: 'ACCEPTED',
    tone: 'success',
    Icon: CheckCircle2,
    ink: 'text-success',
  },
  REJECTED: {
    label: 'ردشده',
    code: 'REJECTED',
    tone: 'danger',
    Icon: XCircle,
    ink: 'text-danger',
  },
  MODIFIED_BY_HUMAN: {
    label: 'اصلاح‌شده توسط انسان',
    code: 'MODIFIED_BY_HUMAN',
    tone: 'warning',
    Icon: PenLine,
    ink: 'text-warning',
  },
};
