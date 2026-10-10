import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import {
  LOW_STOCK_THRESHOLD,
  effectivePrice,
  filterInventory,
  inventorySummary,
  isLowStock,
  matchesQuery,
  stockState,
} from '@/lib/inventory-rules';
import type { InventoryRow } from '@/server/repository';

/** D-172 §2.2 — the badge, the filters and the summary read ONE definition. */

function row(overrides: Partial<InventoryRow> = {}): InventoryRow {
  return {
    variantId: 'var-1',
    productId: 'prod-1',
    productTitle: 'مانتو کتی لنین',
    productSlug: 'manto-keti-lenin',
    sku: 'MANTO-KETI-36-1',
    size: '36',
    colorName: 'مشکی',
    colorHex: '#111111',
    stockQuantity: 10,
    priceOverride: null,
    basePrice: 1_250_000,
    isActive: true,
    ...overrides,
  };
}

describe('inventory rules (§2.2)', () => {
  it('classifies stock at the threshold boundaries', () => {
    assert.equal(stockState(row({ stockQuantity: 0 })).code, 'OUT_OF_STOCK');
    assert.equal(stockState(row({ stockQuantity: 1 })).code, 'LOW_STOCK');
    assert.equal(stockState(row({ stockQuantity: LOW_STOCK_THRESHOLD })).code, 'LOW_STOCK');
    assert.equal(stockState(row({ stockQuantity: LOW_STOCK_THRESHOLD + 1 })).code, 'IN_STOCK');
    assert.equal(stockState(row({ stockQuantity: -3 })).code, 'OUT_OF_STOCK');
  });

  it('honours a configurable threshold', () => {
    assert.equal(isLowStock(row({ stockQuantity: 5 }), 5), true);
    assert.equal(stockState(row({ stockQuantity: 5 }), 5).code, 'LOW_STOCK');
    assert.equal(stockState(row({ stockQuantity: 6 }), 5).code, 'IN_STOCK');
  });

  it('keeps zero stock out of the low-stock bucket', () => {
    assert.equal(isLowStock(row({ stockQuantity: 0 })), false);
    assert.equal(stockState(row({ stockQuantity: 0 })).label, 'ناموجود');
  });

  it('carries a non-colour status code beside every label', () => {
    const state = stockState(row({ stockQuantity: 2 }));
    assert.equal(state.label, 'موجودی کم');
    assert.equal(state.code, 'LOW_STOCK');
    assert.equal(state.tone, 'warning');
  });

  it('filters by low / out / inactive and passes everything through for "all"', () => {
    const rows = [
      row({ variantId: 'a', stockQuantity: 0 }),
      row({ variantId: 'b', stockQuantity: 2 }),
      row({ variantId: 'c', stockQuantity: 9 }),
      row({ variantId: 'd', stockQuantity: 9, isActive: false }),
    ];
    assert.deepEqual(
      filterInventory(rows, 'all').map((entry) => entry.variantId),
      ['a', 'b', 'c', 'd'],
    );
    assert.deepEqual(
      filterInventory(rows, 'low').map((entry) => entry.variantId),
      ['b'],
    );
    assert.deepEqual(
      filterInventory(rows, 'out').map((entry) => entry.variantId),
      ['a'],
    );
    assert.deepEqual(
      filterInventory(rows, 'inactive').map((entry) => entry.variantId),
      ['d'],
    );
  });

  it('summarises the same counts the chips display', () => {
    const rows = [
      row({ variantId: 'a', stockQuantity: 0 }),
      row({ variantId: 'b', stockQuantity: 2 }),
      row({ variantId: 'c', stockQuantity: 9 }),
      row({ variantId: 'd', stockQuantity: 9, isActive: false }),
    ];
    assert.deepEqual(inventorySummary(rows), { total: 4, low: 1, out: 1, inactive: 1 });
  });

  it('charges the override when there is one and the base price otherwise (D-024)', () => {
    assert.equal(effectivePrice(row()), 1_250_000);
    assert.equal(effectivePrice(row({ priceOverride: 990_000 })), 990_000);
    assert.equal(effectivePrice(row({ priceOverride: 0 })), 0);
  });

  it('searches the columns a merchant actually scans', () => {
    const entry = row();
    assert.equal(matchesQuery(entry, ''), true);
    assert.equal(matchesQuery(entry, '  '), true);
    assert.equal(matchesQuery(entry, 'manto'), true);
    assert.equal(matchesQuery(entry, 'MANTO-KETI-36-1'), true);
    assert.equal(matchesQuery(entry, 'مشکی'), true);
    assert.equal(matchesQuery(entry, 'شومیز'), false);
  });
});
