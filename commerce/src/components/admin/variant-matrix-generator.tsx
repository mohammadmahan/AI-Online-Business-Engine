'use client';

import { Plus, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';

import type { VariantPayload } from '@/contracts/catalog';
import {
  DEFAULT_GARMENT_COLOR,
  GARMENT_COLOR_PRESETS,
} from '@/lib/color-palette';
import { formatCountFa } from '@/lib/format';
import { cn } from '@/lib/utils';
import { buildVariantMatrix, MATRIX_MAX_ROWS } from '@/lib/variant-matrix';
import { isHexColor } from '@/lib/validation';
import { Badge, Field, buttonClass, inputClass } from '@/components/ui/primitives';

/**
 * D-172 §2.1 — the variant matrix generator.
 *
 * The merchant picks a colour palette and a size range; the cartesian product
 * becomes the rows. Every generated cell stays EDITABLE (SKU, stock, price
 * override) because the generator proposes and the merchant decides — the SKU it
 * proposes is a convenience, not a claim, and uniqueness is enforced again on
 * submit by `validateProduct` and by the database indexes.
 *
 * The size presets are the Iranian apparel range the roadmap's §1.3 examples use
 * (36…44, FreeSize); anything else can be typed in, because a boutique's size
 * range is its own.
 */

const SIZE_PRESETS = ['36', '38', '40', '42', '44', 'FreeSize'];

// The palette is CATALOG DATA (garment colours), not design tokens, so it lives
// in `@/lib/color-palette` — the one file the raw-hex lint rule exempts.
const PALETTE_PRESETS = GARMENT_COLOR_PRESETS;

export function VariantMatrixGenerator({
  skuPrefix,
  rows,
  onRowsChange,
}: {
  /** SKU namespace — the parent passes the product slug, upper-cased. */
  skuPrefix: string;
  rows: VariantPayload[];
  onRowsChange: (rows: VariantPayload[]) => void;
}) {
  const [colors, setColors] = useState<Array<{ name: string; hex: string }>>([]);
  const [sizes, setSizes] = useState<string[]>([]);
  const [colorName, setColorName] = useState('');
  const [colorHex, setColorHex] = useState(DEFAULT_GARMENT_COLOR.hex);
  const [customSize, setCustomSize] = useState('');
  const [defaultStock, setDefaultStock] = useState(0);
  const [notice, setNotice] = useState<string | null>(null);

  const expectedRows = colors.length * sizes.length;
  const outOfDate = expectedRows > 0 && expectedRows !== rows.length;

  const generatedLabel = useMemo(
    () =>
      `${formatCountFa(colors.length)} رنگ × ${formatCountFa(sizes.length)} سایز = ${formatCountFa(
        expectedRows,
      )} ترکیب`,
    [colors.length, sizes.length, expectedRows],
  );

  function addColor() {
    const name = colorName.trim();
    if (name.length === 0) {
      setNotice('نام رنگ را وارد کنید.');
      return;
    }
    if (!isHexColor(colorHex)) {
      setNotice('کد رنگ باید در قالب #RRGGBB باشد.');
      return;
    }
    if (colors.some((color) => color.name === name || color.hex.toUpperCase() === colorHex.toUpperCase())) {
      setNotice('این رنگ قبلاً به پالت اضافه شده است.');
      return;
    }
    setColors([...colors, { name, hex: colorHex.toUpperCase() }]);
    setColorName('');
    setNotice(null);
  }

  function togglePresetColor(preset: { name: string; hex: string }) {
    if (colors.some((color) => color.name === preset.name)) {
      setColors(colors.filter((color) => color.name !== preset.name));
      return;
    }
    setColors([...colors, { name: preset.name, hex: preset.hex }]);
    setNotice(null);
  }

  function addSize(size: string) {
    const value = size.trim();
    if (value.length === 0) {
      return;
    }
    if (sizes.includes(value)) {
      setNotice('این سایز قبلاً انتخاب شده است.');
      return;
    }
    setSizes([...sizes, value]);
    setCustomSize('');
    setNotice(null);
  }

  function generate() {
    if (colors.length === 0 || sizes.length === 0) {
      setNotice('برای ساخت ماتریس، حداقل یک رنگ و یک سایز انتخاب کنید.');
      return;
    }
    if (colors.length * sizes.length > MATRIX_MAX_ROWS) {
      setNotice(`تعداد سطرهای ماتریس نباید از ${formatCountFa(MATRIX_MAX_ROWS)} بیشتر باشد.`);
      return;
    }
    // Re-generating REPLACES the rows: the palette/size selection is the input,
    // and silently merging would produce rows nobody asked for.
    onRowsChange(buildVariantMatrix({ colors, sizes, skuPrefix, defaultStock }));
    setNotice(null);
  }

  function patchRow(index: number, patch: Partial<VariantPayload>) {
    onRowsChange(rows.map((row, position) => (position === index ? { ...row, ...patch } : row)));
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="grid gap-4 md:grid-cols-2">
        <section className="rounded-[--radius-cp] border border-edge p-3">
          <h3 className="text-cp-label font-semibold text-ink">۱) پالت رنگ</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {PALETTE_PRESETS.map((preset) => {
              const selected = colors.some((color) => color.name === preset.name);
              return (
                <button
                  key={preset.name}
                  type="button"
                  aria-pressed={selected}
                  onClick={() => togglePresetColor(preset)}
                  className={cn(buttonClass.neutral, selected && 'border-primary font-semibold')}
                >
                  <span
                    aria-hidden="true"
                    className="inline-block size-3 rounded-full border border-edge-strong"
                    style={{ backgroundColor: preset.hex }}
                  />
                  {preset.name}
                </button>
              );
            })}
          </div>

          <div className="mt-3 flex flex-wrap items-end gap-2">
            <Field label="نام رنگ" htmlFor="color-name">
              <input
                id="color-name"
                className={inputClass}
                value={colorName}
                onChange={(event) => setColorName(event.target.value)}
                placeholder="مثال: زیتونی"
              />
            </Field>
            <Field label="کد رنگ" htmlFor="color-hex">
              <input
                id="color-hex"
                className={inputClass}
                value={colorHex}
                onChange={(event) => setColorHex(event.target.value.toUpperCase())}
                dir="ltr"
                placeholder={DEFAULT_GARMENT_COLOR.hex}
              />
            </Field>
            <button type="button" className={buttonClass.neutral} onClick={addColor}>
              <Plus aria-hidden="true" size={16} /> افزودن رنگ
            </button>
          </div>

          <ul className="mt-3 flex flex-wrap gap-2">
            {colors.map((color) => (
              <li key={color.name} className="flex items-center gap-2">
                <Badge>
                  <span
                    aria-hidden="true"
                    className="inline-block size-3 rounded-full border border-edge-strong"
                    style={{ backgroundColor: color.hex }}
                  />
                  {color.name} <span className="cp-code">{color.hex}</span>
                  <button
                    type="button"
                    aria-label={`حذف رنگ ${color.name}`}
                    className="cp-target"
                    onClick={() => setColors(colors.filter((entry) => entry.name !== color.name))}
                  >
                    <Trash2 aria-hidden="true" size={14} />
                  </button>
                </Badge>
              </li>
            ))}
          </ul>
        </section>

        <section className="rounded-[--radius-cp] border border-edge p-3">
          <h3 className="text-cp-label font-semibold text-ink">۲) محدودهٔ سایز</h3>
          <div className="mt-2 flex flex-wrap gap-2">
            {SIZE_PRESETS.map((preset) => {
              const selected = sizes.includes(preset);
              return (
                <button
                  key={preset}
                  type="button"
                  aria-pressed={selected}
                  onClick={() =>
                    setSizes(
                      selected ? sizes.filter((size) => size !== preset) : [...sizes, preset],
                    )
                  }
                  className={cn(
                    buttonClass.neutral,
                    selected && 'border-primary font-semibold',
                  )}
                >
                  <span className="cp-code">{preset}</span>
                </button>
              );
            })}
          </div>
          <div className="mt-3 flex flex-wrap items-end gap-2">
            <Field label="سایز دیگر" htmlFor="custom-size" hint="مثال: 46 یا فری‌سایز">
              <input
                id="custom-size"
                className={inputClass}
                value={customSize}
                onChange={(event) => setCustomSize(event.target.value)}
              />
            </Field>
            <button type="button" className={buttonClass.neutral} onClick={() => addSize(customSize)}>
              <Plus aria-hidden="true" size={16} /> افزودن سایز
            </button>
          </div>

          <div className="mt-3 flex flex-wrap items-end gap-2">
            <Field label="موجودی پیش‌فرض هر ترکیب" htmlFor="default-stock">
              <input
                id="default-stock"
                type="number"
                min={0}
                className={inputClass}
                value={defaultStock}
                onChange={(event) => setDefaultStock(Number(event.target.value))}
              />
            </Field>
            <button type="button" className={buttonClass.primary} onClick={generate}>
              ساخت ماتریس ({generatedLabel})
            </button>
          </div>
          <p className="mt-2 text-cp-caption text-ink-muted">
            پیشوند کد کالا: <span className="cp-code">{skuPrefix || 'SKU'}</span> — هر سطر پس از ساخت
            قابل ویرایش است.
          </p>
        </section>
      </div>

      {notice ? (
        <p className="text-cp-label font-medium text-danger" role="alert">
          {notice}
        </p>
      ) : null}

      {outOfDate ? (
        <p className="text-cp-label font-medium text-warning" role="status">
          ماتریس با انتخاب‌های فعلی هم‌خوان نیست؛ برای هم‌خوان شدن، دوباره «ساخت ماتریس» را بزنید.
        </p>
      ) : null}

      {rows.length > 0 ? (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[44rem] border-collapse text-cp-label">
            <caption className="sr-only">ماتریس رنگ و سایز</caption>
            <thead className="bg-surface-muted">
              <tr>
                <th scope="col" className="border-b border-edge px-3 py-2 text-start">
                  رنگ
                </th>
                <th scope="col" className="border-b border-edge px-3 py-2 text-start">
                  سایز
                </th>
                <th scope="col" className="border-b border-edge px-3 py-2 text-start">
                  کد کالا (SKU)
                </th>
                <th scope="col" className="border-b border-edge px-3 py-2 text-start">
                  موجودی
                </th>
                <th scope="col" className="border-b border-edge px-3 py-2 text-start">
                  قیمت اختصاصی (تومان)
                </th>
                <th scope="col" className="border-b border-edge px-3 py-2 text-start">
                  حذف
                </th>
              </tr>
            </thead>
            <tbody>
              {rows.map((row, index) => (
                <tr key={`${row.size}-${row.colorName}-${index}`}>
                  <td className="border-b border-edge px-3 py-2">
                    <span className="flex items-center gap-2">
                      <span
                        aria-hidden="true"
                        className="inline-block size-4 rounded-full border border-edge-strong"
                        style={{ backgroundColor: row.colorHex }}
                      />
                      {row.colorName}
                    </span>
                  </td>
                  <td className="border-b border-edge px-3 py-2">
                    <span className="cp-code">{row.size}</span>
                  </td>
                  <td className="border-b border-edge px-3 py-2">
                    <label className="sr-only" htmlFor={`sku-${index}`}>
                      کد کالا سطر {formatCountFa(index + 1)}
                    </label>
                    <input
                      id={`sku-${index}`}
                      className={cn(inputClass, 'cp-code')}
                      value={row.sku}
                      onChange={(event) => patchRow(index, { sku: event.target.value })}
                    />
                  </td>
                  <td className="border-b border-edge px-3 py-2">
                    <label className="sr-only" htmlFor={`stock-${index}`}>
                      موجودی سطر {formatCountFa(index + 1)}
                    </label>
                    <input
                      id={`stock-${index}`}
                      type="number"
                      min={0}
                      className={inputClass}
                      value={row.stockQuantity ?? 0}
                      onChange={(event) =>
                        patchRow(index, { stockQuantity: Number(event.target.value) })
                      }
                    />
                  </td>
                  <td className="border-b border-edge px-3 py-2">
                    <label className="sr-only" htmlFor={`price-${index}`}>
                      قیمت اختصاصی سطر {formatCountFa(index + 1)}
                    </label>
                    <input
                      id={`price-${index}`}
                      type="number"
                      min={0}
                      className={inputClass}
                      value={row.priceOverride ?? ''}
                      placeholder="بدون قیمت اختصاصی"
                      onChange={(event) =>
                        patchRow(index, {
                          priceOverride:
                            event.target.value === '' ? null : Number(event.target.value),
                        })
                      }
                    />
                  </td>
                  <td className="border-b border-edge px-3 py-2">
                    <button
                      type="button"
                      className={buttonClass.neutral}
                      aria-label={`حذف سطر ${formatCountFa(index + 1)}`}
                      onClick={() => onRowsChange(rows.filter((_, position) => position !== index))}
                    >
                      <Trash2 aria-hidden="true" size={16} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
          هنوز ترکیبی ساخته نشده است. رنگ‌ها و سایزها را انتخاب کنید و «ساخت ماتریس» را بزنید.
        </p>
      )}
    </div>
  );
}
