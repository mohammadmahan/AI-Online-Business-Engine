/**
 * D-172 §2 — display formatting for the merchant panel.
 *
 * D-171 §3.1 applies unchanged: Persian numerals in prose and Persian calendar
 * dates for humans, Latin numerals only for machine identifiers (SKU, tracking
 * code, coupon code) which are rendered as-is.
 *
 * Pure functions, no React, no locale state — unit tested.
 */

const PERSIAN_DIGITS = ['۰', '۱', '۲', '۳', '۴', '۵', '۶', '۷', '۸', '۹'];

/** Latin digits → Persian digits (everything else is passed through). */
export function toPersianDigits(input: string | number): string {
  return String(input).replace(/\d/g, (digit) => PERSIAN_DIGITS[Number(digit)] ?? digit);
}

/** Thousands-separated integer in Persian digits: 1250000 → «۱٬۲۵۰٬۰۰۰». */
export function formatCountFa(value: number): string {
  return toPersianDigits(Math.trunc(value).toLocaleString('en-US').replace(/,/g, '٬'));
}

/** Money is integer Toman (D-010) and is always rendered with its unit. */
export function formatToman(value: number): string {
  return `${formatCountFa(value)} تومان`;
}

/** Persian-calendar date+time for a stored `timestamptz`. */
export function formatDateTimeFa(value: Date): string {
  return new Intl.DateTimeFormat('fa-IR', {
    dateStyle: 'short',
    timeStyle: 'short',
  }).format(value);
}

/** Persian-calendar date only (packing slip, coupon expiry). */
export function formatDateFa(value: Date): string {
  return new Intl.DateTimeFormat('fa-IR', { dateStyle: 'medium' }).format(value);
}

/**
 * Value for an `<input type="datetime-local">`, which speaks local time in
 * `YYYY-MM-DDTHH:mm`. Used only to prefill a form control — never to store.
 */
export function toDateTimeLocalValue(value: Date): string {
  const pad = (part: number) => String(part).padStart(2, '0');
  return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}T${pad(
    value.getHours(),
  )}:${pad(value.getMinutes())}`;
}

/** Tracking codes, SKUs and coupon codes stay Latin so they can be read out. */
export function formatMachineCode(value: string | null): string {
  return value && value.length > 0 ? value : '—';
}
