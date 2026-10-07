'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import {
  Activity,
  Boxes,
  BrainCircuit,
  LayoutDashboard,
  ListChecks,
  Receipt,
  ScrollText,
  Server,
  Workflow,
  type LucideIcon,
} from 'lucide-react';

import { Tooltip } from '@/components/ui/tooltip';
import { ROUTES, type RouteSpec } from '@/lib/routes';
import { cn } from '@/lib/utils';

/**
 * D-171 §2.3 / §10 — contextual navigation shell (Phase 27.10, localized in
 * Phase 27.11).
 *
 * ONE panel, TWO navigation sets. `business` is the default, task-oriented
 * Persian list — plain language only, no container name, port, HTTP status,
 * sidecar, probe, telemetry or ledger vocabulary (§2.3 الف). `technical` is the
 * full operational list: the directive's console entries with their canonical
 * English identifiers kept inline (they are system names, not labels to
 * translate), PLUS every operational route shipped in 27.1–27.8, so nothing is
 * deleted — only contextualized (§10 acceptance: "هیچ مسیر فنی حذف نمی‌شود،
 * فقط زمینه‌محور/پنهان می‌گردد؛ مسیر فعال همیشه صریح است").
 *
 * ── Why both sets are rendered and CSS picks the visible one ───────────────
 * The active view is already on the DOM before first paint:
 * `document.documentElement.dataset.viewMode` is written by the pre-paint
 * bootstrap in `lib/context/view-mode-context.tsx`. Gating the two sets with
 * CSS attribute selectors therefore shows the correct list in the FIRST paint.
 * Rendering them from `useViewMode()` instead would paint the hydration
 * snapshot (`business`) first and replace it after hydration — a visible flash
 * of the wrong menu on every reload in the technical view. Reading the same
 * pre-paint attribute through CSS keeps the swap instant, flash-free and
 * hydration-safe, exactly like the theme layer. The inactive set is
 * `display: none`, so it is neither focusable nor exposed to assistive tech.
 * This deviation from "consume `useViewMode()` in the sidebar" is recorded in
 * D-171 §10 and in the D-171 decision row.
 *
 * Switching a view never navigates: the header switcher only writes the view
 * state, so the current route is kept (§10). `aria-current="page"` is emitted
 * by whichever set is visible; if the active route belongs to the other view,
 * this shell appends a single "صفحهٔ جاری" entry instead of highlighting
 * nothing.
 *
 * Phase 27.11 adds one accessible micro-help tooltip per entry (hover AND
 * keyboard focus, `aria-describedby`-linked, token-only, RTL-aligned); the
 * Business entries explain the task in plain Persian, the Technical entries
 * stay terse and operational.
 *
 * The pending badge count is a server prop (see `app/layout.tsx`) taken from
 * the SAME deterministic HITL source the queue page renders, so the badge and
 * the queue can never disagree — no second data layer, no client fetch.
 */

interface NavItem {
  /** Canonical route — this module never invents or renames a URL (D-171 §5). */
  href: RouteSpec['href'];
  /** Contextual Persian label for this view. */
  label: string;
  /** Micro-help: one sentence, in THIS view's vocabulary (§10, 27.11). */
  tip: string;
  Icon: LucideIcon;
  /** Show the pending HITL review count next to the label. */
  showPending?: boolean;
}

/**
 * Business view — short, task-oriented, plain Persian (D-171 §2.3 الف).
 * No container, probe, telemetry, ledger or HTTP vocabulary is allowed here.
 */
const BUSINESS_ITEMS: readonly NavItem[] = [
  {
    href: '/dashboard',
    label: 'پیشخوان',
    tip: 'یک نگاه سریع به فروش، وضعیت سفارش‌ها و کارهایی که منتظر تصمیم شماست.',
    Icon: LayoutDashboard,
  },
  {
    href: '/orders',
    label: 'سفارش‌ها',
    tip: 'همهٔ سفارش‌های ثبت‌شده؛ پرداخت‌ها، وضعیت ارسال و صورت‌حساب‌ها.',
    Icon: Receipt,
  },
  {
    href: '/inventory',
    label: 'انبار و محصولات',
    tip: 'موجودی و قیمت هر محصول و کالاهایی که در حال تمام‌شدن هستند.',
    Icon: Boxes,
  },
  {
    href: '/hitl-queue',
    label: 'کارهای نیازمند تأیید',
    tip: 'کارهایی که ربات نمی‌تواند تنهایی تصمیم بگیرد و به تصمیم شما نیاز دارد.',
    Icon: ListChecks,
    showPending: true,
  },
  {
    href: '/automations',
    label: 'عملیات‌های خودکار',
    tip: 'کارهای تکراری که فروشگاه خودکار انجام می‌دهد و نتیجهٔ آخرین اجراها.',
    Icon: Workflow,
  },
];

