import {
  Ban,
  CircleCheck,
  CircleDashed,
  CircleX,
  Gauge,
  Hourglass,
  Instagram,
  Landmark,
  PackageCheck,
  Send,
  ShieldAlert,
  Store,
  Truck,
  TriangleAlert,
  Undo2,
  type LucideIcon,
} from 'lucide-react';

import type { Tone } from '@/components/ui/tone-badge';
import type {
  Channel,
  FulfillmentStatus,
  LifecycleState,
  PaymentStatus,
  RiskLevel,
  SettlementState,
} from '@/types/commerce';

/**
 * Presentation metadata for the commerce vocabulary (D-171 §5.6).
 *
 * Every status carries a Persian label, its canonical English code AND an icon,
 * so meaning never depends on colour alone (`color-not-only`). The codes are
 * the canonical strings from `@/types/commerce`, never re-spelled here.
 */
export interface StatusMeta {
  tone: Tone;
  label: string;
  code: string;
  Icon: LucideIcon;
}

/** Sales channel tags (D-171 §5.6). */
export const CHANNEL_META: Record<Channel, StatusMeta> = {
  telegram: { tone: 'neutral', label: 'تلگرام', code: 'TELEGRAM', Icon: Send },
  instagram_dm: { tone: 'neutral', label: 'دایرکت اینستاگرام', code: 'INSTAGRAM_DM', Icon: Instagram },
  web_store: { tone: 'neutral', label: 'فروشگاه وب', code: 'WEB_STORE', Icon: Store },
};

/**
 * Gateway-side payment state. `FAILED` is the only danger state; a `REFUNDED`
 * payment is a legal outcome with its own audit trail, not an alarm.
 */
export const PAYMENT_STATUS_META: Record<PaymentStatus, StatusMeta> = {
  PAID: { tone: 'success', label: 'پرداخت‌شده', code: 'PAID', Icon: CircleCheck },
  PENDING_PAYMENT: { tone: 'warning', label: 'در انتظار پرداخت', code: 'PENDING_PAYMENT', Icon: Hourglass },
  FAILED: { tone: 'danger', label: 'پرداخت ناموفق', code: 'FAILED', Icon: CircleX },
  REFUNDED: { tone: 'neutral', label: 'بازپرداخت‌شده', code: 'REFUNDED', Icon: Undo2 },
};

/** Fulfillment lens over the D-081 lifecycle (presentation taxonomy). */
export const FULFILLMENT_STATUS_META: Record<FulfillmentStatus, StatusMeta> = {
  UNFULFILLED: { tone: 'neutral', label: 'تأمین‌نشده', code: 'UNFULFILLED', Icon: CircleDashed },
  PROCESSING: { tone: 'warning', label: 'در حال پردازش', code: 'PROCESSING', Icon: Gauge },
  SHIPPED: { tone: 'success', label: 'ارسال‌شده', code: 'SHIPPED', Icon: Truck },
  DELIVERED: { tone: 'success', label: 'تحویل‌شده', code: 'DELIVERED', Icon: PackageCheck },
  CANCELLED: { tone: 'neutral', label: 'لغوشده', code: 'CANCELLED', Icon: Ban },
};

/** Canonical D-081 lifecycle states, as rendered in the status history. */
export const LIFECYCLE_STATE_META: Record<LifecycleState, StatusMeta> = {
  PLACED: { tone: 'neutral', label: 'ثبت‌شده', code: 'PLACED', Icon: CircleDashed },
  VALIDATED: { tone: 'neutral', label: 'اعتبارسنجی‌شده', code: 'VALIDATED', Icon: CircleCheck },
  FULFILLING: { tone: 'warning', label: 'در حال تأمین', code: 'FULFILLING', Icon: Gauge },
  COMPLETED: { tone: 'success', label: 'تکمیل‌شده', code: 'COMPLETED', Icon: PackageCheck },
  CANCELLED: { tone: 'neutral', label: 'لغوشده', code: 'CANCELLED', Icon: Ban },
  REFUNDED: { tone: 'warning', label: 'بازپرداخت‌شده', code: 'REFUNDED', Icon: Undo2 },
};

/** Risk buckets; the numeric score stays visible next to the badge. */
export const RISK_LEVEL_META: Record<RiskLevel, StatusMeta> = {
  LOW: { tone: 'success', label: 'ریسک کم', code: 'LOW', Icon: CircleCheck },
  MEDIUM: { tone: 'warning', label: 'ریسک متوسط', code: 'MEDIUM', Icon: TriangleAlert },
  HIGH: { tone: 'danger', label: 'ریسک بالا', code: 'HIGH', Icon: ShieldAlert },
};

/** Settlement position of captured money (integer Toman). */
export const SETTLEMENT_STATE_META: Record<SettlementState, StatusMeta> = {
  SETTLED: { tone: 'success', label: 'تسویه‌شده', code: 'SETTLED', Icon: Landmark },
  PENDING: { tone: 'warning', label: 'در انتظار تسویه', code: 'PENDING', Icon: Hourglass },
  NOT_APPLICABLE: { tone: 'neutral', label: 'نامرتبط', code: 'NOT_APPLICABLE', Icon: CircleDashed },
  REFUNDED: { tone: 'neutral', label: 'بازگشته', code: 'REFUNDED', Icon: Undo2 },
};
