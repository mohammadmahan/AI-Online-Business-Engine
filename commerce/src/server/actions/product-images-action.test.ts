import assert from 'node:assert/strict';
import { describe, it } from 'node:test';

import { updateProductImagesAction } from '@/server/actions/products';

/**
 * D-172 Phase 4 / §2.1 — the gallery write is an ADMIN write.
 *
 * The proxy already refuses `/admin/**`, but a Server Action has its own entry
 * point: its id is a global URL, and the path rule describes the PAGE a request
 * came from, not the repository operation a POST performs. So the action checks
 * the session itself (`withAdminRepository`), and this test drives the action
 * with NO request scope — which is exactly what an unauthenticated caller looks
 * like (`getAdminSession` answers `null` when there is no cookie jar).
 *
 * The refusal must come BEFORE anything is validated or written: no repository
 * is reached, so the answer cannot depend on the payload, the database or the
 * media provider.
 */

describe('updateProductImagesAction — anonymous write denial', () => {
  it('refuses with UNAUTHORIZED and an operator-facing message', async () => {
    const result = await updateProductImagesAction({
      productId: '00000000-0000-4000-8000-000000000000',
      images: [],
    });
    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'UNAUTHORIZED');
    assert.match(result.message, /ورود|دسترسی|مدیر/);
  });

  it('refuses before payload validation, so a malformed body reveals nothing', async () => {
    const result = await updateProductImagesAction({
      productId: 'not-a-uuid',
      images: [{ storagePath: '../etc/passwd', publicUrl: 'https://evil.example/x.jpg' }],
    });
    assert.equal(result.ok, false);
    if (result.ok) return;
    assert.equal(result.code, 'UNAUTHORIZED');
  });
});
