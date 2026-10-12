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
} from '@/lib/catalog-filters';
import { formatCountFa, formatToman } from '@/lib/format';
import { CATALOG_SORT_OPTIONS } from '@/lib/storefront-display';
import { buttonClass, inputClass } from '@/components/ui/primitives';
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
 * Filters that match nothing say so and offer a way back, and the paging button
 * reports how many products are left instead of merely being enabled — the two
 * states a customer would otherwise read as a broken page.
 */

const PRICE_STEP = 50_000;

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

  const facets = useMemo(() => deriveFacets(cards), [cards]);
  const ceiling = facets.maxPrice > 0 ? facets.maxPrice : 0;

  // The two sliders hold their own values so a drag stays smooth; only a value
  // that actually narrows the range is written into the filter state.
  const [minSlider, setMinSlider] = useState(0);
  const [maxSlider, setMaxSlider] = useState(ceiling);

  const filtered = useMemo(() => applyFilters(cards, filters), [cards, filters]);
  const visible = paginate(filtered, page, CATALOG_PAGE_SIZE);
  const activeCount = countActiveFilters(filters);

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

  return (
    <div className="mt-6 flex flex-col gap-4 lg:flex-row">
      <form
        aria-label="فیلترهای فهرست محصولات"
        className="flex w-full flex-col gap-4 rounded-[--radius-cp] border border-edge bg-surface p-4 lg:max-w-xs"
        onSubmit={(event) => event.preventDefault()}
      >
        <div className="flex flex-col gap-1">
          <label htmlFor="catalog-search" className="text-cp-label font-medium text-ink">
            جست‌وجو
          </label>
          <input
            id="catalog-search"
            type="search"
            className={inputClass}
            value={filters.query}
            placeholder="نام محصول یا دسته"
            onChange={(event) => update({ query: event.target.value })}
          />
        </div>

        <div className="flex flex-col gap-1">
          <label htmlFor="catalog-sort" className="text-cp-label font-medium text-ink">
            ترتیب نمایش
          </label>
          <select
            id="catalog-sort"
            className={inputClass}
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

        <fieldset className="flex flex-col gap-2">
          <legend className="text-cp-label font-medium text-ink">دسته‌بندی</legend>
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              aria-pressed={filters.category === null}
              className={cn(
                buttonClass.neutral,
                'px-2 text-cp-caption',
                filters.category === null && 'border-primary text-primary',
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
                  buttonClass.neutral,
                  'px-2 text-cp-caption',
                  filters.category === category.name && 'border-primary text-primary',
                )}
                onClick={() => update({ category: category.name })}
              >
                {category.name}{' '}
                <span className="cp-code">{formatCountFa(category.productCount)}</span>
              </button>
            ))}
          </div>
        </fieldset>

        {facets.sizes.length > 0 ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="text-cp-label font-medium text-ink">اندازه</legend>
            <div className="flex flex-wrap gap-2">
              {facets.sizes.map((size) => (
                <button
                  key={size}
                  type="button"
                  aria-pressed={filters.sizes.includes(size)}
                  className={cn(
                    buttonClass.neutral,
                    'px-3 text-cp-caption',
                    filters.sizes.includes(size) && 'border-primary text-primary',
                  )}
                  onClick={() => update({ sizes: toggle(filters.sizes, size) })}
                >
                  <span className="cp-code">{size}</span>
                </button>
              ))}
            </div>
          </fieldset>
        ) : null}

        {facets.colors.length > 0 ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="text-cp-label font-medium text-ink">رنگ</legend>
            <div className="flex flex-wrap gap-2">
              {facets.colors.map((color) => (
                <button
                  key={color.name}
                  type="button"
                  aria-pressed={filters.colors.includes(color.name)}
                  className={cn(
                    buttonClass.neutral,
                    'px-2 text-cp-caption',
                    filters.colors.includes(color.name) && 'border-primary text-primary',
                  )}
                  onClick={() => update({ colors: toggle(filters.colors, color.name) })}
                >
                  <span
                    aria-hidden="true"
                    className="inline-block size-4 rounded-full border border-edge-strong"
                    style={{ backgroundColor: color.hex }}
                  />
                  {color.name}
                </button>
              ))}
            </div>
          </fieldset>
        ) : null}

        {ceiling > 0 ? (
          <fieldset className="flex flex-col gap-2">
            <legend className="text-cp-label font-medium text-ink">محدودهٔ قیمت</legend>
            <label htmlFor="catalog-price-min" className="text-cp-caption text-ink-muted">
              از {formatToman(minSlider)}
            </label>
            <input
              id="catalog-price-min"
              type="range"
              min={0}
              max={ceiling}
              step={PRICE_STEP}
              value={minSlider}
              onChange={(event) => {
                const next = Math.min(Number(event.target.value), maxSlider);
                setMinSlider(next);
                update({ minPrice: next === 0 ? null : next });
              }}
            />
            <label htmlFor="catalog-price-max" className="text-cp-caption text-ink-muted">
              تا {formatToman(maxSlider)}
            </label>
            <input
              id="catalog-price-max"
              type="range"
              min={0}
              max={ceiling}
              step={PRICE_STEP}
              value={maxSlider}
              onChange={(event) => {
                const next = Math.max(Number(event.target.value), minSlider);
                setMaxSlider(next);
                update({ maxPrice: next >= ceiling ? null : next });
              }}
            />
            <p className="text-cp-caption text-ink-muted">
              کم‌ترین و بیش‌ترین قیمت منتشرشده: {formatToman(facets.minPrice)} تا{' '}
              {formatToman(facets.maxPrice)}
            </p>
          </fieldset>
        ) : null}

        <label className="flex items-center gap-2 text-cp-label text-ink">
          <input
            type="checkbox"
            checked={filters.onlyAvailable}
            onChange={(event) => update({ onlyAvailable: event.target.checked })}
          />
          فقط کالاهای موجود
        </label>

        <p className="flex flex-wrap items-center gap-2 text-cp-caption text-ink-muted">
          <span>
            فیلترهای فعال: <span className="cp-code">{formatCountFa(activeCount)}</span>
          </span>
          {activeCount > 0 ? (
            <button type="button" className={buttonClass.neutral} onClick={clearAll}>
              پاک کردن فیلترها
            </button>
          ) : null}
        </p>
      </form>

      <div className="flex-1">
        <p role="status" className="text-cp-label text-ink-muted">
          {visible.total === 0
            ? 'محصولی با این فیلترها پیدا نشد.'
            : `${formatCountFa(visible.total)} محصول، نمایش ${formatCountFa(visible.items.length)} مورد`}
        </p>

        {visible.items.length === 0 ? (
          <div className="mt-4 flex flex-col items-start gap-3 rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-4">
            <p className="text-cp-label text-ink-muted">
              هیچ محصولی با این ترکیب فیلترها مطابقت ندارد. یکی از فیلترها را بردارید یا همه را پاک
              کنید.
            </p>
            <button type="button" className={buttonClass.primary} onClick={clearAll}>
              پاک کردن فیلترها
            </button>
          </div>
        ) : (
          <>
            <ul className="mt-4 grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {visible.items.map((card) => (
                <li key={card.id}>
                  <ProductCard card={card} />
                </li>
              ))}
            </ul>
            {visible.hasMore ? (
              <div className="mt-6">
                <button
                  type="button"
                  className={buttonClass.primary}
                  onClick={() => setPage((current) => current + 1)}
                >
                  نمایش محصولات بیشتر (
                  {formatCountFa(visible.total - visible.items.length)} مورد باقی‌مانده)
                </button>
              </div>
            ) : visible.total > CATALOG_PAGE_SIZE ? (
              <p className="mt-6 text-cp-caption text-ink-muted">همهٔ محصولات نمایش داده شد.</p>
            ) : null}
          </>
        )}
      </div>
    </div>
  );
}
