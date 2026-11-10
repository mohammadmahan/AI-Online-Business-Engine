import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { productStatus } from '@/db/schema';
import { PRODUCT_STATUSES, PRODUCT_STATUS_LABELS, isProductStatus } from '@/lib/product-status';

/**
 * The panel's browser-safe status mirror must stay identical to the database
 * enum. If a migration adds a lifecycle status, this test fails until the edit
 * form and its badges learn about it.
 */
describe('product status mirror', () => {
  it('matches the database enum exactly', () => {
    assert.deepEqual([...PRODUCT_STATUSES].sort(), [...productStatus.enumValues].sort());
  });

  it('labels every status and refuses anything else', () => {
    for (const status of PRODUCT_STATUSES) {
      assert.equal(typeof PRODUCT_STATUS_LABELS[status], 'string');
      assert.equal(isProductStatus(status), true);
    }
    assert.equal(isProductStatus('SOLD'), false);
    assert.equal(isProductStatus(null), false);
  });
});
