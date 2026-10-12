import Link from 'next/link';

import type { StorefrontProductCard } from '@/contracts/storefront';
import { formatToman } from '@/lib/format';
import { Badge } from '@/components/ui/primitives';

/**
 * D-172 §3.1/§3.2 — the grid and carousel card.
 *
 * Presentational and free of state, so a page can render it on the server. It
 * shows only what the public read model carries: a stock LEVEL (never a
 * quantity), the sizes the published variants actually have, and the resolved
 * price — nothing about cost, drafts or inventory counts.
 */
export function ProductCard({ card }: { card: StorefrontProductCard }) {
  return (
    <article className="flex h-full flex-col overflow-hidden rounded-[--radius-cp] border border-edge bg-surface">
      <Link href={`/products/${card.slug}`} className="block" tabIndex={-1} aria-hidden="true">
        {card.primaryImageUrl ? (
          /* eslint-disable-next-line @next/next/no-img-element -- the media host is an open owner decision (D-172 G-5); next/image would need a remotePatterns entry for a host that does not exist yet. */
          <img
            src={card.primaryImageUrl}
            alt=""
            loading="lazy"
            className="aspect-square w-full bg-surface-muted object-cover"
          />
        ) : (
          <span className="flex aspect-square w-full items-center justify-center bg-surface-muted text-cp-caption text-ink-muted">
            بدون تصویر
          </span>
        )}
      </Link>

      <div className="flex flex-1 flex-col gap-2 p-3">
        <h3 className="text-cp-label font-semibold text-ink">
          <Link href={`/products/${card.slug}`}>{card.title}</Link>
        </h3>
        <p className="text-cp-caption text-ink-muted">{card.categoryName}</p>

        <p className="flex flex-wrap items-baseline gap-2">
          <span className="text-cp-body font-bold text-ink">{formatToman(card.effectivePrice)}</span>
          {card.hasDiscount ? (
            <>
              <s className="text-cp-caption text-ink-muted">{formatToman(card.basePrice)}</s>
              <Badge tone="warning">تخفیف‌دار</Badge>
            </>
          ) : null}
        </p>

        <p className="mt-auto flex flex-wrap items-center gap-1">
          <Badge tone={card.availability === 'IN' ? 'success' : 'danger'}>
            {card.availability === 'IN' ? 'موجود' : 'ناموجود'}{' '}
            <span className="cp-code">{card.availability}</span>
          </Badge>
          {card.sizes.map((size) => (
            <span
              key={size}
              className="rounded-[--radius-cp] border border-edge px-1.5 py-0.5 text-cp-caption text-ink-muted"
            >
              <span className="cp-code">{size}</span>
            </span>
          ))}
        </p>
      </div>
    </article>
  );
}
