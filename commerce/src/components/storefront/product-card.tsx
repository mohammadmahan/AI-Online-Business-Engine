import Link from 'next/link';

import type { StorefrontProductCard } from '@/contracts/storefront';
import { formatToman } from '@/lib/format';

/**
 * D-172 §3.1/§3.2 — the grid and carousel card.
 *
 * Presentational and free of state, so a page can render it on the server. It
 * shows only what the public read model carries: a stock LEVEL (never a
 * quantity), the sizes the published variants actually have, and the resolved
 * price — nothing about cost, drafts or inventory counts.
 *
 * Editorial treatment (D-172 §3): a 3:4 portrait crop, no card chrome, the title
 * in the display face and the price as the second typographic beat. Availability
 * still carries BOTH a Persian label and its Latin code, so state never depends
 * on colour alone (D-171 §3.5). `article > h3` is the structure the storefront
 * E2E script asserts, so it is preserved exactly.
 */
export function ProductCard({ card }: { card: StorefrontProductCard }) {
  return (
    <article className="group flex h-full flex-col">
      <Link
        href={`/products/${card.slug}`}
        className="block overflow-hidden rounded-sf bg-sf-muted"
        tabIndex={-1}
        aria-hidden="true"
      >
        {card.primaryImageUrl ? (
          /* eslint-disable-next-line @next/next/no-img-element -- the media host is an open owner decision (D-172 G-5); next/image would need a remotePatterns entry for a host that does not exist yet. */
          <img
            src={card.primaryImageUrl}
            alt=""
            loading="lazy"
            className="sf-zoom aspect-[3/4] w-full object-cover"
          />
        ) : (
          <span className="flex aspect-[3/4] w-full items-center justify-center text-sf-caption text-sf-ink-muted">
            بدون تصویر
          </span>
        )}
      </Link>

      <div className="flex flex-1 flex-col gap-1.5 pt-4">
        <p className="text-sf-caption text-sf-ink-muted">{card.categoryName}</p>
        <h3 className="font-display text-lg font-semibold leading-snug text-sf-ink">
          <Link href={`/products/${card.slug}`} className="sf-link">
            {card.title}
          </Link>
        </h3>

        <p className="mt-1 flex flex-wrap items-baseline gap-2">
          <span className="text-sf-body font-medium text-sf-ink">
            {formatToman(card.effectivePrice)}
          </span>
          {card.hasDiscount ? (
            <>
              <s className="text-sf-caption text-sf-ink-muted">{formatToman(card.basePrice)}</s>
              <span className="text-sf-caption font-medium text-sf-accent">تخفیف‌دار</span>
            </>
          ) : null}
        </p>

        <p className="mt-auto flex flex-wrap items-center gap-x-2 gap-y-1 pt-2 text-sf-caption text-sf-ink-muted">
          <span className="inline-flex items-center gap-1.5">
            <span
              aria-hidden="true"
              className={`size-1.5 rounded-full ${
                card.availability === 'IN' ? 'bg-sf-accent' : 'bg-sf-edge-strong'
              }`}
            />
            {card.availability === 'IN' ? 'موجود' : 'ناموجود'}{' '}
            <span className="cp-code">{card.availability}</span>
          </span>
          {card.sizes.length > 0 ? <span aria-hidden="true">·</span> : null}
          {card.sizes.map((size) => (
            <span key={size} className="cp-code">
              {size}
            </span>
          ))}
        </p>
      </div>
    </article>
  );
}
