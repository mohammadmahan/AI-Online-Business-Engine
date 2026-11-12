import {
  applyShippingOverrides,
  assertValidShippingConfig,
  ShippingConfigError,
  VALIDATED_DEFAULT_SHIPPING_CONFIG,
  type ShippingConfig,
} from '@/lib/shipping';

/**
 * D-175 / MCS-02 — server-side resolution of the carrier registry.
 *
 * The browser receives the RESOLVED snapshot from the checkout server page, so
 * the displayed options and the write path read one configuration. Secrets are
 * not involved: carrier credentials do not exist in this track.
 */

export const SHIPPING_CONFIG_JSON_ENV = 'COMMERCE_SHIPPING_CONFIG_JSON';
export const SHIPPING_ENABLED_ENV = 'COMMERCE_SHIPPING_ENABLED';
export const SHIPPING_PRIORITY_ENV = 'COMMERCE_SHIPPING_PRIORITY';

let cached: ShippingConfig | null = null;

function parseJsonOverride(raw: string): ShippingConfig {
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    // Never echo the raw value: it may contain operator copy/paste noise.
    throw new ShippingConfigError(`${SHIPPING_CONFIG_JSON_ENV} is not valid JSON`);
  }
  return assertValidShippingConfig(parsed);
}

/** Pure-ish resolution from an explicit env map; no process-global cache. */
export function resolveShippingConfig(
  env: Readonly<Record<string, string | undefined>> = process.env,
): ShippingConfig {
  const rawOverride = env[SHIPPING_CONFIG_JSON_ENV];
  const base =
    rawOverride !== undefined && rawOverride.trim().length > 0
      ? parseJsonOverride(rawOverride)
      : VALIDATED_DEFAULT_SHIPPING_CONFIG;

  return applyShippingOverrides(base, {
    enabled: env[SHIPPING_ENABLED_ENV],
    priority: env[SHIPPING_PRIORITY_ENV],
  });
}

/**
 * Resolved once per server process. Invalid configuration throws a named error;
 * `instrumentation.ts` calls this at startup and the checkout page also catches
 * it so a later runtime change cannot render a half-valid form.
 */
export function getShippingConfig(): ShippingConfig {
  cached ??= resolveShippingConfig();
  return cached;
}

/** Test hook only: production code resolves once and keeps the snapshot. */
export function resetShippingConfigCacheForTests(): void {
  cached = null;
}
