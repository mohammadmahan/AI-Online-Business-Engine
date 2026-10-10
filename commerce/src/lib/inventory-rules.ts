import type { InventoryRow } from '@/server/repository';

/**
 * D-172 §2.2 — inventory display rules, as a PURE module.
 *
 * Shared by the grid (browser) and the service (server) so the badge, the
 * filter chips and the summary counts are all computed from ONE definition and
 * can never disagree with each other.
 */

/** Default low-stock threshold; a per-product override is a later concern. */
export const LOW_STOCK_THRESHOLD = 3;

export type StockFilter = 'all' | 'low' | 'out' | 'inactive';

export interface StockState {
  label: string;
  code: 'IN_STOCK' | 'LOW_STOCK' | 'OUT_OF_STOCK';
  tone: 'success' | 'warning' | 'danger';
}

export function stockState(row: InventoryRow, threshold = LOW_STOCK_THRESHOLD): StockState {
  if (row.stockQuantity <= 0) {
    return { label: 'ناموجود', code: 'OUT_OF_STOCK', tone: 'danger' };
  }
  if (row.stockQuantity <= threshold) {
    return { label: 'موجودی کم', code: 'LOW_STOCK', tone: 'warning' };
  }
  return { label: 'موجود', code: 'IN_STOCK', tone: 'success' };
}

export function isLowStock(row: InventoryRow, threshold = LOW_STOCK_THRESHOLD): boolean {
  return row.stockQuantity > 0 && row.stockQuantity <= threshold;
}

export function filterInventory(
  rows: InventoryRow[],
  filter: StockFilter,
  threshold = LOW_STOCK_THRESHOLD,
): InventoryRow[] {
  switch (filter) {
    case 'low':
      return rows.filter((row) => isLowStock(row, threshold));
    case 'out':
      return rows.filter((row) => row.stockQuantity <= 0);
    case 'inactive':
      return rows.filter((row) => !row.isActive);
    case 'all':
    default:
      return rows;
  }
}

export interface InventorySummary {
  total: number;
  low: number;
  out: number;
  inactive: number;
}

export function inventorySummary(
  rows: InventoryRow[],
  threshold = LOW_STOCK_THRESHOLD,
): InventorySummary {
  return {
    total: rows.length,
    low: rows.filter((row) => isLowStock(row, threshold)).length,
    out: rows.filter((row) => row.stockQuantity <= 0).length,
    inactive: rows.filter((row) => !row.isActive).length,
  };
}

/** The price actually charged for a variant: override when present (D-024). */
export function effectivePrice(row: InventoryRow): number {
  return row.priceOverride ?? row.basePrice;
}

/** Free-text search across the columns a merchant actually scans. */
export function matchesQuery(row: InventoryRow, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (needle.length === 0) {
    return true;
  }
  return [row.productTitle, row.sku, row.size, row.colorName]
    .join(' ')
    .toLowerCase()
    .includes(needle);
}
