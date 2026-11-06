import { z } from 'zod';

import type { VariantMatrixPayload } from '@/contracts/catalog';

import { MAX_MONEY_TOMAN } from './validation';

/**
 * D-172 §2.1 — the Zod contract behind the variant matrix generator.
 *
 * The generator is the one place where the merchant hands over a STRUCTURE
 * (colours × sizes plus per-row overrides) instead of a handful of scalars, and
 * that structure is built in the browser and re-checked on the server. A Zod
 * schema keeps the shape single-sourced: `z.infer` produces the type the
 * component and the pure builder share, so a new rule can only be added in one
 * place and both callers pick it up. `MATRIX_CONTRACT_PARITY` below makes the
 * drift a COMPILE error rather than a review note.
 *
 * The bounds MIRROR THE DATABASE (`src/db/schema/catalog.ts`), which stays the
 * final authority:
 *   - `product_variants.sku`       varchar(120), unique
 *   - `.color_name` / `.size`      varchar(120) / varchar(64)
 *   - `.stock_quantity`            integer, check `>= 0`
 *   - `.price_override`            bigint, check `>= 0 or null`
 * so anything this schema accepts fits PostgreSQL's length and sign rules.
 * Uniqueness ACROSS products remains the database's job (the unique index);
 * uniqueness INSIDE one submission is validated here because it turns a
 * constraint violation into a field-level message.
 */

/** Row ceiling of one matrix, so the table stays renderable and reviewable. */
export const MATRIX_MAX_ROWS = 240;

/** Same stock ceiling the canonical `isStock` uses (`src/lib/validation.ts`). */
export const MATRIX_MAX_STOCK = 1_000_000;

/** `#RRGGBB` — the format `product_variants.color_hex` stores. */
export const MATRIX_HEX_RE = /^#[0-9a-fA-F]{6}$/;

/** Mirrors the canonical SKU rule (2–64 chars, leading alphanumeric). */
export const MATRIX_SKU_RE = /^[A-Za-z0-9][A-Za-z0-9._-]{1,63}$/;

const HEX_MESSAGE = 'کد رنگ باید در قالب #RRGGBB باشد.';

/** One colour in the palette: display name + swatch. */
export const garmentColorSchema = z.object({
  name: z
    .string()
    .trim()
    .min(1, 'نام رنگ الزامی است.')
    .max(120, 'نام رنگ بیش از ۱۲۰ نویسه است.'),
  hex: z
    .string()
    .trim()
    .regex(MATRIX_HEX_RE, HEX_MESSAGE)
    // Stored upper-case so `#f5f5dc` and `#F5F5DC` are one colour, not two.
    .transform((value) => value.toUpperCase()),
});

/**
 * Select colours + sizes → the request that generates the matrix.
 *
 * `skuPrefix`, `defaultStock` and `defaultPriceOverride` are the generator's
 * CONVENIENCES: the server does not trust them, it re-derives every row and its
 * SKU from the submitted matrix (`validateProduct` + the DB indexes).
 */
