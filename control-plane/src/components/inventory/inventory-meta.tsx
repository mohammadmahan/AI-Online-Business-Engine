import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  GitCompareArrows,
  Lock,
  PackageX,
  Snowflake,
  Unlock,
  XCircle,
} from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

import type { Tone } from '@/components/ui/tone-badge';
import type {
  LockState,
  ReviewState,
  SourceType,
  StockCategory,
  SyncHistoryEntry,
  SyncStatus,
} from '@/types/inventory';

/**
 * Presentation vocabulary for the inventory screen.
 *
 * Every entry pairs an ICON with a PERSIAN LABEL and an ENGLISH CODE, so no
 * meaning depends on colour alone (`color-not-only`, D-171 §3.2). The codes are
 * the control plane's canonical sync codes (see `types/inventory.ts`) and the
 * engine's own D-026 provenance values — the UI never renames them.
 */

export interface InventoryMeta {
  label: string;
  code: string;
  tone: Tone;
  Icon: LucideIcon;
  /** Foreground token used when the state is shown as bare text/icon. */
  ink: string;
}

/**
 * WooCommerce link state.
 *
 * Only `IN_SYNC` is toned green: a pending or failed sync is outstanding work,
 * and drift is an explicit conflict that stays visible until a human resolves
 * it (fail-closed — a conflict is never quietly toned neutral).
 */
export const SYNC_STATUS_META: Record<SyncStatus, InventoryMeta> = {
  IN_SYNC: {
    label: 'همگام',
    code: 'IN_SYNC',
    tone: 'success',
    Icon: CheckCircle2,
    ink: 'text-success',
  },
  PENDING_SYNC: {
    label: 'در انتظار همگام‌سازی',
    code: 'PENDING_SYNC',
    tone: 'warning',
    Icon: Clock,
    ink: 'text-warning',
  },
  SYNC_ERROR: {
    label: 'خطای همگام‌سازی',
    code: 'SYNC_ERROR',
    tone: 'danger',
    Icon: XCircle,
    ink: 'text-danger',
  },
  DRIFT_DETECTED: {
    label: 'واگرایی',
    code: 'DRIFT_DETECTED',
    tone: 'danger',
    Icon: GitCompareArrows,
    ink: 'text-danger',
  },
};

/** Stock state, derived from quantity against the safe threshold (D-082). */
export const STOCK_CATEGORY_META: Record<StockCategory, InventoryMeta> = {
  IN_STOCK: {
    label: 'موجود',
    code: 'IN_STOCK',
    tone: 'success',
    Icon: CheckCircle2,
    ink: 'text-success',
  },
  LOW_STOCK: {
    label: 'موجودی کم',
    code: 'LOW_STOCK',
    tone: 'warning',
    Icon: AlertTriangle,
    ink: 'text-warning',
  },
  OUT_OF_STOCK: {
    label: 'ناموجود',
    code: 'OUT_OF_STOCK',
    tone: 'danger',
    Icon: PackageX,
    ink: 'text-danger',
  },
};

/** Manual lock state; both lock kinds are human acts and carry a reason. */
export const LOCK_STATE_META: Record<LockState, InventoryMeta> = {
  NONE: {
    label: 'آزاد',
    code: 'NONE',
    tone: 'neutral',
    Icon: Unlock,
    ink: 'text-ink-muted',
  },
  PRICE_FREEZE: {
    label: 'قفل قیمت',
    code: 'PRICE_FREEZE',
    tone: 'warning',
    Icon: Snowflake,
    ink: 'text-warning',
  },
  STOCK_OVERRIDE: {
    label: 'قفل موجودی',
    code: 'STOCK_OVERRIDE',
    tone: 'danger',
    Icon: Lock,
    ink: 'text-danger',
  },
};

/** D-026 source types, with the engine's own codes. */
export const SOURCE_TYPE_LABEL: Record<SourceType, { label: string; code: string }> = {
  HUMAN_ENTERED: { label: 'ورود انسانی', code: 'HUMAN_ENTERED' },
  SYSTEM_GENERATED: { label: 'تولید سیستمی', code: 'SYSTEM_GENERATED' },
  AI_GENERATED: { label: 'تولید هوش مصنوعی', code: 'AI_GENERATED' },
  IMPORTED: { label: 'ورود از فایل', code: 'IMPORTED' },
  EXTERNAL_SYNC: { label: 'همگام‌سازی بیرونی', code: 'EXTERNAL_SYNC' },
};

/** D-026 review states. */
export const REVIEW_STATE_LABEL: Record<ReviewState, { label: string; code: string }> = {
  PENDING: { label: 'در انتظار بازبینی', code: 'PENDING' },
  HUMAN_REVIEWED: { label: 'بازبینی‌شده', code: 'HUMAN_REVIEWED' },
  HUMAN_VERIFIED: { label: 'تأیید انسانی', code: 'HUMAN_VERIFIED' },
};

/** Sync-history direction. */
export const SYNC_DIRECTION_LABEL: Record<
  SyncHistoryEntry['direction'],
  { label: string; code: string }
> = {
  PUSH: { label: 'ارسال', code: 'PUSH' },
  PULL: { label: 'دریافت', code: 'PULL' },
  RECONCILE: { label: 'تطبیق', code: 'RECONCILE' },
};

/** Sync-history outcome. */
export const SYNC_OUTCOME_META: Record<SyncHistoryEntry['outcome'], InventoryMeta> = {
  OK: {
    label: 'موفق',
    code: 'OK',
    tone: 'success',
    Icon: CheckCircle2,
    ink: 'text-success',
  },
  FAILED: {
    label: 'ناموفق',
    code: 'FAILED',
    tone: 'danger',
    Icon: XCircle,
    ink: 'text-danger',
  },
  DRIFT: {
    label: 'واگرایی',
    code: 'DRIFT',
    tone: 'danger',
    Icon: GitCompareArrows,
    ink: 'text-danger',
  },
};
