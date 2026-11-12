/**
 * D-175 / MCS-02 — fail fast on an invalid carrier configuration.
 *
 * The registry is data, so a malformed enablement list or JSON override must be
 * caught before checkout can serve a form. The resolver does not read secrets
 * and performs no network I/O.
 */
export async function register(): Promise<void> {
  if (process.env.NEXT_RUNTIME !== 'nodejs') {
    return;
  }
  const { getShippingConfig } = await import('./server/shipping/config');
  try {
    getShippingConfig();
  } catch (error) {
    // A bad registry must not serve a checkout that cannot price shipping.
    // The message names the offending FIELD/carrier, never an env value.
    console.error('[commerce] invalid shipping configuration — refusing to start', {
      name: error instanceof Error ? error.name : 'UnknownError',
      message: error instanceof Error ? error.message : 'unknown error',
    });
    process.exit(1);
  }
}
