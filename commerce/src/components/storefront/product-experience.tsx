'use client';

import { Ruler, ShoppingBag } from 'lucide-react';
import { useMemo, useRef, useState } from 'react';

import type { StorefrontProductDetail } from '@/contracts/storefront';
import { MAX_DISTINCT_LINES } from '@/lib/checkout-rules';
import { formatCountFa, formatToman } from '@/lib/format';
import {
  SIZE_CHART,
  SIZE_CHART_COLUMNS,
  SIZE_CHART_NOTE,
  SIZE_CHART_UNKNOWN_NOTE,
  sizeChartRow,
} from '@/lib/size-chart';
import { STOCK_LEVEL_LABELS } from '@/lib/storefront-display';
import {
  canAddVariant,
  colorOptions,
  defaultColor,
  findVariant,
  selectionCap,
  selectionGallery,
  selectionLevel,
  selectionPrice,
  sizeOptions,
  toCartLine,
} from '@/lib/variant-selection';
import { Modal } from '@/components/ui/dialog';
import { sfButton, sfChip, sfField } from '@/components/storefront/storefront-primitives';
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
 * The selection RULES live in `@/lib/variant-selection` so the matrix, the cap,
 * the badge's claim and the cart line can be driven by a hermetic funnel test
 * (`src/__tests__/funnel.test.ts`). This component keeps only state and markup.
 *
 * The quantity cap follows the level: a «موجودی محدود» line can only be taken up
 * to the boutique's low-stock threshold. That reduces — never guarantees — an
 * oversell; the write path re-reads the real quantity inside its transaction.
 *
 * Phase 2C (D-177): editorial treatment only. The gallery is 3:4, the buy box
 * speaks in ink/hairline chips, the level indicator is a dot + Persian label +
 * Latin code (never colour alone), and the CTA is the ink storefront button. The
 * size-chart modal is the ONLY modal on this page switched to the storefront
 * chrome, and it restores focus to its trigger on close; the shared panel default
 * is untouched.
 */
