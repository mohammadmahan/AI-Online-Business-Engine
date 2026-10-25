import { getRepository } from '../db-context';

import { createRepositoryPaymentAuthorizationStore } from './authority-store';
import { createMockPaymentGateway, type PaymentGateway } from './gateway';
import { createZarinPalGatewayFromEnv } from './zarinpal';

/**
 * D-172 §6.1 — the gateway the APPLICATION wires.
 *
 * One construction site for the production adapter, so the checkout action and
 * the browser-return route can never end up on two different gateways (a
 * callback verified by an adapter the checkout never used is exactly the bug
 * this file makes impossible).
 *
 * Constructed PER CALL on purpose: selection reads the environment at call time
 * (D-045), and a cached object would freeze a configuration that is unset today.
 * Nothing is opened here — the store resolves the repository only when a payment
 * is actually requested or verified.
 *
 * Two modes, and exactly one of them is a demo:
 *
 *   - `PAYMENT_MODE=mock` (case-insensitive) selects the mock adapter with an
 *     `AUTHORIZED` outcome, so a checkout completes WITHOUT any external call.
 *     It is NOT confirmation: `placeCheckoutOrder` records the `MOCK-` prefixed
 *     reference and the order stays `PENDING`. The returned `redirectUrl`
 *     points at `/api/payments/mock/callback`, which — only under this same
 *     mode — runs the SAME `applyPaymentCallback` transition a real provider
 *     return uses. Two steps, one write path, no faked status.
 *   - everything else — unset, `zarinpal`, or an unrecognised value — selects
 *     the ZarinPal adapter, exactly as before. With no merchant id or callback
 *     URL it refuses every payment (`UNAVAILABLE`) and the order stays
 *     `PENDING`, so an unconfigured deployment still cannot charge and never
 *     reports a faked success (D-171 §2.2, AC-8).
 *
 * An unrecognised value deliberately falls through to ZarinPal rather than to
 * the mock: a typo must never be the reason a deployment accepts fake
 * authorisations.
 *
 * PRODUCTION REFUSES THE DEMO. `NODE_ENV=production` (what `next build` /
 * `next start` set) disables mock selection entirely, whatever `PAYMENT_MODE`
 * says, because production in this track means live money behind the D-139
 * activation gate (AC-8, §6.3 NO-GO). The demo exists for local development;
 * a production build answers ZarinPal, which still refuses without credentials.
 */

/** The one variable that can select the demo adapter. */
export const PAYMENT_MODE_ENV = 'PAYMENT_MODE';

/** The only value that selects the mock; anything else keeps ZarinPal. */
export const MOCK_PAYMENT_MODE = 'mock';

/** The build mode in which the demo adapter is refused outright. */
export const PRODUCTION_NODE_ENV = 'production';

/**
 * Where a demo checkout sends the browser after an authorised mock attempt.
 * The route behind it refuses unless the mode is `mock`, so this template is
 * an address, not an authorization.
 */
export const MOCK_CALLBACK_URL_TEMPLATE =
  '/api/payments/mock/callback?reference={reference}';

export function isProductionConfig(
  env: Readonly<Record<string, string | undefined>> = process.env,
): boolean {
  return (env.NODE_ENV ?? '').trim().toLowerCase() === PRODUCTION_NODE_ENV;
}

export function getPaymentGateway(
  env: Readonly<Record<string, string | undefined>> = process.env,
): PaymentGateway {
  const mode = (env[PAYMENT_MODE_ENV] ?? '').trim().toLowerCase();
  if (mode === MOCK_PAYMENT_MODE && !isProductionConfig(env)) {
    return createMockPaymentGateway({
      outcome: 'AUTHORIZED',
      redirectUrlTemplate: MOCK_CALLBACK_URL_TEMPLATE,
    });
  }
  return createZarinPalGatewayFromEnv({
    store: createRepositoryPaymentAuthorizationStore(getRepository),
  });
}
