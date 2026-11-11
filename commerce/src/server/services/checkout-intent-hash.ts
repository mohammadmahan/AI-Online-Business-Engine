import { createHash } from 'node:crypto';

import {
  checkoutIntentFingerprint,
  type CheckoutIntent,
} from '@/lib/checkout-idempotency';

/**
 * Binds an idempotency key to the exact checkout intent that used it.
 *
 * The canonical JSON comes from the same client-safe function that decides when
 * the browser rotates its key, so the payload the browser intended and the
 * payload the server stores cannot drift apart. Only the digest is persisted:
 * the order needs an equality check, not a second copy of customer PII.
 */
export function checkoutIntentHash(intent: CheckoutIntent): string {
  return createHash('sha256').update(checkoutIntentFingerprint(intent)).digest('hex');
}
