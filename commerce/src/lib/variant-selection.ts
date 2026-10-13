import type {
  CartLine,
  StockLevel,
  StorefrontImageRef,
  StorefrontProductDetail,
  StorefrontVariantView,
} from '@/contracts/storefront';
import { galleryForColor, isSellableLevel, quantityCapForLevel } from '@/lib/storefront-display';

/**
 * D-172 §3.3 — the PDP's colour × size matrix, as a PURE module.
 *
 * The product page is the most rule-dense screen on the storefront: which colour
 * is preselected, which sizes are DISABLED rather than hidden, what the stock
 * badge is allowed to claim before a size is picked, how many pieces may be
 * added, and what exactly lands in the cart. All of it used to live inside the
 * client component, where the only way to test it was to render React.
 *
 * Moving the rules here buys two things that matter beyond tidiness:
 *
 *  - the selection can be driven END TO END by a hermetic test (see
 *    `src/__tests__/funnel.test.ts`), so the customer journey — matrix choice →
 *    cart line → checkout → order row — is guarded without a browser;
 *  - the component keeps only what a component should own: state and markup.
 *
 * Nothing here invents data. A level comes from the server's variant view, a cap
 * comes from `@/lib/storefront-display`, and a missing variant stays missing
 * (the size button stays visible but disabled, per the roadmap's requirement,
 * instead of quietly disappearing).
 */

export interface ColorOption {
  name: string;
  hex: string;
  /** True when ANY size of this colour is sellable today. */
  sellable: boolean;
}

/** Colours in the order the catalog returned them, deduplicated by name. */
export function colorOptions(variants: StorefrontVariantView[]): ColorOption[] {
  const seen = new Map<string, string>();
  for (const variant of variants) {
    if (!seen.has(variant.colorName)) {
      seen.set(variant.colorName, variant.colorHex);
    }
  }
  return [...seen.entries()].map(([name, hex]) => ({
    name,
    hex,
    sellable: variants.some(
      (variant) => variant.colorName === name && isSellableLevel(variant.level),
    ),
  }));
}

/**
 * The colour the page opens on: the first one that can actually be bought, and
 * only when nothing is sellable the first colour at all — so a sold-out product
 * still shows its own colour instead of an empty selector.
 */
export function defaultColor(variants: StorefrontVariantView[]): string | null {
  const sellable = variants.find((variant) => isSellableLevel(variant.level));
  return sellable?.colorName ?? variants[0]?.colorName ?? null;
}

export function variantsForColor(
  variants: StorefrontVariantView[],
  colorName: string | null,
): StorefrontVariantView[] {
  return variants.filter((variant) => variant.colorName === colorName);
}

/** The variant behind one colour + size cell, or `null` when that cell is empty. */
export function findVariant(
  variants: StorefrontVariantView[],
  colorName: string | null,
  size: string | null,
): StorefrontVariantView | null {
  if (colorName === null || size === null) {
    return null;
  }
  return (
    variants.find((variant) => variant.colorName === colorName && variant.size === size) ?? null
  );
}

export interface SizeOption {
  size: string;
  /** The cell's variant, or `null` when this colour has no such size. */
  variant: StorefrontVariantView | null;
  available: boolean;
}

/**
 * One entry per PUBLISHED size of the product — not per size this colour has —
 * so a customer who came for size L learns that this colour has no L instead of
 * wondering where the button went.
 */
export function sizeOptions(
  sizes: string[],
  variants: StorefrontVariantView[],
  colorName: string | null,
): SizeOption[] {
  return sizes.map((size) => {
    const variant = findVariant(variants, colorName, size);
    return {
      size,
      variant,
      available: variant !== null && isSellableLevel(variant.level),
    };
  });
}

/**
 * The level the badge is allowed to state. With a chosen variant it is that
 * cell's own level; before a size is picked it answers about the COLOUR as a
 * whole, and a colour with nothing sellable is `OUT` rather than a reassuring
 * `IN` — never a claim the data cannot support.
 */
export function selectionLevel(
  variants: StorefrontVariantView[],
  colorName: string | null,
  size: string | null,
): StockLevel {
  const variant = findVariant(variants, colorName, size);
  if (variant) {
    return variant.level;
  }
  return variantsForColor(variants, colorName).some((entry) => isSellableLevel(entry.level))
    ? 'IN'
    : 'OUT';
}

/** How many pieces may be added right now, following the level (0 = not addable). */
export function selectionCap(level: StockLevel): number {
  return quantityCapForLevel(level);
}

/**
 * Gallery for the selected colour: photos bound to one of this colour's variants
 * first, the product's own photos after, the whole gallery when this colour has
 * no photos of its own (never an empty viewer).
 */
export function selectionGallery(
  product: StorefrontProductDetail,
  colorName: string | null,
): StorefrontImageRef[] {
  return galleryForColor(
    product.images,
    variantsForColor(product.variants, colorName).map((variant) => variant.variantId),
  );
}

/** Price of the chosen cell, falling back to the product's own price. */
export function selectionPrice(
  product: StorefrontProductDetail,
  variant: StorefrontVariantView | null,
): number {
  return variant?.effectivePrice ?? product.effectivePrice;
}

/** A variant is addable only when it exists AND is sellable today. */
export function canAddVariant(variant: StorefrontVariantView | null): boolean {
  return variant !== null && isSellableLevel(variant.level);
}

/**
 * Builds the cart line for a selection, clamping the quantity to the level's cap.
 *
 * The clamp is a courtesy to the customer, not a guarantee: the write path
 * re-reads the real quantity inside its transaction, and the stored price is
 * display data only.
 */
export function toCartLine(
  product: StorefrontProductDetail,
  variant: StorefrontVariantView,
  quantity: number,
): CartLine {
  const cap = selectionCap(variant.level);
  return {
    variantId: variant.variantId,
    productSlug: product.slug,
    productTitle: product.title,
    size: variant.size,
    colorName: variant.colorName,
    colorHex: variant.colorHex,
    unitPrice: variant.effectivePrice,
    quantity: Math.min(Math.max(Math.trunc(quantity), 1), cap),
    imageUrl: product.primaryImageUrl,
  };
}
