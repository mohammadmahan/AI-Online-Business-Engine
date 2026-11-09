import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { normalizeImageSelection, orderedSlotKeys } from '@/lib/product-images';

/**
 * D-172 §2.1 — the pure gallery-edit rules.
 *
 * These tests are negative-first on purpose: the dangerous cases are the ones
 * that would let a submission mean two things at once (an existing row AND a new
 * reference), show one photo twice, or leave a gallery with two primaries.
 */

describe('normalizeImageSelection — the two slot forms', () => {
  it('splits existing rows (by id) from new references (by path + url)', () => {
    const result = normalizeImageSelection([
      { id: 'row-1', isPrimary: true },
      { storagePath: 'products/sha256/aa/a.jpg', publicUrl: '/media/products/sha256/aa/a.jpg' },
    ]);
    assert.equal(result.ok, true);
    if (!result.ok) return;
    assert.deepEqual(result.selection.keep, [{ id: 'row-1', displayOrder: 0, isPrimary: true }]);
    assert.deepEqual(result.selection.add, [
      {
        storagePath: 'products/sha256/aa/a.jpg',
        publicUrl: '/media/products/sha256/aa/a.jpg',
        displayOrder: 1,
        isPrimary: false,
      },
    ]);
  });

  it('refuses a slot that claims both forms at once', () => {
    const result = normalizeImageSelection([
      { id: 'row-1', storagePath: 'products/sha256/aa/a.jpg', publicUrl: '/media/x.jpg' },
    ]);
    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.field, 'images.0');
  });

  it('refuses a new reference with only half of the pair', () => {
    for (const entry of [
      { storagePath: 'products/sha256/aa/a.jpg' },
      { publicUrl: '/media/products/sha256/aa/a.jpg' },
      {},
    ]) {
      const result = normalizeImageSelection([entry]);
      assert.equal(result.ok, false);
    }
  });
});

describe('normalizeImageSelection — ordering, primary and duplicates', () => {
  it('uses array position as display order for both kinds', () => {
    const result = normalizeImageSelection([
      { id: 'row-2' },
      { id: 'row-1' },
      { storagePath: 'products/sha256/aa/a.jpg', publicUrl: '/media/products/sha256/aa/a.jpg' },
    ]);
    assert.equal(result.ok, true);
    if (!result.ok) return;
    assert.deepEqual(orderedSlotKeys(result.selection), [
      'id:row-2',
      'id:row-1',
      'path:products/sha256/aa/a.jpg',
    ]);
    assert.deepEqual(
      result.selection.keep.map((entry) => entry.displayOrder),
      [0, 1],
    );
  });

  it('defaults the first slot to primary when none is flagged', () => {
    const result = normalizeImageSelection([{ id: 'row-2' }, { id: 'row-1' }]);
    assert.equal(result.ok, true);
    if (!result.ok) return;
    assert.deepEqual(
      result.selection.keep.map((entry) => entry.isPrimary),
      [true, false],
    );
  });

  it('moves the primary flag to whichever slot carries it', () => {
    const result = normalizeImageSelection([{ id: 'a' }, { id: 'b', isPrimary: true }, { id: 'c' }]);
    assert.equal(result.ok, true);
    if (!result.ok) return;
    assert.deepEqual(
      result.selection.keep.map((entry) => entry.isPrimary),
      [false, true, false],
    );
  });

  it('refuses two primaries', () => {
    const result = normalizeImageSelection([{ id: 'a', isPrimary: true }, { id: 'b', isPrimary: true }]);
    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.field, 'images');
  });

  it('refuses the same existing row twice and the same stored object twice', () => {
    const duplicateId = normalizeImageSelection([{ id: 'a' }, { id: 'a' }]);
    assert.equal(duplicateId.ok, false);

    const duplicatePath = normalizeImageSelection([
      { storagePath: 'products/sha256/aa/a.jpg', publicUrl: '/media/products/sha256/aa/a.jpg' },
      { storagePath: 'products/sha256/aa/a.jpg', publicUrl: '/media/products/sha256/aa/a.jpg' },
    ]);
    assert.equal(duplicatePath.ok, false);
  });

  it('accepts an empty gallery (every association removed)', () => {
    const result = normalizeImageSelection([]);
    assert.equal(result.ok, true);
    if (!result.ok) return;
    assert.deepEqual(result.selection, { keep: [], add: [] });
  });
});
