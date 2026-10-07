/**
 * The seven canonical routes of the control plane (D-171 §5).
 *
 * Titles are Persian (the UI language) with the English code preserved for
 * traceability, matching the spec's "icon + Persian label + English status
 * code" convention.
 */

export interface RouteSpec {
  /** Canonical path, exactly as specified in D-171 §5. */
  href:
    | '/dashboard'
    | '/hitl-queue'
    | '/inventory'
    | '/automations'
    | '/ai-engine'
    | '/orders'
    | '/settings';
  /** Persian display title. */
  title: string;
  /** English code retained for traceability. */
  code: string;
  /** Short Persian description shown on the page and in the nav tooltip. */
  description: string;
  /**
   * Phase that implements the page's real content, following the owner's
   * renumbered Phase 27 sequence (27.1 foundations, 27.2 shell, 27.3
   * executive overview, 27.4 HITL, 27.5 inventory & canonical SKU control,
   * 27.6 telemetry & gates, 27.7 AI ops, 27.8 commerce). The 2026-10-04
   * inventory directive moved inventory ahead of telemetry, so those two
   * labels swapped; D-171 §4 content is unchanged.
   */
  phase: string;
}

export const ROUTES: RouteSpec[] = [
  {
    href: '/dashboard',
    title: 'نمای فرماندهی',
    code: 'EXECUTIVE_OVERVIEW',
    // Subtitle copy is shared by BOTH views (PageHeader), so it stays plain
    // Persian: console vocabulary lives in the console's own panels. Phase
    // 27.13 classification rule — see DECISIONS.md row 72.
    description: 'یک نگاه کلی به فروش، سفارش‌ها و کارهایی که منتظر تصمیم شماست',
    phase: 'Phase 27.3',
  },
  {
    href: '/hitl-queue',
    title: 'صف تأیید انسانی',
    code: 'HITL_QUEUE',
    description: 'تصمیم‌های هوش مصنوعی در انتظار بازبینی انسانی',
    phase: 'Phase 27.4',
  },
  {
    href: '/inventory',
    title: 'موجودی و محصولات',
    code: 'INVENTORY',
    // Subtitle copy is shared by BOTH views, so it names the business meaning
    // only; D-015's separate Product ID / Variant ID / SKU identity lives in
    // the console's own columns (Phase 27.13).
    description: 'موجودی، قیمت و وضعیت همگام‌سازی محصولات فروشگاه',
    phase: 'Phase 27.5',
  },
  {
    href: '/automations',
    title: 'اتوماسیون‌ها',
    code: 'AUTOMATIONS',
    description: 'کارهای خودکار فروشگاه و نتیجهٔ آخرین اجراها',
    phase: 'Phase 27.6',
  },
  {
    href: '/ai-engine',
    title: 'موتور هوش مصنوعی',
    code: 'AI_ENGINE',
    description: 'وضعیت دستیارهای هوشمند فروشگاه و مصرف آن‌ها',
    phase: 'Phase 27.7',
  },
  {
    href: '/orders',
    title: 'سفارش‌ها',
    code: 'ORDERS',
    description: 'مسیر حسابرسی تراکنش‌ها، پرداخت و فاکتور',
    phase: 'Phase 27.8',
  },
  {
    href: '/settings',
    title: 'تنظیمات',
    code: 'SETTINGS',
    description: 'تنظیمات فروشگاه، اتصال‌ها و کلید توقف اضطراری',
    phase: 'Phase 27.8',
  },
];

export function routeByHref(href: RouteSpec['href']): RouteSpec {
  const found = ROUTES.find((r) => r.href === href);
  if (!found) throw new Error(`unknown route: ${href}`);
  return found;
}
