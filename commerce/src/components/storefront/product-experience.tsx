'use client';

import { Ruler, ShoppingBag } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { CartLine, StorefrontProductDetail } from '@/contracts/storefront';
import { formatCountFa, formatToman } from '@/lib/format';
import {
  SIZE_CHART,
  SIZE_CHART_COLUMNS,
  SIZE_CHART_NOTE,
  SIZE_CHART_UNKNOWN_NOTE,
  sizeChartRow,
} from '@/lib/size-chart';
import {
  STOCK_LEVEL_LABELS,
  STOCK_LEVEL_TONE,
  galleryForColor,
  isSellableLevel,
  quantityCapForLevel,
} from '@/lib/storefront-display';
import { Modal } from '@/components/ui/dialog';
import { Badge, Table, Td, Th, buttonClass } from '@/components/ui/primitives';
import { cn } from '@/lib/utils';

import { useCart } from './cart-provider';
import { ProductGallery } from './product-gallery';

/**
 * D-172 §3.3 — the interactive body of the product page.
 *
 * One client component owns the selection (colour → size → quantity) because the
 * gallery and the buy box must agree: the colour drives which photos the gallery
 * shows, which sizes are selectable, and which stock level is announced.
 *
 * Everything displayed is a LEVEL, never a quantity: `StorefrontVariantView`
 * carries `IN` / `LOW` / `OUT` from the server, so the page can say «موجودی محدود»
 * without publishing how many pieces the boutique holds (D-172 §3).
 *
 * The size buttons use the product's full published size list and DISABLE the
 * ones the chosen colour does not have, rather than hiding them: a customer who
 * came for size L learns that this colour has no L instead of wondering where the
 * button went (the roadmap's "automatic disabled state").
 *
 * The quantity cap follows the level: a «موجودی محدود» line can only be taken up
 * to the boutique's low-stock threshold. That reduces — never guarantees — an
 * oversell; the write path re-reads the real quantity inside its transaction.
 */
