import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { validProductPayload } from '@/lib/validation.fixtures';
import { effectivePrice, stockState } from '@/lib/inventory-rules';
import { MAX_MONEY_TOMAN } from '@/lib/validation';
import { createMemoryRepository } from '@/server/repository-memory';
import type { InventoryRow } from '@/server/repository';
import { createProduct } from '@/server/services/products';
import { updatePrice, updateStock } from '@/server/services/inventory';

/**
 * D-172 §2.2 — the two inline writes. Every value is validated on the SERVER as
 * well, because the input control in the browser is a convenience and the
 * refusal is the guarantee.
 */

/** A well-formed id that belongs to no row: absent, not malformed. */
const MISSING_VARIANT_ID = '00000000-0000-4000-8000-000000000000';

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

    const result = await updateStock(repository, MISSING_VARIANT_ID, 3);

    assert.equal(result.ok, false);
    assert.ok(!result.ok && result.code === 'NOT_FOUND');
  });

  it('refuses a malformed variant id before it reaches the repository', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);

    for (const badId of ['', '   ', 'variant-does-not-exist', '123', target.variantId.slice(0, -1)]) {
      const result = await updateStock(repository, badId, 5);
      assert.equal(result.ok, false, `id ${JSON.stringify(badId)} must be refused`);
      assert.ok(!result.ok && result.code === 'VALIDATION_ERROR');
      assert.equal(!result.ok ? result.issues?.[0]?.field : undefined, 'variantId');
    }

    // Nothing was written while the ids were being refused.
    const after = await repository.listInventory();
    assert.equal(
      after.find((row) => row.variantId === target.variantId)?.stockQuantity,
      target.stockQuantity,
    );
  });

  it('accepts the stock ceiling exactly and refuses one above it', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);

    assert.equal((await updateStock(repository, target.variantId, 1_000_000)).ok, true);

    const tooMuch = await updateStock(repository, target.variantId, 1_000_001);
    assert.equal(tooMuch.ok, false);
    assert.ok(!tooMuch.ok && tooMuch.code === 'VALIDATION_ERROR');

    const after = await repository.listInventory();
    assert.equal(after.find((row) => row.variantId === target.variantId)?.stockQuantity, 1_000_000);
  });

  it('is idempotent — re-sending the same quantity succeeds and changes nothing', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);

    for (let attempt = 0; attempt < 3; attempt += 1) {
      assert.deepEqual(await updateStock(repository, target.variantId, 7), {
        ok: true,
        variantId: target.variantId,
      });
    }

    const after = await repository.listInventory();
    assert.equal(after.find((row) => row.variantId === target.variantId)?.stockQuantity, 7);
  });

  it('moves the row across the low-stock badge boundaries', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);

    const readBack = async () => {
      const row = (await repository.listInventory()).find(
        (entry) => entry.variantId === target.variantId,
      );
      assert.ok(row);
      return row;
    };

    await updateStock(repository, target.variantId, 3);
    assert.equal(stockState(await readBack()).code, 'LOW_STOCK');

    await updateStock(repository, target.variantId, 4);
    assert.equal(stockState(await readBack()).code, 'IN_STOCK');

    await updateStock(repository, target.variantId, 0);
    assert.equal(stockState(await readBack()).code, 'OUT_OF_STOCK');
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

    const result = await updatePrice(repository, MISSING_VARIANT_ID, 100_000);

    assert.equal(result.ok, false);
    assert.ok(!result.ok && result.code === 'NOT_FOUND');
  });

  it('refuses a malformed variant id before it reaches the repository', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);

    for (const badId of ['', 'not-a-uuid', '123', target.variantId.slice(0, -1)]) {
      const result = await updatePrice(repository, badId, 500_000);
      assert.equal(result.ok, false, `id ${JSON.stringify(badId)} must be refused`);
      assert.ok(!result.ok && result.code === 'VALIDATION_ERROR');
      assert.equal(!result.ok ? result.issues?.[0]?.field : undefined, 'variantId');
    }

    const after = await repository.listInventory();
    assert.equal(
      after.find((row) => row.variantId === target.variantId)?.priceOverride,
      target.priceOverride,
    );
  });

  it('accepts zero and the money ceiling, and refuses one Toman above it', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);

    assert.equal((await updatePrice(repository, target.variantId, 0)).ok, true);
    assert.equal((await updatePrice(repository, target.variantId, MAX_MONEY_TOMAN)).ok, true);

    const tooMuch = await updatePrice(repository, target.variantId, MAX_MONEY_TOMAN + 1);
    assert.equal(tooMuch.ok, false);
    assert.ok(!tooMuch.ok && tooMuch.code === 'VALIDATION_ERROR');

    const after = await repository.listInventory();
    assert.equal(
      after.find((row) => row.variantId === target.variantId)?.priceOverride,
      MAX_MONEY_TOMAN,
    );
  });

  it('is idempotent for the same override and keeps it stored', async () => {
    const { repository, rows } = await seeded();
    const target = rows[0];
    assert.ok(target);

    for (let attempt = 0; attempt < 3; attempt += 1) {
      assert.deepEqual(await updatePrice(repository, target.variantId, 880_000), {
        ok: true,
        variantId: target.variantId,
      });
    }

    const after = await repository.listInventory();
    const updated = after.find((row) => row.variantId === target.variantId);
    assert.ok(updated);
    assert.equal(updated.priceOverride, 880_000);
    assert.equal(effectivePrice(updated), 880_000);
  });
});
