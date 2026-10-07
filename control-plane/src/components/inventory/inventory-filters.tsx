'use client';

import { Filter, ListFilter, X } from 'lucide-react';
import { useState } from 'react';

import { STOCK_CATEGORY_META, SYNC_STATUS_META } from '@/components/inventory/inventory-meta';
import { cn } from '@/lib/utils';
import type { InventoryItem, StockCategory, SyncStatus } from '@/types/inventory';

const SYNC_STATUSES: SyncStatus[] = [
  'IN_SYNC',
  'PENDING_SYNC',
  'SYNC_ERROR',
  'DRIFT_DETECTED',
];
const STOCK_CATEGORIES: StockCategory[] = ['IN_STOCK', 'LOW_STOCK', 'OUT_OF_STOCK'];

/** Filters are a client concern: they never change what the server rendered. */
export interface InventoryFilterState {
  /** Free-text query matched against SKU and the Persian product name. */
  query: string;
  syncStatuses: SyncStatus[];
  stockCategories: StockCategory[];
  /** Raw input strings — parsed strictly, so "abc" is never read as zero. */
  priceMin: string;
  priceMax: string;
}

export const EMPTY_INVENTORY_FILTERS: InventoryFilterState = {
  query: '',
  syncStatuses: [],
  stockCategories: [],
  priceMin: '',
  priceMax: '',
};

const TOMAN_INPUT_RE = /^[0-9]+$/;

/**
 * Parse the price range inputs.
 *
 * A non-numeric or inverted range is reported as `invalid` instead of being
 * silently ignored: applying "no filter" to a range the operator typed would
 * show results that look like they matched it (fail-closed, D-171 §2.2).
 */
export function parsePriceRange(filters: InventoryFilterState): {
  min: number | null;
  max: number | null;
  invalid: boolean;
} {
  const minRaw = filters.priceMin.trim();
  const maxRaw = filters.priceMax.trim();
  const badMin = minRaw !== '' && !TOMAN_INPUT_RE.test(minRaw);
  const badMax = maxRaw !== '' && !TOMAN_INPUT_RE.test(maxRaw);
  const min = minRaw === '' || badMin ? null : Number.parseInt(minRaw, 10);
  const max = maxRaw === '' || badMax ? null : Number.parseInt(maxRaw, 10);
  const invalid = badMin || badMax || (min !== null && max !== null && min > max);
  return { min, max, invalid };
}

/** Apply the filter state to a row list. An invalid range yields no rows. */
export function applyInventoryFilters(
  items: InventoryItem[],
  filters: InventoryFilterState,
): InventoryItem[] {
  const { min, max, invalid } = parsePriceRange(filters);
  if (invalid) return [];

  const needle = filters.query.trim().toLowerCase();
  return items.filter((item) => {
    if (filters.syncStatuses.length > 0 && !filters.syncStatuses.includes(item.sync.status)) {
      return false;
    }
    if (
      filters.stockCategories.length > 0 &&
      !filters.stockCategories.includes(item.stockCategory)
    ) {
      return false;
    }
    if (min !== null && item.price_toman < min) return false;
    if (max !== null && item.price_toman > max) return false;
    if (needle.length > 0) {
      const haystack = [item.sku, item.nameFa].join(' ').toLowerCase();
      if (!haystack.includes(needle)) return false;
    }
    return true;
  });
}

/**
 * Search & filters (D-171 §5.3): SKU/title search, sync status, stock category
 * and price range.
 *
 * Filtering is purely presentational: it cannot sync, lock or edit anything.
 * The active-filter count and the shown/total count are stated in words as well
 * as visually, so the operator always knows what is hidden.
 */
