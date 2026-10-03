import {
  AlertTriangle,
  ArrowUpCircle,
  Ban,
  CheckCircle2,
  Clock,
  CornerUpRight,
  Inbox,
  PencilLine,
  ShieldAlert,
  TimerOff,
  UserCheck,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type { Tone } from '@/components/ui/tone-badge';
import type {
  HitlSeverity,
  RequiredRole,
  ResolutionStatus,
  ReviewDecision,
} from '@/types/hitl';

/**
 * Presentation vocabulary for the HITL queue.
 *
 * Every entry pairs an ICON with a PERSIAN LABEL and an ENGLISH CODE, so no
 * meaning depends on colour alone (`color-not-only`, D-171 §3.2). The codes are
 * the canonical engine values from `local/canonical/hitl_contracts.py` — the UI
 * never renames them.
 */

export interface StatusMeta {
  label: string;
  code: string;
  tone: Tone;
  Icon: LucideIcon;
  /** Foreground token used when the state is shown as bare text/icon. */
  ink: string;
}

export const SEVERITY_META: Record<HitlSeverity, StatusMeta> = {
  critical: {
    label: 'بحرانی',
    code: 'CRITICAL',
    tone: 'danger',
    Icon: ShieldAlert,
    ink: 'text-danger',
  },
  high: {
    label: 'بالا',
    code: 'HIGH',
    tone: 'danger',
    Icon: AlertTriangle,
    ink: 'text-danger',
  },
  medium: {
    label: 'متوسط',
    code: 'MEDIUM',
    tone: 'warning',
    Icon: Clock,
    ink: 'text-warning',
  },
  low: {
    label: 'پایین',
    code: 'LOW',
    tone: 'neutral',
    Icon: Inbox,
    ink: 'text-ink-muted',
  },
};

/**
 * Lifecycle presentation (D-105).
 *
 * `PENDING_REVIEW` and `CLAIMED` are deliberately NOT success-toned: a queue
 * item awaiting a human is work outstanding, never a green outcome. Only the
 * decided states carry a success/neutral tone, and `EXPIRED` is stated as a
 * neutral event because no reviewer acted.
 */
export const STATUS_META: Record<ResolutionStatus, StatusMeta> = {
  PENDING_REVIEW: {
    label: 'در انتظار بازبینی',
    code: 'PENDING_REVIEW',
    tone: 'warning',
    Icon: Clock,
    ink: 'text-warning',
  },
  CLAIMED: {
    label: 'قفل‌شده',
    code: 'CLAIMED',
    tone: 'warning',
    Icon: UserCheck,
    ink: 'text-warning',
  },
  APPROVED: {
    label: 'تأییدشده',
    code: 'APPROVED',
    tone: 'success',
    Icon: CheckCircle2,
    ink: 'text-success',
  },
  REJECTED: {
    label: 'ردشده',
    code: 'REJECTED',
    tone: 'neutral',
    Icon: Ban,
    ink: 'text-ink-muted',
  },
  MODIFIED: {
    label: 'اصلاح‌شده',
    code: 'MODIFIED',
    tone: 'success',
    Icon: PencilLine,
    ink: 'text-success',
  },
  ESCALATED: {
    label: 'ارجاع‌شده',
    code: 'ESCALATED',
    tone: 'danger',
    Icon: CornerUpRight,
    ink: 'text-danger',
  },
  EXPIRED: {
    label: 'منقضی',
    code: 'EXPIRED',
    tone: 'neutral',
    Icon: TimerOff,
    ink: 'text-ink-muted',
  },
};

/** Action decision presentation (D-171 §5.2). */
export const DECISION_META: Record<
  ReviewDecision,
  { label: string; code: string; Icon: LucideIcon }
> = {
  APPROVED: { label: 'تأیید', code: 'APPROVED', Icon: CheckCircle2 },
  MODIFIED: { label: 'اصلاح', code: 'MODIFIED', Icon: PencilLine },
  REJECTED: { label: 'رد', code: 'REJECTED', Icon: Ban },
  ESCALATED: { label: 'ارجاع', code: 'ESCALATED', Icon: ArrowUpCircle },
};

/** Required-role presentation, with the engine's own role names. */
export const ROLE_LABEL: Record<RequiredRole, { label: string; code: string }> = {
  any: { label: 'هر بازبین', code: 'any' },
  owner: { label: 'مالک', code: 'owner' },
  publisher: { label: 'ناشر', code: 'publisher' },
  ops: { label: 'عملیات', code: 'ops' },
  escalation: { label: 'ارجاع', code: 'escalation' },
};

/** Queue-type presentation (D-105), with the engine's own codes. */
export const QUEUE_TYPE_LABEL: Record<string, { label: string }> = {
  INSIGHT_REVIEW: { label: 'بازبینی بینش' },
  PUBLISH_GATE: { label: 'گیت انتشار' },
  ORDER_OVERRIDE: { label: 'بازنویسی سفارش' },
  ASSET_FLAG: { label: 'نشان‌گذاری دارایی' },
};
