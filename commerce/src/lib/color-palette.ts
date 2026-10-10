/**
 * D-172 §2.1 — the apparel colour palette, as DATA.
 *
 * These hex values are garment colours a boutique sells (the product's
 * `color_hex`), NOT design tokens: they belong to the catalog and never style
 * the panel. `eslint.config.mjs` therefore exempts this one file from the
 * raw-hex rule that governs every component — the design system still lives in
 * `src/app/globals.css` and nothing else may carry a literal colour.
 */

export interface GarmentColor {
  name: string;
  /** Stored in the catalog as `#RRGGBB`; validated by `isHexColor`. */
  hex: string;
}

/** The starting palette offered by the matrix generator (§2.1). */
export const GARMENT_COLOR_PRESETS: GarmentColor[] = [
  { name: 'مشکی', hex: '#111111' },
  { name: 'کرم', hex: '#F5F5DC' },
  { name: 'نسکافه‌ای', hex: '#6B4A2F' },
  { name: 'سفید', hex: '#FFFFFF' },
  { name: 'زیتونی', hex: '#556B2F' },
  { name: 'سرمه‌ای', hex: '#1E3A8A' },
];

/** Pre-selected colour for the manual "add colour" row. */
export const DEFAULT_GARMENT_COLOR: GarmentColor = GARMENT_COLOR_PRESETS[0]!;