export function ProductExperience({ product }: { product: StorefrontProductDetail }) {
  const { add, openCart } = useCart();

  const colors = useMemo(() => colorOptions(product.variants), [product.variants]);
  const [selectedColor, setSelectedColor] = useState<string | null>(() =>
    defaultColor(product.variants),
  );
  const [selectedSize, setSelectedSize] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [sizeChartOpen, setSizeChartOpen] = useState(false);
  const [cartNotice, setCartNotice] = useState<string | null>(null);
  const sizeGuideRef = useRef<HTMLButtonElement>(null);

  const sizes = useMemo(
    () => sizeOptions(product.sizes, product.variants, selectedColor),
    [product.sizes, product.variants, selectedColor],
  );
  const selectedVariant = findVariant(product.variants, selectedColor, selectedSize);
  const gallery = selectionGallery(product, selectedColor);

  // The level answers about the chosen variant when there is one, and about the
  // colour as a whole before a size is picked — never a claim the data cannot
  // support.
  const level = selectionLevel(product.variants, selectedColor, selectedSize);
  const cap = selectionCap(level);
  const canAdd = canAddVariant(selectedVariant);
  const price = selectionPrice(product, selectedVariant);
  const chartRow = selectedSize === null ? null : sizeChartRow(selectedSize);

  function addToCart() {
    if (!selectedVariant) {
      return;
    }
    const added = add(toCartLine(product, selectedVariant, quantity));
    if (!added) {
      // The basket already holds MAX_DISTINCT_LINES variants; say so rather than
      // letting the click disappear.
      setCartNotice(
        `سبد خرید حداکثر ${formatCountFa(MAX_DISTINCT_LINES)} ردیف دارد؛ برای افزودن این گونه ابتدا یک ردیف را حذف کنید.`,
      );
      return;
    }
    setCartNotice(null);
    openCart();
  }

  return (
    <div className="mt-10 grid gap-10 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)] lg:items-start lg:gap-14">
      {/* The colour is part of the key: switching colour resets the viewer, so a
          stale index can never point past the new photo list. */}
      <ProductGallery
        key={selectedColor ?? 'all'}
        images={gallery}
        title={product.title}
        colorLabel={selectedColor}
      />

      <div className="flex flex-col gap-8">
        <div className="flex flex-col gap-3">
          <p className="flex flex-wrap items-baseline gap-3">
            <span className="font-display text-sf-title font-semibold text-sf-ink">
              {formatToman(price)}
            </span>
            {product.hasDiscount ? (
              <s className="text-sf-caption text-sf-ink-muted">{formatToman(product.basePrice)}</s>
            ) : null}
          </p>

          <p className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sf-caption text-sf-ink">
            <span className="inline-flex items-center gap-2">
              <span
                aria-hidden="true"
                className={cn(
                  'size-2 rounded-full',
                  level === 'IN'
                    ? 'bg-sf-accent'
                    : level === 'LOW'
                      ? 'bg-sf-edge-strong'
                      : 'bg-sf-ink-muted',
                )}
              />
              <span className="font-medium">{STOCK_LEVEL_LABELS[level]}</span>
              <span className="sf-code text-sf-ink-muted">{level}</span>
            </span>
            {selectedVariant === null ? (
              <span className="text-sf-ink-muted">یک اندازه انتخاب کنید.</span>
            ) : selectedVariant.level === 'OUT' ? (
              <span className="text-sf-ink-muted">این ترکیب رنگ و اندازه موجود نیست.</span>
            ) : selectedVariant.level === 'LOW' ? (
              <span className="text-sf-ink-muted">
                از این ترکیب فقط تعداد کمی باقی مانده است.
              </span>
            ) : null}
          </p>
        </div>

        <fieldset className="flex flex-col gap-3">
          <legend className="text-sf-caption font-medium text-sf-ink">رنگ</legend>
          <div className="flex flex-wrap gap-2">
            {colors.map((color) => {
              const isSelected = selectedColor === color.name;
              const sellable = color.sellable;
              return (
                <button
                  key={color.name}
                  type="button"
                  aria-pressed={isSelected}
                  disabled={!sellable}
                  title={sellable ? undefined : 'این رنگ ناموجود است'}
                  className={cn(
                    sfChip.base,
                    isSelected ? sfChip.active : sfChip.rest,
                    !sellable && 'opacity-40',
                  )}
                  onClick={() => {
                    setSelectedColor(color.name);
                    setSelectedSize(null);
                    setQuantity(1);
                  }}
                >
                  <span
                    aria-hidden="true"
                    className="inline-block size-4 rounded-full border border-sf-edge-strong"
                    style={{ backgroundColor: color.hex }}
                  />
                  {color.name}
                  {sellable ? null : ' — ناموجود'}
                </button>
              );
            })}
          </div>
        </fieldset>

        <div className="flex flex-col gap-3">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p id="pdp-size-label" className="text-sf-caption font-medium text-sf-ink">
              اندازه
            </p>
            <button
              ref={sizeGuideRef}
              type="button"
              className="sf-link inline-flex min-h-11 items-center gap-1.5 text-sf-caption"
              onClick={() => setSizeChartOpen(true)}
            >
              <Ruler aria-hidden="true" size={14} />
              راهنمای اندازه
            </button>
          </div>
          <div
            role="group"
            aria-labelledby="pdp-size-label"
            className="flex flex-wrap gap-2"
          >
            {sizes.map(({ size, variant, available }) => (
              <button
                key={size}
                type="button"
                aria-pressed={selectedSize === size}
                disabled={!available}
                title={available ? undefined : 'این اندازه برای رنگ انتخابی ناموجود است'}
                className={cn(
                  sfChip.base,
                  selectedSize === size ? sfChip.active : sfChip.rest,
                  !available && 'opacity-40',
                )}
                onClick={() => {
                  setSelectedSize(size);
                  setQuantity(1);
                }}
              >
                <span className="sf-code">{size}</span>
                {variant === null ? (
                  <span className="text-sf-caption">—</span>
                ) : (
                  <span className="text-sf-caption">{STOCK_LEVEL_LABELS[variant.level]}</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {cap > 0 ? (
          <div className="flex flex-wrap items-center gap-3">
            <label htmlFor="pdp-quantity" className="text-sf-caption text-sf-ink">
              تعداد
            </label>
            <select
              id="pdp-quantity"
              className={cn(sfField, 'w-24')}
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
              <span className="text-sf-caption text-sf-ink-muted">
                حداکثر {formatCountFa(cap)} عدد از این ترکیب قابل سفارش است.
              </span>
            ) : null}
          </div>
        ) : null}

        <button
          type="button"
          className={cn(sfButton.primary, 'w-full disabled:opacity-40')}
          disabled={!canAdd}
          onClick={addToCart}
        >
          <ShoppingBag aria-hidden="true" size={16} />
          افزودن به سبد خرید
        </button>
        {cartNotice === null ? null : (
          <p
            role="status"
            className="border-s-2 border-sf-ink ps-3 text-sf-caption font-medium text-sf-ink"
          >
            {cartNotice}
          </p>
        )}

        <Modal
          open={sizeChartOpen}
          onOpenChange={setSizeChartOpen}
          title="راهنمای اندازه"
          description="اندازه‌ها تقریبی و بر حسب سانتی‌متر است."
          surface="storefront"
          onCloseAutoFocus={(event) => {
            // Radix has no Trigger here (the guide is a plain button), so its
            // default would drop focus on <body>. Return it to the control that
            // opened the chart, synchronously, with no timeout.
            event.preventDefault();
            sizeGuideRef.current?.focus();
          }}
        >
          <table className="w-full border-collapse text-start text-sf-caption">
            <caption className="sr-only">راهنمای اندازهٔ لباس</caption>
            <thead>
              <tr className="border-b border-sf-edge">
                <th scope="col" className="px-2 py-3 text-start font-medium text-sf-ink">
                  اندازه
                </th>
                {SIZE_CHART_COLUMNS.map((column) => (
                  <th
                    key={column.key}
                    scope="col"
                    className="px-2 py-3 text-start font-medium text-sf-ink"
                  >
                    {column.label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {SIZE_CHART.map((row) => (
                <tr
                  key={row.size}
                  className={cn(
                    'border-b border-sf-edge',
                    chartRow?.size === row.size && 'bg-sf-muted',
                  )}
                >
                  <th scope="row" className="px-2 py-3 text-start font-normal text-sf-ink">
                    <span className="sf-code">{row.size}</span>
                  </th>
                  {SIZE_CHART_COLUMNS.map((column) => (
                    <td key={column.key} className="px-2 py-3 text-sf-ink">
                      <span className="sf-code">{formatCountFa(row[column.key])}</span>
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
          <p className="mt-4 text-sf-caption leading-relaxed text-sf-ink-muted">{SIZE_CHART_NOTE}</p>
          {selectedSize !== null && chartRow === null ? (
            <p className="mt-2 text-sf-caption leading-relaxed text-sf-ink-muted">
              {SIZE_CHART_UNKNOWN_NOTE}
            </p>
          ) : null}
        </Modal>
      </div>
    </div>
  );
}
