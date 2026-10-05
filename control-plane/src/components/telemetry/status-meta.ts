import {
  AlertTriangle,
  Ban,
  CheckCircle2,
  HelpCircle,
  Hourglass,
  ShieldAlert,
  XCircle,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type { Tone } from '@/components/ui/tone-badge';
import type { ContainerStatus, GateStatus, QueuePressure } from '@/types/telemetry';

/**
 * Status vocabulary → presentation, shared by every telemetry component.
 *
 * Each state pairs an icon, a Persian label and the English code, so meaning
 * never depends on colour alone (`color-not-only`). The mapping is DERIVED from
 * the canonical taxonomy — a FAIL from the cutover verifier renders as BLOCKED,
 * "cannot assess" (exit 2) as EVALUATING, and V-10's refusal as
 * BYPASS_PREVENTED — and no state is green unless its canonical meaning is a
 * verified PASS with fresh evidence.
 */
export interface StatusMeta {
  label: string;
  code: string;
  tone: Tone;
  Icon: LucideIcon;
  ink: string;
}

export const CONTAINER_STATUS_META: Record<ContainerStatus, StatusMeta> = {
  HEALTHY: {
    label: 'سالم',
    code: 'HEALTHY',
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
  DOWN: {
    label: 'از کار افتاده',
    code: 'DOWN',
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

export const GATE_STATUS_META: Record<GateStatus, StatusMeta & { auditLabel: string | null }> = {
  PASS: {
    label: 'گذر',
    code: 'PASS',
    tone: 'success',
    Icon: CheckCircle2,
    ink: 'text-success',
    auditLabel: null,
  },
  BLOCKED: {
    label: 'مسدود',
    code: 'BLOCKED',
    tone: 'danger',
    Icon: Ban,
    ink: 'text-danger',
    auditLabel: 'رکورد مسدودسازی',
  },
  EVALUATING: {
    label: 'در حال ارزیابی',
    code: 'EVALUATING',
    tone: 'warning',
    Icon: Hourglass,
    ink: 'text-warning',
    auditLabel: null,
  },
  BYPASS_PREVENTED: {
    label: 'عبور رد شد',
    code: 'BYPASS_PREVENTED',
    tone: 'warning',
    Icon: ShieldAlert,
    ink: 'text-warning',
    auditLabel: 'رکورد جلوگیری از عبور',
  },
};

export const QUEUE_PRESSURE_META: Record<QueuePressure, StatusMeta> = {
  OK: { label: 'عادی', code: 'OK', tone: 'success', Icon: CheckCircle2, ink: 'text-success' },
  WARN: {
    label: 'هشدار',
    code: 'WARN',
    tone: 'warning',
    Icon: AlertTriangle,
    ink: 'text-warning',
  },
  CRITICAL: {
    label: 'بحرانی',
    code: 'CRITICAL',
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
