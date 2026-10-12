import type { StorefrontProductCard } from '@/contracts/storefront';

import { ProductCard } from './product-card';

/**
 * D-172 §3.1 — a carousel rail (New Arrivals / Best Sellers).
 *
 * A horizontally scrollable list rather than a JavaScript carousel: native
 * scroll-snap works with a trackpad, a touch swipe, a keyboard and a screen
 * reader, and it degrades to a plain row when scrolling is unavailable. A rail
 * with nothing in it renders NOTHING — an empty "پرفروش‌ها" heading would be a
 * claim about the shop that is not true yet.
 */
export function ProductRail({
  id,
  title,
  description,
  cards,
}: {
  id: string;
  title: string;
  description?: string;
  cards: StorefrontProductCard[];
}) {
  if (cards.length === 0) {
    return null;
  }

  return (
    <section aria-labelledby={id} className="mt-8">
      <h2 id={id} className="text-cp-heading font-semibold text-ink">
        {title}
      </h2>
      {description ? <p className="mt-1 text-cp-label text-ink-muted">{description}</p> : null}
      <ul className="mt-4 grid snap-x snap-mandatory grid-flow-col auto-cols-[minmax(13rem,1fr)] gap-4 overflow-x-auto pb-2 sm:auto-cols-[minmax(16rem,1fr)]">
        {cards.map((card) => (
          <li key={card.id} className="snap-start">
            <ProductCard card={card} />
          </li>
        ))}
      </ul>
    </section>
  );
}
