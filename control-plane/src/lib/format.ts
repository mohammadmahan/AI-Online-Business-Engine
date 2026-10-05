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

/**
 * Integer Toman amount with thousands separators (D-010 — amounts are integers
 * with no decimals anywhere). The unit is part of the formatted value so a
 * bare number can never be read as a different currency.
 */
export function formatToman(value: number): string {
  return `${NUMBER.format(value)} تومان`;
}

/**
 * Whole seconds as a Persian duration with Latin digits (e.g. «۱۲ روز و ۳ ساعت»).
 * Deterministic: no locale API, no wall clock.
 */
export function formatUptimeSeconds(seconds: number): string {
  const total = Math.max(0, Math.floor(seconds));
  const days = Math.floor(total / 86_400);
  const hours = Math.floor((total % 86_400) / 3_600);
  const minutes = Math.floor((total % 3_600) / 60);
  if (days > 0) {
    return hours > 0 ? `${days} روز و ${hours} ساعت` : `${days} روز`;
  }
  if (hours > 0) {
    return minutes > 0 ? `${hours} ساعت و ${minutes} دقیقه` : `${hours} ساعت`;
  }
  if (minutes > 0) return `${minutes} دقیقه`;
  return `${total} ثانیه`;
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
