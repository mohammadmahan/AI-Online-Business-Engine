import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { validProductPayload } from '@/lib/validation.fixtures';
import { effectivePrice } from '@/lib/inventory-rules';
import { createMemoryRepository } from '@/server/repository-memory';
import type { InventoryRow } from '@/server/repository';
import { createProduct } from '@/server/services/products';
import { updatePrice, updateStock } from '@/server/services/inventory';

/**
 * D-172 §2.2 — the two inline writes. Every value is validated on the SERVER as
 * well, because the input control in the browser is a convenience and the
 * refusal is the guarantee.
 */

async function seeded(): Promise<{ repository: ReturnType<typeof createMemoryRepository>; rows: InventoryRow[] }> {
  const repository = createMemoryRepository();
  const created = await createProduct(repository, validProductPayload());
  assert.equal(created.ok, true);
  return { repository, rows: await repository.listInventory() };
}

describe('inventory service — stock (§2.2)', () => {
  it('stores a valid quantity and the grid reads it back', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);

    const result = await updateStock(repository, target.variantId, 42);

    assert.deepEqual(result, { ok: true, variantId: target.variantId });
    const after = await repository.listInventory();
    assert.equal(after.find((row) => row.variantId === target.variantId)?.stockQuantity, 42);
  });

  it('accepts zero — "sold out" is a state, not an error', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);

    const result = await updateStock(repository, target.variantId, 0);

    assert.equal(result.ok, true);
    const after = await repository.listInventory();
    assert.equal(after.find((row) => row.variantId === target.variantId)?.stockQuantity, 0);
  });

  it('refuses a negative, fractional, NaN or non-numeric quantity and keeps the stored value', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);
    const before = target.stockQuantity;

    for (const bad of [-1, 2.5, Number.NaN, '5', null, undefined]) {
      const result = await updateStock(repository, target.variantId, bad);
      assert.equal(result.ok, false);
      assert.ok(!result.ok && result.code === 'VALIDATION_ERROR');
    }

    const after = await repository.listInventory();
    assert.equal(after.find((row) => row.variantId === target.variantId)?.stockQuantity, before);
  });

  it('reports a missing variant instead of silently succeeding', async () => {
    const { repository } = await seeded();

    const result = await updateStock(repository, 'variant-does-not-exist', 3);

    assert.equal(result.ok, false);
    assert.ok(!result.ok && result.code === 'NOT_FOUND');
  });
});

describe('inventory service — price override (§2.2)', () => {
  it('sets an override and the effective price follows it (D-024)', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);

    const result = await updatePrice(repository, target.variantId, 990_000);

    assert.equal(result.ok, true);
    const after = await repository.listInventory();
    const updated = after.find((row) => row.variantId === target.variantId);
    assert.ok(updated);
    assert.equal(updated.priceOverride, 990_000);
    assert.equal(effectivePrice(updated), 990_000);
    assert.equal(updated.basePrice, 1_250_000);
  });

  it('clears the override with null so the base price applies again', async () => {
    const { repository, rows } = await seeded();
    const overridden = rows.find((row) => row.priceOverride !== null);
    assert.ok(overridden);

    const result = await updatePrice(repository, overridden.variantId, null);

    assert.equal(result.ok, true);
    const after = await repository.listInventory();
    const updated = after.find((row) => row.variantId === overridden.variantId);
    assert.ok(updated);
    assert.equal(updated.priceOverride, null);
    assert.equal(effectivePrice(updated), updated.basePrice);
  });

  it('refuses a fractional, negative or absent value', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);

    for (const bad of [0.5, -1, Number.NaN, undefined, '990000']) {
      const result = await updatePrice(repository, target.variantId, bad);
      assert.equal(result.ok, false);
      assert.ok(!result.ok && result.code === 'VALIDATION_ERROR');
    }
  });

  it('reports a missing variant instead of silently succeeding', async () => {
    const { repository } = await seeded();

    const result = await updatePrice(repository, 'variant-does-not-exist', 100_000);

    assert.equal(result.ok, false);
    assert.ok(!result.ok && result.code === 'NOT_FOUND');
  });
});