export function InventoryFilters({
  filters,
  onChange,
  shown,
  total,
}: {
  filters: InventoryFilterState;
  onChange: (next: InventoryFilterState) => void;
  shown: number;
  total: number;
}) {
  const [open, setOpen] = useState(false);

  const activeCount =
    filters.syncStatuses.length +
    filters.stockCategories.length +
    (filters.query.trim() ? 1 : 0) +
    (filters.priceMin.trim() || filters.priceMax.trim() ? 1 : 0);

  const price = parsePriceRange(filters);

  const toggleSync = (status: SyncStatus) => {
    const next = filters.syncStatuses.includes(status)
      ? filters.syncStatuses.filter((value) => value !== status)
      : [...filters.syncStatuses, status];
    onChange({ ...filters, syncStatuses: next });
  };

  const toggleStock = (category: StockCategory) => {
    const next = filters.stockCategories.includes(category)
      ? filters.stockCategories.filter((value) => value !== category)
      : [...filters.stockCategories, category];
    onChange({ ...filters, stockCategories: next });
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls="inventory-filter-panel"
          className={cn(
            'cp-target inline-flex items-center gap-2 rounded-[--radius-cp]',
            'border border-edge-strong bg-surface px-3 py-2',
            'text-cp-label font-medium text-ink hover:bg-surface-muted',
          )}
        >
          <Filter aria-hidden="true" className="size-4" />
          فیلترها
          {activeCount > 0 ? (
            <span className="rounded-full bg-primary px-2 text-cp-caption font-semibold text-on-primary tabular-nums">
              {activeCount}
            </span>
          ) : null}
        </button>

        <label className="flex items-center gap-2">
          <span className="sr-only">جست‌وجو بر اساس SKU یا نام محصول</span>
          <input
            type="search"
            value={filters.query}
            onChange={(event) => onChange({ ...filters, query: event.target.value })}
            placeholder="جست‌وجو در SKU یا نام محصول…"
            className={cn(
              'cp-target w-64 max-w-full rounded-[--radius-cp] border border-edge-strong',
              'bg-surface px-3 py-2 text-cp-label text-ink placeholder:text-ink-muted',
            )}
          />
        </label>

        <p className="text-cp-caption text-ink-muted" role="status">
          نمایش <span className="tabular-nums">{shown}</span> از{' '}
          <span className="tabular-nums">{total}</span> SKU
        </p>

        {activeCount > 0 ? (
          <button
            type="button"
            onClick={() => onChange(EMPTY_INVENTORY_FILTERS)}
            className="cp-target inline-flex items-center gap-1 rounded-[--radius-cp] px-2 py-1 text-cp-caption font-medium text-primary hover:underline"
          >
            <X aria-hidden="true" className="size-4" />
            پاک‌کردن فیلترها
          </button>
        ) : null}
      </div>

      {open ? (
        <div
          id="inventory-filter-panel"
          className="flex flex-col gap-4 rounded-[--radius-cp] border border-edge bg-surface-muted p-3"
        >
          <fieldset className="flex flex-col gap-2">
            <legend className="flex items-center gap-2 text-cp-label font-semibold text-ink">
              <ListFilter aria-hidden="true" className="size-4" />
              وضعیت همگام‌سازی
            </legend>
            <div className="flex flex-wrap gap-2">
              {SYNC_STATUSES.map((status) => {
                const meta = SYNC_STATUS_META[status];
                const active = filters.syncStatuses.includes(status);
                return (
                  <button
                    key={status}
                    type="button"
                    onClick={() => toggleSync(status)}
                    aria-pressed={active}
                    className={cn(
                      'cp-target rounded-full border px-3 py-1 text-cp-caption font-medium',
                      active
                        ? 'border-primary bg-primary text-on-primary'
                        : 'border-edge-strong bg-surface text-ink hover:bg-surface-muted',
                    )}
                  >
                    {meta.label} ({meta.code})
                  </button>
                );
              })}
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-cp-label font-semibold text-ink">وضعیت موجودی</legend>
            <div className="flex flex-wrap gap-2">
              {STOCK_CATEGORIES.map((category) => {
                const meta = STOCK_CATEGORY_META[category];
                const active = filters.stockCategories.includes(category);
                return (
                  <button
                    key={category}
                    type="button"
                    onClick={() => toggleStock(category)}
                    aria-pressed={active}
                    className={cn(
                      'cp-target rounded-full border px-3 py-1 text-cp-caption font-medium',
                      active
                        ? 'border-primary bg-primary text-on-primary'
                        : 'border-edge-strong bg-surface text-ink hover:bg-surface-muted',
                    )}
                  >
                    {meta.label} ({meta.code})
                  </button>
                );
              })}
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-cp-label font-semibold text-ink">
              بازهٔ قیمت (تومان)
            </legend>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-cp-caption text-ink-muted">از</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  step={1}
                  value={filters.priceMin}
                  onChange={(event) => onChange({ ...filters, priceMin: event.target.value })}
                  className={cn(
                    'cp-target w-36 rounded-[--radius-cp] border border-edge-strong',
                    'bg-surface px-3 py-2 text-cp-label text-ink tabular-nums',
                  )}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-cp-caption text-ink-muted">تا</span>
                <input
                  type="number"
                  inputMode="numeric"
                  min={0}
                  step={1}
                  value={filters.priceMax}
                  onChange={(event) => onChange({ ...filters, priceMax: event.target.value })}
                  className={cn(
                    'cp-target w-36 rounded-[--radius-cp] border border-edge-strong',
                    'bg-surface px-3 py-2 text-cp-label text-ink tabular-nums',
                  )}
                />
              </label>
            </div>
            {price.invalid ? (
              <p
                role="alert"
                className="rounded-[--radius-cp] border border-danger bg-surface p-2 text-cp-caption text-danger"
              >
                بازهٔ قیمت نامعتبر است (ورودی غیرعددی یا حد پایین بزرگ‌تر از حد بالا)؛ تا اصلاح
                آن هیچ SKUی نمایش داده نمی‌شود.
              </p>
            ) : null}
          </fieldset>
        </div>
      ) : null}
    </div>
  );
}