/**
 * Technical console — the full operational list. Canonical English
 * identifiers stay inline wherever the Persian label names a system (per the
 * Phase 27.11 directive): sidecar, HTTP, probe names, trace ids, SKU, D-121
 * are operational identifiers, never translated.
 *
 * The container/sidecar probe assets (ids, probe latency, HTTP status, queue
 * pressure, gate matrix V-01..V-10) are rendered on `/automations`, which is
 * why "کانتینرها و سایدکار سلامت" points there rather than at the executive
 * overview; the raw D-121 ledger and audit-retention surface is `/settings`
 * (D-171 §5.7 «لجر و حسابرسی»). Both are existing routes — nothing is added.
 */
const TECHNICAL_ITEMS: readonly NavItem[] = [
  {
    href: '/dashboard',
    label: 'نمای ادمین و تلمتری (System Overview)',
    tip: 'شاخص‌های خام اجرایی، سلامت سرویس‌ها و جریان رویدادهای لجر (D-121).',
    Icon: Activity,
  },
  {
    href: '/automations',
    label: 'کانتینرها و سایدکار سلامت (Sidecar Health)',
    tip: 'کاوش زندهٔ sidecar: تأخیر، کد وضعیت HTTP، فشار صف و ماتریس گیت‌ها V-01..V-10.',
    Icon: Server,
  },
  {
    href: '/ai-engine',
    label: 'صف خام تصمیمات و موتور AI (AI Runtime)',
    tip: 'مشاهده‌پذیری عامل‌ها، مصرف توکن، وضعیت حافظهٔ مشترک و ردهای خام (trace).',
    Icon: BrainCircuit,
  },
  {
    href: '/hitl-queue',
    label: 'صف بازبینی فنی (HITL Ledger)',
    tip: 'لجر خام تیکت‌های HITL با payload، diff و لاگ استدلال (D-027).',
    Icon: ListChecks,
    showPending: true,
  },
  {
    href: '/settings',
    label: 'لاگ‌های ممیزی (Audit Ledger D-121)',
    tip: 'لجر رویدادها، وضعیت یکپارچگی زنجیره و خروجی حسابرسی.',
    Icon: ScrollText,
  },
  {
    href: '/orders',
    label: 'سفارش‌ها (ORDERS)',
    tip: 'مسیر حسابرسی تراکنش‌ها، پرداخت و فاکتور در سطح رکوردهای خام.',
    Icon: Receipt,
  },
  {
    href: '/inventory',
    label: 'موجودی و SKU (Inventory)',
    tip: 'Product ID / Variant ID / SKU به‌صورت جدا (D-015) و رکوردهای همگام‌سازی.',
    Icon: Boxes,
  },
];

/** Canonical icon per route — used by the "current page" fallback entry. */
const ROUTE_ICON: Record<RouteSpec['href'], LucideIcon> = {
  '/dashboard': LayoutDashboard,
  '/hitl-queue': ListChecks,
  '/inventory': Boxes,
  '/automations': Workflow,
  '/ai-engine': BrainCircuit,
  '/orders': Receipt,
  '/settings': ScrollText,
};

/** Stable, collision-free tooltip id (both sets live in the same document). */
function tipId(set: string, href: RouteSpec['href']): string {
  return `nav-tip-${set}-${href.replace(/\//g, '-')}`;
}