export const variantMatrixRequestSchema = z
  .object({
    skuPrefix: z
      .string()
      .trim()
      .min(1, 'پیشوند کد کالا الزامی است.')
      .max(48, 'پیشوند کد کالا بیش از ۴۸ نویسه است.'),
    colors: z.array(garmentColorSchema).min(1, 'حداقل یک رنگ انتخاب کنید.'),
    sizes: z
      .array(
        z
          .string()
          .trim()
          .min(1, 'اندازه (سایز) الزامی است.')
          .max(64, 'اندازه بیش از ۶۴ نویسه است.'),
      )
      .min(1, 'حداقل یک سایز انتخاب کنید.'),
    defaultStock: z
      .number()
      .int('موجودی باید عدد صحیح باشد.')
      .min(0, 'موجودی نمی‌تواند منفی باشد.')
      .max(MATRIX_MAX_STOCK, `موجودی بیش از حد مجاز (${MATRIX_MAX_STOCK}) است.`)
      .optional(),
    defaultPriceOverride: z
      .number()
      .int('قیمت اختصاصی باید عدد صحیح باشد.')
      .min(0, 'قیمت اختصاصی نمی‌تواند منفی باشد.')
      .max(MAX_MONEY_TOMAN, 'قیمت اختصاصی بیش از سقف مجاز است.')
      .nullable()
      .optional(),
  })
  .superRefine((value, ctx) => {
    if (value.colors.length * value.sizes.length > MATRIX_MAX_ROWS) {
      ctx.addIssue({
        code: 'custom',
        path: ['matrix'],
        message: `تعداد سطرهای ماتریس بیش از حد مجاز (${MATRIX_MAX_ROWS}) است.`,
      });
    }
    // A repeated size (or colour name) would generate two identical cells that
    // `validateProduct` and the unique index would reject only on submit.
    if (new Set(value.sizes).size !== value.sizes.length) {
      ctx.addIssue({
        code: 'custom',
        path: ['sizes'],
        message: 'این سایز قبلاً انتخاب شده است.',
      });
    }
    if (new Set(value.colors.map((color) => color.name)).size !== value.colors.length) {
      ctx.addIssue({
        code: 'custom',
        path: ['colors'],
        message: 'این رنگ قبلاً به پالت اضافه شده است.',
      });
    }
  });

/** The generator request — the type the component and the builder both use. */
export type VariantMatrixRequest = z.infer<typeof variantMatrixRequestSchema>;

/**
 * Compile-time parity with the shared contract in `@/contracts/catalog`.
 * If the schema stops producing the promised shape, this file fails to compile
 * instead of the browser and the server drifting apart silently.
 */
export type MatrixContractParity = VariantMatrixRequest extends VariantMatrixPayload
  ? true
  : never;
export const MATRIX_CONTRACT_PARITY: MatrixContractParity = true;

/**
 * One generated cell, validated against the columns it will be written to.
 * `stockQuantity`, `priceOverride` and `isActive` are optional because the DB
 * defaults them; a row that omits them is still a valid row.
 */
export const variantRowSchema = z.object({
  sku: z
    .string()
    .trim()
    .regex(MATRIX_SKU_RE, 'کد کالا باید ۲ تا ۶۴ نویسهٔ لاتین، رقم، نقطه، خط تیره یا زیرخط باشد.'),
  colorName: z
    .string()
    .trim()
    .min(1, 'نام رنگ الزامی است.')
    .max(120, 'نام رنگ بیش از ۱۲۰ نویسه است.'),
  colorHex: z.string().trim().regex(MATRIX_HEX_RE, HEX_MESSAGE),
  size: z
    .string()
    .trim()
    .min(1, 'اندازه (سایز) الزامی است.')
    .max(64, 'اندازه بیش از ۶۴ نویسه است.'),
  stockQuantity: z.number().int('موجودی باید عدد صحیح باشد.').min(0, 'موجودی نمی‌تواند منفی باشد.').max(MATRIX_MAX_STOCK).optional(),
  priceOverride: z
    .number()
    .int('قیمت اختصاصی باید عدد صحیح باشد.')
    .min(0, 'قیمت اختصاصی نمی‌تواند منفی باشد.')
    .max(MAX_MONEY_TOMAN)
    .nullable()
    .optional(),
  isActive: z.boolean().optional(),
});

/** A whole submitted matrix: non-empty, unique SKUs, one row per colour × size. */
export const variantRowsSchema = z
  .array(variantRowSchema)
  .min(1, 'حداقل یک ترکیب رنگ و سایز لازم است.')
  .superRefine((rows, ctx) => {
    const skus = rows.map((row) => row.sku.trim().toUpperCase());
    if (new Set(skus).size !== skus.length) {
      ctx.addIssue({
        code: 'custom',
        path: ['variants'],
        message: 'کد کالا (SKU) در سطرهای ماتریس تکراری است.',
      });
    }
    const cells = rows.map((row) => `${row.size}::${row.colorName}`);
    if (new Set(cells).size !== cells.length) {
      ctx.addIssue({
        code: 'custom',
        path: ['variants'],
        message: 'ترکیب رنگ و سایز تکراری است؛ هر ترکیب فقط یک سطر دارد.',
      });
    }
  });
