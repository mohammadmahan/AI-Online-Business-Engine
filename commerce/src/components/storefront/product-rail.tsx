import type { StorefrontProductCard } from '@/contracts/storefront';

import { ProductCard } from './product-card';
import { SectionTitle } from './storefront-primitives';

/**
 * D-172 §3.1 — a carousel rail (New Arrivals / Best Sellers).
 *
 * A horizontally scrollable list rather than a JavaScript carousel: native
 * scroll-snap works with a trackpad, a touch swipe, a keyboard and a screen
 * reader, and it degrades to a plain row when scrolling is unavailable. A rail
 * with nothing in it renders NOTHING — an empty "پرفروش‌ها" heading would be a
 * claim about the shop that is not true yet.
 *
 * Editorial: the heading sits above a hairline, and the track is bled to the page
 * gutter so the first and last card align with the text column.
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
    <section aria-labelledby={id} className="mt-14">
      <div className="flex flex-wrap items-baseline justify-between gap-x-6 gap-y-1 border-b border-sf-edge pb-3">
        <SectionTitle id={id}>{title}</SectionTitle>
        {description ? (
          <p className="text-sf-caption text-sf-ink-muted">{description}</p>
        ) : null}
      </div>
      <ul className="mt-6 grid snap-x snap-mandatory grid-flow-col auto-cols-[minmax(13rem,1fr)] gap-6 overflow-x-auto pb-2 sm:auto-cols-[minmax(16rem,1fr)]">
        {cards.map((card) => (
          <li key={card.id} className="snap-start">
            <ProductCard card={card} />
          </li>
        ))}
      </ul>
    </section>
  );
}
