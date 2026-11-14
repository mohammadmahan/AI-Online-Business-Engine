'use client';

import { useMemo, useState } from 'react';

import type {
  CatalogFilters,
  CatalogSort,
  StorefrontProductCard,
} from '@/contracts/storefront';
import { EMPTY_CATALOG_FILTERS } from '@/contracts/storefront';
import {
  CATALOG_PAGE_SIZE,
  applyFilters,
  countActiveFilters,
  deriveFacets,
  paginate,
  priceStepFor,
  withCategory,
} from '@/lib/catalog-filters';
import { formatCountFa, formatToman } from '@/lib/format';
import { CATALOG_SORT_OPTIONS } from '@/lib/storefront-display';
import { sfButton, sfChip, sfField } from '@/components/storefront/storefront-primitives';
import { cn } from '@/lib/utils';
import type { StorefrontCategory } from '@/server/repository';

import { ProductCard } from './product-card';

/**
 * D-172 §3.2 — the catalog: faceted, instant, and entirely client-side.
 *
 * The server sends the PUBLISHED cards once; every filter below runs in the
 * browser through `@/lib/catalog-filters`, so a chip is instant and costs no
 * round trip. The facets themselves are DERIVED from those cards, which is why a
 * size nobody stocks, or a colour nobody sells, never appears as an option.
 *
 * Phase 2B (D-177) puts this surface on the editorial layer: hairline panel on
 * ivory, ink chips instead of the panel's blue `aria-pressed` treatment, display
 * typography and editorial grid rhythm. On a phone the whole filter panel would
 * otherwise push the first row of products below the fold, so it starts
 * COLLAPSED behind an `aria-expanded` disclosure; the desktop rail is always
 * open. Filtering is unchanged and still instant either way.
 *
 * Filters that match nothing say so and offer a way back, and the paging button
 * reports how many products are left instead of merely being enabled — the two
 * states a customer would otherwise read as a broken page.
 */