export function ProductExperience({ product }: { product: StorefrontProductDetail }) {
  const { add, openCart } = useCart();

  const colors = useMemo(() => {
    const seen = new Map<string, string>();
    for (const variant of product.variants) {
      if (!seen.has(variant.colorName)) {
        seen.set(variant.colorName, variant.colorHex);
      }
    }
    return [...seen.entries()].map(([name, hex]) => ({ name, hex }));
  }, [product.variants]);

  const [selectedColor, setSelectedColor] = useState<string | null>(() => {
    const sellable = product.variants.find((variant) => isSellableLevel(variant.level));
    return sellable?.colorName ?? colors[0]?.name ?? null;
  });
  const [selectedSize, setSelectedSize] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [sizeChartOpen, setSizeChartOpen] = useState(false);

  const colorVariants = product.variants.filter((variant) => variant.colorName === selectedColor);
  const selectedVariant = colorVariants.find((variant) => variant.size === selectedSize) ?? null;
  const gallery = galleryForColor(
    product.images,
    colorVariants.map((variant) => variant.variantId),
  );

  // The badge answers about the chosen variant when there is one, and about the
  // colour as a whole before a size is picked — never a claim the data cannot
  // support.
  const level = selectedVariant
    ? selectedVariant.level
    : colorVariants.some((variant) => isSellableLevel(variant.level))
      ? 'IN'
      : 'OUT';
  const cap = quantityCapForLevel(level);
  const canAdd = selectedVariant !== null && isSellableLevel(selectedVariant.level);
  const price = selectedVariant?.effectivePrice ?? product.effectivePrice;
  const chartRow = selectedSize === null ? null : sizeChartRow(selectedSize);

  function addToCart() {
    if (!selectedVariant) {
      return;
    }
    const line: CartLine = {
      variantId: selectedVariant.variantId,
      productSlug: product.slug,
      productTitle: product.title,
      size: selectedVariant.size,
      colorName: selectedVariant.colorName,
      colorHex: selectedVariant.colorHex,
      unitPrice: selectedVariant.effectivePrice,
      quantity: Math.min(quantity, cap),
      imageUrl: product.primaryImageUrl,
    };
    add(line);
    openCart();
  }

  return (
    <div className="mt-6 grid gap-6 lg:grid-cols-2">
      {/* The colour is part of the key: switching colour resets the viewer, so a
          stale index can never point past the new photo list. */}
      <ProductGallery
        key={selectedColor ?? 'all'}
        images={gallery}
        title={product.title}
        colorLabel={selectedColor}
      />

      <div className="flex flex-col gap-4">
        <p className="flex flex-wrap items-baseline gap-2">
          <span className="text-cp-heading font-bold text-ink">{formatToman(price)}</span>
          {product.hasDiscount ? (
            <s className="text-cp-label text-ink-muted">{formatToman(product.basePrice)}</s>
          ) : null}
        </p>

        <p className="flex flex-wrap items-center gap-2">
          <Badge tone={STOCK_LEVEL_TONE[level]}>
            {STOCK_LEVEL_LABELS[level]} <span className="cp-code">{level}</span>
          </Badge>
          {selectedVariant === null ? (
            <span className="text-cp-caption text-ink-muted">یک اندازه انتخاب کنید.</span>
          ) : selectedVariant.level === 'OUT' ? (
            <span className="text-cp-caption text-ink-muted">
              این ترکیب رنگ و اندازه موجود نیست.
            </span>
          ) : selectedVariant.level === 'LOW' ? (
            <span className="text-cp-caption text-ink-muted">
              از این ترکیب فقط تعداد کمی باقی مانده است.
            </span>
          ) : null}
        </p>

        <fieldset className="flex flex-col gap-2">
          <legend className="text-cp-label font-medium text-ink">رنگ</legend>
          <div className="flex flex-wrap gap-2">
            {colors.map((color) => {
              const sellable = product.variants.some(
                (variant) => variant.colorName === color.name && isSellableLevel(variant.level),
              );
              const isSelected = selectedColor === color.name;
              return (
                <button
                  key={color.name}
                  type="button"
                  aria-pressed={isSelected}
                  disabled={!sellable}
                  title={sellable ? undefined : 'این رنگ ناموجود است'}
                  className={cn(
                    buttonClass.neutral,
                    isSelected && 'border-primary text-primary',
                    !sellable && 'opacity-50',
                  )}
                  onClick={() => {
                    setSelectedColor(color.name);
                    setSelectedSize(null);
                    setQuantity(1);
                  }}
                >
                  <span
                    aria-hidden="true"
                    className="inline-block size-4 rounded-full border border-edge-strong"
                    style={{ backgroundColor: color.hex }}
                  />
                  {color.name}
                  {sellable ? null : ' — ناموجود'}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="flex flex-col gap-2">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-cp-label font-medium text-ink">اندازه</p>
            <button
              type="button"
              className={cn(buttonClass.neutral, 'px-2 text-cp-caption')}
              onClick={() => setSizeChartOpen(true)}
            >
              <Ruler aria-hidden="true" size={14} />
              راهنمای اندازه
            </button>
          </div>
          <div className="flex flex-wrap gap-2">
            {product.sizes.map((size) => {
              const variant = colorVariants.find((entry) => entry.size === size) ?? null;
              const available = variant !== null && isSellableLevel(variant.level);
              return (
                <button
                  key={size}
                  type="button"
                  aria-pressed={selectedSize === size}
                  disabled={!available}
                  title={available ? undefined : 'این اندازه برای رنگ انتخابی ناموجود است'}
                  className={cn(
                    buttonClass.neutral,
                    selectedSize === size && 'border-primary text-primary',
                    !available && 'opacity-50',
                  )}
                  onClick={() => {
                    setSelectedSize(size);
                    setQuantity(1);
                  }}
                >
                  <span className="cp-code">{size}</span>
                  {variant === null ? (
                    <span className="text-cp-caption text-ink-muted">—</span>
                  ) : (
                    <span className="text-cp-caption text-ink-muted">
                      {STOCK_LEVEL_LABELS[variant.level]}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </div>

        {cap > 0 ? (
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="pdp-quantity" className="text-cp-label text-ink">
              تعداد
            </label>
            <select
              id="pdp-quantity"
              className={cn(buttonClass.neutral, 'cp-target')}
              value={Math.min(quantity, cap)}
              onChange={(event) => setQuantity(Number(event.target.value))}
            >
              {Array.from({ length: cap }, (_, index) => index + 1).map((value) => (
                <option key={value} value={value}>
                  {formatCountFa(value)}
                </option>
              ))}
            </select>
            {level === 'LOW' ? (
              <span className="text-cp-caption text-ink-muted">
                حداکثر {formatCountFa(cap)} عدد از این ترکیب قابل سفارش است.
              </span>
            ) : null}
          </div>
        ) : null}

        <button type="button" className={buttonClass.primary} disabled={!canAdd} onClick={addToCart}>
          <ShoppingBag aria-hidden="true" size={16} />
          افزودن به سبد خرید
        </button>

        <Modal
          open={sizeChartOpen}
          onOpenChange={setSizeChartOpen}
          title="راهنمای اندازه"
          description="اندازه‌ها تقریبی و بر حسب سانتی‌متر است."
        >
          <Table
            caption="راهنمای اندازهٔ لباس"
            head={
              <tr>
                <Th>اندازه</Th>
                {SIZE_CHART_COLUMNS.map((column) => (
                  <Th key={column.key}>{column.label}</Th>
                ))}
              </tr>
            }
          >
            {SIZE_CHART.map((row) => (
              <tr key={row.size} className={cn(chartRow?.size === row.size && 'bg-surface-muted')}>
                <Td>
                  <span className="cp-code">{row.size}</span>
                </Td>
                {SIZE_CHART_COLUMNS.map((column) => (
                  <Td key={column.key}>
                    <span className="cp-code">{formatCountFa(row[column.key])}</span>
                  </Td>
                ))}
              </tr>
            ))}
          </Table>
          <p className="mt-3 text-cp-caption text-ink-muted">{SIZE_CHART_NOTE}</p>
          {selectedSize !== null && chartRow === null ? (
            <p className="mt-2 text-cp-caption text-ink-muted">{SIZE_CHART_UNKNOWN_NOTE}</p>
          ) : null}
        </Modal>
      </div>
    </div>
  );
}
