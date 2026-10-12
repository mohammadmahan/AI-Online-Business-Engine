/**
 * D-172 §3.3 — the size-chart guide, as DATA.
 *
 * The roadmap requires a modal size chart with garment measurements in
 * centimetres. Phase 1 enumerated no size-chart table, so this is the GENERAL
 * guide the modal publishes, and the modal says exactly that: it is not a
 * per-product measurement sheet, and no product claims measurements it does not
 * have. A per-product chart would need a schema decision (a `product_measurements`
 * table), which is not this phase's to make silently.
 *
 * Sizes are keyed by the same strings the variant matrix stores (`S`, `M`, `L`,
 * …), so the PDP can look up the row for the size the customer selected.
 */

export interface SizeChartRow {
  size: string;
  /** Centimetres around the fullest part of the chest. */
  chest: number;
  /** Centimetres around the natural waistline. */
  waist: number;
  /** Centimetres around the fullest part of the hips. */
  hip: number;
  /** Garment length from the high point of the shoulder, in centimetres. */
  length: number;
}

export const SIZE_CHART: SizeChartRow[] = [
  { size: 'S', chest: 88, waist: 68, hip: 94, length: 110 },
  { size: 'M', chest: 94, waist: 74, hip: 100, length: 112 },
  { size: 'L', chest: 100, waist: 80, hip: 106, length: 114 },
  { size: 'XL', chest: 106, waist: 86, hip: 112, length: 116 },
  { size: '2XL', chest: 112, waist: 92, hip: 118, length: 118 },
];

export const SIZE_CHART_COLUMNS = [
  { key: 'chest', label: 'دور سینه' },
  { key: 'waist', label: 'دور کمر' },
  { key: 'hip', label: 'دور باسن' },
  { key: 'length', label: 'قد لباس' },
] as const;

export const SIZE_CHART_NOTE =
  'این جدول یک راهنمای کلی است و اندازه‌ها تقریبی و بر حسب سانتی‌متر است. برای انتخاب مطمئن‌تر، اندازه‌های بدن خود را با متر پارچه‌ای بسنجید و در صورت تردید یک سایز بزرگ‌تر انتخاب کنید.';

export const SIZE_CHART_UNKNOWN_NOTE =
  'برای این اندازه راهنمای ثبت‌شده‌ای وجود ندارد؛ می‌توانید اندازه‌های درخواستی خود را در توضیح سفارش بنویسید.';

/** `null` (never a guess) when the selected size has no published row. */
export function sizeChartRow(size: string): SizeChartRow | null {
  const needle = size.trim().toUpperCase();
  return SIZE_CHART.find((row) => row.size.toUpperCase() === needle) ?? null;
}