/** One navigation row: link + badge + micro-help tooltip. */
function NavRow({
  item,
  set,
  active,
  pending,
}: {
  item: NavItem;
  set: 'business' | 'technical';
  active: boolean;
  pending: number;
}) {
  const Icon = item.Icon;
  const id = tipId(set, item.href);
  const showBadge = item.showPending === true && pending > 0;

  return (
    <Tooltip id={id} text={item.tip} className="flex w-full">
      <Link
        href={item.href}
        aria-current={active ? 'page' : undefined}
        aria-describedby={id}
        className={cn(
          'cp-target flex w-full items-center gap-3 rounded-[--radius-cp]',
          'px-3 py-2 text-cp-label font-medium transition-colors',
          active ? 'bg-primary text-surface' : 'text-ink hover:bg-surface-muted',
        )}
      >
        <Icon aria-hidden="true" className="size-4 shrink-0" />
        <span className="flex-1">{item.label}</span>
        {showBadge ? (
          <span
            className={cn(
              'inline-flex min-w-6 shrink-0 items-center justify-center rounded-full',
              'px-1.5 py-0.5 text-cp-caption font-semibold tabular-nums',
              // On the active (primary-filled) row the chip takes the surface
              // pairing, so its own fill stays distinguishable from the row fill;
              // on inactive rows it is the gate-enforced warning chip pairing.
              active ? 'bg-surface text-ink' : 'bg-warning text-on-warning',
            )}
          >
            <span className="sr-only">مورد در انتظار تأیید: </span>
            {pending}
          </span>
        ) : null}
      </Link>
    </Tooltip>
  );
}

/**
 * Keeps the active route explicit when it does not live in this view's set
 * (deep link, bookmark, or the Phase 27.12 drill-down bridge). The view swap
 * never navigates, so without this entry the visible set would highlight
 * nothing at all — the one outcome D-171 §10 forbids.
 */
function CurrentRouteEntry({
  pathname,
  items,
}: {
  pathname: string;
  items: readonly NavItem[];
}) {
  if (items.some((item) => item.href === pathname)) return null;
  const route = ROUTES.find((candidate) => candidate.href === pathname);
  if (route === undefined) return null; // unknown path (e.g. not-found)
  const Icon = ROUTE_ICON[route.href];
  const id = 'nav-tip-current';

  return (
    <li className="mt-2 border-t border-edge pt-2">
      <p className="px-2 pb-1 text-cp-caption text-ink-muted">صفحهٔ جاری</p>
      <Tooltip
        id={id}
        text="این صفحه همین حالا باز است؛ در فهرست این نما جای دیگری ندارد."
        className="flex w-full"
      >
        <Link
          href={route.href}
          aria-current="page"
          aria-describedby={id}
          className={cn(
            'cp-target flex w-full items-center gap-3 rounded-[--radius-cp]',
            'bg-primary px-3 py-2 text-cp-label font-medium text-surface transition-colors',
          )}
        >
          <Icon aria-hidden="true" className="size-4 shrink-0" />
          <span className="flex-1">{route.title}</span>
        </Link>
      </Tooltip>
    </li>
  );
}

function NavSet({
  name,
  heading,
  items,
  pathname,
  pending,
}: {
  name: 'business' | 'technical';
  heading: string;
  items: readonly NavItem[];
  pathname: string;
  pending: number;
}) {
  const visible =
    name === 'business'
      ? 'flex [[data-view-mode=technical]_&]:hidden'
      : 'hidden [[data-view-mode=technical]_&]:flex';

  return (
    <nav
      data-nav-set={name}
      aria-label={heading}
      className={cn('flex-col gap-1', visible)}
    >
      <p className="mb-2 px-2 text-cp-caption font-medium text-ink-muted">
        {heading}
      </p>
      <ul className="flex flex-col gap-1">
        {items.map((item) => (
          <li key={item.href}>
            <NavRow
              item={item}
              set={name}
              active={pathname === item.href}
              pending={pending}
            />
          </li>
        ))}
        <CurrentRouteEntry pathname={pathname} items={items} />
      </ul>
    </nav>
  );
}

export function Sidebar({
  /** Pending HITL reviews, computed by the server shell from the queue source. */
  hitlPending,
}: {
  hitlPending: number;
}) {
  const pathname = usePathname();

  return (
    <div className="flex h-full flex-col gap-1 border-e border-edge bg-surface p-3">
      <NavSet
        name="business"
        heading="مدیریت فروشگاه (BUSINESS)"
        items={BUSINESS_ITEMS}
        pathname={pathname}
        pending={hitlPending}
      />
      <NavSet
        name="technical"
        heading="کنسول زیرساخت (TECHNICAL)"
        items={TECHNICAL_ITEMS}
        pathname={pathname}
        pending={hitlPending}
      />
    </div>
  );
}