export function CatalogBrowser({
  cards,
  categories,
  initialCategory = null,
}: {
  cards: StorefrontProductCard[];
  categories: StorefrontCategory[];
  initialCategory?: string | null;
}) {
  const [filters, setFilters] = useState<CatalogFilters>({
    ...EMPTY_CATALOG_FILTERS,
    category: initialCategory,
  });
  const [page, setPage] = useState(1);
  // Closed on a phone so the grid is visible on arrival; the `lg:` rail is
  // always shown regardless of this state.
  const [filtersOpen, setFiltersOpen] = useState(false);

  const facets = useMemo(() => deriveFacets(cards), [cards]);
  const ceiling = facets.maxPrice > 0 ? facets.maxPrice : 0;
  // The rail can only offer multiples of `step`, so a fixed step would leave a
  // ceiling that is not a multiple of it unreachable (`@/lib/catalog-filters`).
  const priceStep = priceStepFor(ceiling);

  // The two sliders hold their own values so a drag stays smooth; only a value
  // that actually narrows the range is written into the filter state.
  const [minSlider, setMinSlider] = useState(0);
  const [maxSlider, setMaxSlider] = useState(ceiling);

  const filtered = useMemo(() => applyFilters(cards, filters), [cards, filters]);
  const visible = paginate(filtered, page, CATALOG_PAGE_SIZE);
  const activeCount = countActiveFilters(filters);

  // A category can arrive AFTER the first render: `/catalog?category=…` is the
  // homepage's category-circle target, and the App Router keeps this component
  // mounted when only a search parameter changes (back/forward, or another
  // category link while the catalog is already open). The prop only seeds state,
  // so it is re-applied here during render — React's own pattern for state
  // derived from a prop, and cheaper than an effect, which would paint the stale
  // list once first. Paging resets because the result list is a new one. Choosing
  // a chip on this page changes state, never the URL, so `appliedCategory` and
  // the incoming prop stay equal and the customer's own choice is never undone.
  const [appliedCategory, setAppliedCategory] = useState<string | null>(initialCategory);
  if (appliedCategory !== initialCategory) {
    setAppliedCategory(initialCategory);
    setFilters((current) => withCategory(current, initialCategory));
    setPage(1);
  }

  /** Every filter change resets paging: results are a new list, not a longer one. */
  function update(patch: Partial<CatalogFilters>) {
    setFilters((current) => ({ ...current, ...patch }));
    setPage(1);
  }

  function clearAll() {
    setFilters(EMPTY_CATALOG_FILTERS);
    setMinSlider(0);
    setMaxSlider(ceiling);
    setPage(1);
  }

  function toggle(list: string[], value: string): string[] {
    return list.includes(value) ? list.filter((entry) => entry !== value) : [...list, value];
  }

  const filterPanelId = 'catalog-filters';

  return (
    <div className="mt-10 flex flex-col gap-8 lg:flex-row lg:items-start">
      <div className="flex flex-wrap items-center gap-3 lg:hidden">
        <button
          type="button"
          aria-expanded={filtersOpen}
          aria-controls={filterPanelId}
          className={cn(sfButton.quiet, 'flex-1 justify-between')}
          onClick={() => setFiltersOpen((open) => !open)}
        >
          <span className="flex items-center gap-2">
            فیلترها
            {activeCount > 0 ? (
              <span className="text-sf-ink-muted">({formatCountFa(activeCount)})</span>
            ) : null}
          </span>
          <span aria-hidden="true" className="text-base leading-none">
            {filtersOpen ? '−' : '+'}
          </span>
        </button>
        {activeCount > 0 ? (
          <button type="button" className="sf-link text-sf-caption" onClick={clearAll}>
            پاک کردن فیلترها
          </button>
        ) : null}
      </div>

      <form
        id={filterPanelId}
        aria-label="فیلترهای فهرست محصولات"
        className={cn(
          'w-full flex-col gap-6 rounded-sf border border-sf-edge bg-sf-surface p-5 lg:flex lg:w-80 lg:shrink-0',
          filtersOpen ? 'flex' : 'hidden',
        )}
        onSubmit={(event) => event.preventDefault()}
      >
        <div className="flex flex-col gap-2">
          <label htmlFor="catalog-search" className="text-sf-caption font-medium text-sf-ink">
            جست‌وجو
          </label>
          <input
            id="catalog-search"
            type="search"
            className={sfField}
            value={filters.query}
            placeholder="نام محصول یا دسته"
            onChange={(event) => update({ query: event.target.value })}
          />
        </div>

        <div className="flex flex-col gap-2">
          <label htmlFor="catalog-sort" className="text-sf-caption font-medium text-sf-ink">
            ترتیب نمایش
          </label>
          <select
            id="catalog-sort"
            className={sfField}
            value={filters.sort}
            onChange={(event) => update({ sort: event.target.value as CatalogSort })}
          >
            {CATALOG_SORT_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <fieldset className="flex flex-col gap-3 border-t border-sf-edge pt-6">
          <legend className="text-sf-caption font-medium text-sf-ink">دسته‌بندی</legend>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              aria-pressed={filters.category === null}
              className={cn(
                sfChip.base,
                filters.category === null ? sfChip.active : sfChip.rest,
              )}
              onClick={() => update({ category: null })}
            >
              همه
            </button>
            {categories.map((category) => (
              <button
                key={category.slug}
                type="button"
                aria-pressed={filters.category === category.name}
                className={cn(
                  sfChip.base,
                  filters.category === category.name ? sfChip.active : sfChip.rest,
                )}
                onClick={() => update({ category: category.name })}
              >
                {category.name}
                <span className="text-sf-caption">{formatCountFa(category.productCount)}</span>
              </button>
            ))}
          </div>
        </fieldset>

        {facets.sizes.length > 0 ? (
          <fieldset className="flex flex-col gap-3 border-t border-sf-edge pt-6">
            <legend className="text-sf-caption font-medium text-sf-ink">اندازه</legend>
            <div className="flex flex-wrap gap-2">
              {facets.sizes.map((size) => (
                <button
                  key={size}
                  type="button"
                  aria-pressed={filters.sizes.includes(size)}
                  className={cn(
                    sfChip.base,
                    'px-4',
                    filters.sizes.includes(size) ? sfChip.active : sfChip.rest,
                  )}
                  onClick={() => update({ sizes: toggle(filters.sizes, size) })}
                >
                  <span className="sf-code">{size}</span>
                </button>
              ))}
            </div>
          </fieldset>
        ) : null}

        {facets.colors.length > 0 ? (
          <fieldset className="flex flex-col gap-3 border-t border-sf-edge pt-6">
            <legend className="text-sf-caption font-medium text-sf-ink">رنگ</legend>
            <div className="flex flex-wrap gap-2">
              {facets.colors.map((color) => (
                <button
                  key={color.name}
                  type="button"
                  aria-pressed={filters.colors.includes(color.name)}
                  className={cn(
                    sfChip.base,
                    filters.colors.includes(color.name) ? sfChip.active : sfChip.rest,
                  )}
                  onClick={() => update({ colors: toggle(filters.colors, color.name) })}
                >
                  <span
                    aria-hidden="true"
                    className="inline-block size-4 rounded-full border border-sf-edge-strong"
                    style={{ backgroundColor: color.hex }}
                  />
                  {color.name}
                </button>
              ))}
            </div>
          </fieldset>
        ) : null}

        {ceiling > 0 ? (
          <fieldset className="flex flex-col gap-2 border-t border-sf-edge pt-6">
            <legend className="text-sf-caption font-medium text-sf-ink">محدودهٔ قیمت</legend>
            <label htmlFor="catalog-price-min" className="text-sf-caption text-sf-ink-muted">
              از {formatToman(minSlider)}
            </label>
            <input
              id="catalog-price-min"
              type="range"
              min={0}
              max={ceiling}
              step={priceStep}
              value={minSlider}
              aria-describedby="catalog-price-bounds"
              className="h-11 w-full accent-sf-ink"
              onChange={(event) => {
                const next = Math.min(Number(event.target.value), maxSlider);
                setMinSlider(next);
                update({ minPrice: next === 0 ? null : next });
              }}
            />
            <label htmlFor="catalog-price-max" className="text-sf-caption text-sf-ink-muted">
              تا {formatToman(maxSlider)}
            </label>
            <input
              id="catalog-price-max"
              type="range"
              min={0}
              max={ceiling}
              step={priceStep}
              value={maxSlider}
              aria-describedby="catalog-price-bounds"
              className="h-11 w-full accent-sf-ink"
              onChange={(event) => {
                const next = Math.max(Number(event.target.value), minSlider);
                setMaxSlider(next);
                update({ maxPrice: next >= ceiling ? null : next });
              }}
            />
            <p id="catalog-price-bounds" className="text-sf-caption text-sf-ink-muted">
              کم‌ترین و بیش‌ترین قیمت منتشرشده: {formatToman(facets.minPrice)} تا{' '}
              {formatToman(facets.maxPrice)}
            </p>
          </fieldset>
        ) : null}

        <label className="flex min-h-11 items-center gap-3 border-t border-sf-edge pt-6 text-sf-body text-sf-ink">
          <input
            type="checkbox"
            className="size-4 accent-sf-ink"
            checked={filters.onlyAvailable}
            onChange={(event) => update({ onlyAvailable: event.target.checked })}
          />
          فقط کالاهای موجود
        </label>

        <p className="flex flex-wrap items-center gap-3 text-sf-caption text-sf-ink-muted">
          <span>
            فیلترهای فعال: <span className="text-sf-ink">{formatCountFa(activeCount)}</span>
          </span>
          {activeCount > 0 ? (
            <button type="button" className="sf-link text-sf-caption" onClick={clearAll}>
              پاک کردن فیلترها
            </button>
          ) : null}
        </p>
      </form>

      <div className="min-w-0 flex-1">
        <p role="status" className="text-sf-caption text-sf-ink-muted">
          {visible.total === 0
            ? 'محصولی با این فیلترها پیدا نشد.'
            : `${formatCountFa(visible.total)} محصول، نمایش ${formatCountFa(visible.items.length)} مورد`}
        </p>

        {visible.items.length === 0 ? (
          <div className="mt-6 border border-sf-edge bg-sf-surface p-8">
            <p className="font-display text-xl font-semibold text-sf-ink">نتیجه‌ای پیدا نشد</p>
            <p className="mt-2 max-w-md text-sf-caption leading-relaxed text-sf-ink-muted">
              هیچ محصولی با این ترکیب فیلترها مطابقت ندارد. یکی از فیلترها را بردارید یا همه را پاک
              کنید.
            </p>
            <button type="button" className={cn(sfButton.primary, 'mt-5')} onClick={clearAll}>
              پاک کردن فیلترها
            </button>
          </div>
        ) : (
          <>
            <ul className="mt-6 grid grid-cols-2 gap-x-4 gap-y-8 sm:gap-x-6 sm:gap-y-10 lg:grid-cols-3">
              {visible.items.map((card) => (
                <li key={card.id}>
                  <ProductCard card={card} />
                </li>
              ))}
            </ul>
            {visible.hasMore ? (
              <div className="mt-12">
                <button
                  type="button"
                  className={sfButton.primary}
                  onClick={() => setPage((current) => current + 1)}
                >
                  نمایش محصولات بیشتر ({formatCountFa(visible.total - visible.items.length)} مورد
                  باقی‌مانده)
                </button>
              </div>
            ) : visible.total > CATALOG_PAGE_SIZE ? (
              <p className="mt-10 text-sf-caption text-sf-ink-muted">
                همهٔ محصولات نمایش داده شد.
              </p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
