import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import type { ProductUpdatePayload } from '@/contracts/catalog';
import { updateProductAction } from '@/server/actions/products';

/**
 * D-172 §2.1 — editing a product is an ADMIN write.
 *
 * The proxy guards `/admin/**`, but a Server Action has its own global entry
 * point, so the action checks the session itself. With no request scope the
 * session is `null` — exactly what an unauthenticated POST looks like — and the
 * refusal must happen before the payload, the repository or the database is
 * consulted.
 */

const payload: ProductUpdatePayload = {
  categoryId: 'cat-1',
  title: 'عنوان تازه',
  slug: 'manto-keti-lenin',
  basePrice: 1_000_000,
  discountPrice: null,
  descriptionRaw: 'توضیح',
  fabricType: 'لنین',
  season: 'بهاره',
  careInstructions: null,
  status: 'DRAFT',
};

describe('updateProductAction — anonymous write denial', () => {
  it('refuses with UNAUTHORIZED and an operator-facing message', async () => {
    const result = await updateProductAction({
      productId: '00000000-0000-4000-8000-000000000000',
      product: payload,
    });
    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'UNAUTHORIZED');
    assert.match(result.message, /ورود|دسترسی|مدیر/);
  });

  it('refuses a malformed body before validating it', async () => {
    const result = await updateProductAction({
      productId: 'not-a-uuid',
      product: null as unknown as ProductUpdatePayload,
    });
    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'UNAUTHORIZED');
  });
});
