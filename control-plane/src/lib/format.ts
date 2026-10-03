/**
 * Deterministic display formatting (D-171 §3.1).
 *
 * Every formatter pins its locale AND its time zone. A value must render
 * identically on the build machine and in the browser, otherwise a statically
 * prerendered page hydrates with different text than it shipped.
 *
 * Latin digits are used for amounts, identifiers and tabular data; the
 * surrounding Persian narrative stays Persian (D-171 §3.1).
 */

const NUMBER = new Intl.NumberFormat('en-US');

/** Thousands-separated integer, Latin digits. Toman amounts are integers (D-010). */
export function formatNumber(value: number): string {
  return NUMBER.format(value);
}

/** One decimal place, Latin digits, always signed where a sign is meaningful. */
export function formatPercent(value: number): string {
  return `${value.toFixed(1)}%`;
}

const TIME_UTC = new Intl.DateTimeFormat('en-GB', {
  hour: '2-digit',
  minute: '2-digit',
  hour12: false,
  timeZone: 'UTC',
});

/** `HH:MM` in UTC. The UI labels the zone so the reading is unambiguous. */
export function formatTimeUtc(iso: string): string {
  return TIME_UTC.format(new Date(iso));
}
