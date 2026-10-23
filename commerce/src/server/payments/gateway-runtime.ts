import { getRepository } from '../db-context';

import { createRepositoryPaymentAuthorizationStore } from './authority-store';
import type { PaymentGateway } from './gateway';
import { createZarinPalGatewayFromEnv } from './zarinpal';

/**
 * D-172 §6.1 — the gateway the APPLICATION wires.
 *
 * One construction site for the production adapter, so the checkout action and
 * the browser-return route can never end up on two different gateways (a
 * callback verified by an adapter the checkout never used is exactly the bug
 * this file makes impossible).
 *
 * Constructed PER CALL on purpose: `createZarinPalGatewayFromEnv` reads the
 * `ZARINPAL_*` variables at call time (D-045), and a cached object would freeze
 * a configuration that is unset today. Nothing is opened here — the store
 * resolves the repository only when a payment is actually requested or verified.
 *
 * Fail-closed, exactly like the mock it replaces: with no merchant id or
 * callback URL the adapter refuses every payment (`UNAVAILABLE`) and the order
 * stays `PENDING`, so an unconfigured deployment still cannot charge and never
 * reports a faked success (D-171 §2.2, AC-8).
 */
export function getPaymentGateway(): PaymentGateway {
  return createZarinPalGatewayFromEnv({
    store: createRepositoryPaymentAuthorizationStore(getRepository),
  });
}
