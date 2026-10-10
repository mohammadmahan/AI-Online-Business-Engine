import type { ProductCreatePayload, VariantPayload } from '@/contracts/catalog';

/**
 * D-172 Phase 2 — fixtures for the native test suite.
 *
 * Imported ONLY by `*.test.ts`; no application module may import this file, so
 * no invented data can ever reach a rendered route (the admin panel renders the
 * database or a stated refusal, never a sample — D-171 §2.2).
 */

export function variant(overrides: Partial<VariantPayload> = {}): VariantPayload {
  return {
    sku: 'MANTO-KETI-36-1',
    colorName: 'مشکی',
    colorHex: '#111111',
    size: '36',
    stockQuantity: 5,
    priceOverride: null,
    ...overrides,
  };
}

export function validProductPayload(
  overrides: Partial<ProductCreatePayload> = {},
): ProductCreatePayload {
  return {
    categoryId: 'cat-1',
    title: 'مانتو کتی لنین بهاره',
    slug: 'manto-keti-lenin',
    basePrice: 1_250_000,
    discountPrice: null,
    descriptionRaw: 'مانتو کتی لنین با دوخت تمیز و آستر کامل.',
    descriptionHtml: '',
    fabricType: 'لنین',
    season: 'بهاره',
    careInstructions: 'شست‌وشوی دستی با آب سرد',
    status: 'DRAFT',
    variants: [
      variant(),
      variant({ sku: 'MANTO-KETI-38-1', size: '38', stockQuantity: 2, priceOverride: 1_200_000 }),
      variant({ sku: 'MANTO-KETI-36-2', colorName: 'کرم', colorHex: '#F5F5DC' }),
      variant({
        sku: 'MANTO-KETI-38-2',
        colorName: 'کرم',
        colorHex: '#F5F5DC',
        size: '38',
        stockQuantity: 0,
      }),
    ],
    images: [],
    ...overrides,
  };
}
