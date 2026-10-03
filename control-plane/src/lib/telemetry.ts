import type { ServiceHealth, TelemetrySummary } from '@/types/telemetry';

/**
 * Roll up service health for the page-level summary.
 *
 * The roll-up is deliberately pessimistic: `worst` is the most severe state
 * present, and `hasAlert` is true whenever anything is not `ok`. There is no
 * averaging that could let several failures hide behind a healthy majority.
 */
export function summarize(services: ServiceHealth[]): TelemetrySummary {
  const count = (state: ServiceHealth['state']) =>
    services.filter((service) => service.state === state).length;

  const ok = count('ok');
  const degraded = count('degraded');
  const unavailable = count('unavailable');
  const unknown = count('unknown');

  const worst: TelemetrySummary['worst'] =
    unavailable > 0
      ? 'unavailable'
      : degraded > 0
        ? 'degraded'
        : unknown > 0
          ? 'unknown'
          : 'ok';

  return {
    total: services.length,
    ok,
    degraded,
    unavailable,
    unknown,
    hasAlert: ok !== services.length,
    worst,
  };
}
