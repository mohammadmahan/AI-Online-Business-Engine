import Link from 'next/link';

import { Card, Placeholder } from '@/components/ui/card';
import { VIEW_GATE_CLASS } from '@/components/ui/view-gate';
import { routeByHref, type RouteSpec } from '@/lib/routes';

/** Technical-only class, applied inline where a wrapper node would be wrong. */
const TECHNICAL_ONLY_CLASS = VIEW_GATE_CLASS.technical;

/**
 * Breadcrumb + Persian title + English code for one route.
 *
 * Shared by every page so the seven routes stay structurally identical
 * (D-171 §5). `PageShell` composes it with the not-yet-wired placeholder; the
 * executive overview uses the header alone because it renders real content.
 */
export function PageHeader({
  href,
  meta,
}: {
  href: RouteSpec['href'];
  /** Optional extra line under the description (e.g. a data-provenance note). */
  meta?: React.ReactNode;
}) {
  const route = routeByHref(href);

  return (
    <>
      <nav aria-label="مسیر صفحه">
        <ol className="flex items-center gap-2 text-cp-caption text-ink-muted">
          <li>
            <Link href="/dashboard" className="hover:text-ink hover:underline">
              صفحهٔ کنترل
            </Link>
          </li>
          <li aria-hidden="true">/</li>
          <li aria-current="page" className="text-ink">
            {route.title}
          </li>
        </ol>
      </nav>

      <div>
        <h1 className="text-cp-display font-bold text-ink">{route.title}</h1>
        <p className="mt-1 text-cp-label text-ink-muted">
          {route.description}{' '}
          {/* The route's machine code is a console asset (Phase 27.13): the
              Business view shows the Persian title/description only. */}
          <span
            data-view-gate="technical"
            data-surface="page-route-code"
            className={`font-mono text-cp-caption opacity-80 ${TECHNICAL_ONLY_CLASS}`}
          >
            ({route.code})
          </span>
        </p>
        {meta}
      </div>
    </>
  );
}

/**
 * Shared page shell for routes whose data source is not wired yet. It states
 * the truth (nothing is connected) rather than showing zeros, which would read
 * as a real measurement (D-171 §2.2).
 */
export function PageShell({
  href,
  children,
}: {
  href: RouteSpec['href'];
  children?: React.ReactNode;
}) {
  const route = routeByHref(href);

  return (
    <div className="mx-auto flex max-w-6xl flex-col gap-4">
      <PageHeader href={href} />
      <Card>
        <Placeholder>
          دادهٔ زنده پس از تکمیل راه‌اندازی متصل می‌شود. تا آن زمان وضعیت این صفحه{' '}
          <strong>نامشخص (UNKNOWN)</strong> است — نه صفر، نه موفق.
          {/* The roadmap phase label is internal project vocabulary (Phase
              27.13): the Business view states the truth without it. */}
          <span
            data-view-gate="technical"
            data-surface="page-phase-ref"
            className={`mt-1 block font-mono text-cp-caption text-ink-muted ${TECHNICAL_ONLY_CLASS}`}
          >
            فعال‌سازی در {route.phase}
          </span>
        </Placeholder>
        {children}
      </Card>
    </div>
  );
}
