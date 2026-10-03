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
   * executive overview, 27.4 HITL, 27.5 telemetry, 27.6 inventory, 27.7
   * AI ops, 27.8 commerce).
   */
  phase: string;
}

export const ROUTES: RouteSpec[] = [
  {
    href: '/dashboard',
    title: 'نمای فرماندهی',
    code: 'EXECUTIVE_OVERVIEW',
    description: 'شاخص‌های کلیدی، وضعیت گیت‌ها و سلامت سرویس‌ها',
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
    description: 'نمایش Product ID، Variant ID و SKU به‌صورت جداگانه',
    phase: 'Phase 27.6',
  },
  {
    href: '/automations',
    title: 'اتوماسیون‌ها',
    code: 'AUTOMATIONS',
    description: 'وضعیت و تلمتری جریان‌های کاری n8n و صف‌ها',
    phase: 'Phase 27.5',
  },
  {
    href: '/ai-engine',
    title: 'موتور هوش مصنوعی',
    code: 'AI_ENGINE',
    description: 'مشاهده‌پذیری عامل‌ها، مصرف توکن و وضعیت حافظه‌ی مشترک',
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
    description: 'پیکربندی سیستم، یکپارچه‌سازی‌ها و کلیدهای اضطراری',
    phase: 'Phase 27.8',
  },
];

export function routeByHref(href: RouteSpec['href']): RouteSpec {
  const found = ROUTES.find((r) => r.href === href);
  if (!found) throw new Error(`unknown route: ${href}`);
  return found;
}
