'use client';

import { Check, Loader2, Save } from 'lucide-react';
import { useMemo, useState } from 'react';

import { formatCountFa, formatToman } from '@/lib/format';
import {
  LOW_STOCK_THRESHOLD,
  effectivePrice,
  filterInventory,
  inventorySummary,
  matchesQuery,
  stockState,
  type StockFilter,
} from '@/lib/inventory-rules';
import { cn } from '@/lib/utils';
import type { InventoryRow } from '@/server/repository';
import { updatePriceAction, updateStockAction } from '@/server/actions/inventory';
import { Badge, Card, CardHeader, Td, Th, Table, buttonClass, inputClass } from '@/components/ui/primitives';

/**
 * D-172 §2.2 — inventory & inline management.
 *
 * Every cell saves on its own (Enter or the row's save button) and answers for
 * its own result: a refused edit shows the server's Persian message right there
 * and leaves the stored value untouched — the grid never claims a save that did
 * not happen. The filter chips and the badges are computed from the same pure
 * rules module the server uses, so "موجودی کم" means one thing in this panel.
 */

type RowMessage = { tone: 'ok' | 'error'; text: string };

export function InventoryWorkspace({
  rows,
  threshold = LOW_STOCK_THRESHOLD,
}: {
  rows: InventoryRow[];
  threshold?: number;
}) {
  const [filter, setFilter] = useState<StockFilter>('all');
  const [query, setQuery] = useState('');
  const [drafts, setDrafts] = useState<Record<string, { stock?: string; price?: string }>>({});
  const [messages, setMessages] = useState<Record<string, RowMessage>>({});
  const [saving, setSaving] = useState<Record<string, boolean>>({});

  const summary = useMemo(() => inventorySummary(rows, threshold), [rows, threshold]);
  const visible = useMemo(
    () => filterInventory(rows, filter, threshold).filter((row) => matchesQuery(row, query)),
    [rows, filter, threshold, query],
  );

  function draftFor(row: InventoryRow) {
    const draft = drafts[row.variantId] ?? {};
    return {
      stock: draft.stock ?? String(row.stockQuantity),
      price: draft.price ?? (row.priceOverride === null ? '' : String(row.priceOverride)),
    };
  }

  function setDraft(variantId: string, patch: { stock?: string; price?: string }) {
    setDrafts((current) => ({ ...current, [variantId]: { ...current[variantId], ...patch } }));
  }

  function clearMessage(variantId: string) {
    setMessages((current) => {
      const next = { ...current };
      delete next[variantId];
      return next;
    });
  }

  async function saveStock(row: InventoryRow) {
    const draft = draftFor(row).stock;
    clearMessage(row.variantId);
    setSaving((current) => ({ ...current, [`${row.variantId}:stock`]: true }));
    const response = await updateStockAction({
      variantId: row.variantId,
      stockQuantity: draft === '' ? Number.NaN : Number(draft),
    });
    setSaving((current) => ({ ...current, [`${row.variantId}:stock`]: false }));
    setMessages((current) => ({
      ...current,
      [row.variantId]: response.ok
        ? { tone: 'ok', text: 'موجودی ذخیره شد.' }
        : { tone: 'error', text: response.message },
    }));
  }

  async function savePrice(row: InventoryRow) {
    const draft = draftFor(row).price;
    clearMessage(row.variantId);
    setSaving((current) => ({ ...current, [`${row.variantId}:price`]: true }));
    const response = await updatePriceAction({
      variantId: row.variantId,
      priceOverride: draft === '' ? null : Number(draft),
    });
    setSaving((current) => ({ ...current, [`${row.variantId}:price`]: false }));
    setMessages((current) => ({
      ...current,
      [row.variantId]: response.ok
        ? { tone: 'ok', text: 'قیمت ذخیره شد.' }
        : { tone: 'error', text: response.message },
    }));
  }

  const chips: Array<{ key: StockFilter; label: string; count: number }> = [
    { key: 'all', label: 'همه', count: summary.total },
    { key: 'low', label: 'موجودی کم', count: summary.low },
    { key: 'out', label: 'ناموجود', count: summary.out },
    { key: 'inactive', label: 'غیرفعال', count: summary.inactive },
  ];

  return (
    <Card>
      <CardHeader
        title="موجودی و قیمت"
        description={`آستانهٔ «موجودی کم»: ${formatCountFa(threshold)} عدد. ویرایش درجا بدون بازخوانی صفحه ذخیره می‌شود.`}
        action={
          <input
            type="search"
            className={inputClass}
            placeholder="جست‌وجو در محصول، کد کالا، سایز، رنگ"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            aria-label="جست‌وجو در موجودی"
          />
        }
      />

      <div className="mb-3 flex flex-wrap gap-2">
        {chips.map((chip) => (
          <button
            key={chip.key}
            type="button"
            aria-pressed={filter === chip.key}
            className={cn(buttonClass.neutral, filter === chip.key && 'border-primary font-semibold')}
            onClick={() => setFilter(chip.key)}
          >
            {chip.label} ({formatCountFa(chip.count)})
          </button>
        ))}
      </div>

      {visible.length === 0 ? (
        <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
          در این فیلتر سطری وجود ندارد.
        </p>
      ) : (
        <Table
          caption="فهرست موجودی گونه‌ها"
          head={
            <tr>
              <Th>محصول</Th>
              <Th>کد کالا</Th>
              <Th>سایز</Th>
              <Th>رنگ</Th>
              <Th>وضعیت</Th>
              <Th>موجودی</Th>
              <Th>قیمت مؤثر</Th>
              <Th>قیمت اختصاصی</Th>
              <Th>ذخیره</Th>
            </tr>
          }
        >
          {visible.map((row) => {
            const state = stockState(row, threshold);
            const draft = draftFor(row);
            const message = messages[row.variantId];
            return (
              <tr key={row.variantId}>
                <Td>
                  {row.productTitle}
                  <span className="block text-cp-caption text-ink-muted">{row.productSlug}</span>
                </Td>
                <Td>
                  <span className="cp-code">{row.sku}</span>
                </Td>
                <Td>
                  <span className="cp-code">{row.size}</span>
                </Td>
                <Td>
                  <span className="flex items-center gap-2">
                    <span
                      aria-hidden="true"
                      className="inline-block size-4 rounded-full border border-edge-strong"
                      style={{ backgroundColor: row.colorHex }}
                    />
                    {row.colorName}
                  </span>
                </Td>
                <Td>
                  <Badge tone={state.tone}>
                    {state.label} <span className="cp-code">{state.code}</span>
                  </Badge>
                </Td>
                <Td>
                  <label className="sr-only" htmlFor={`stock-${row.variantId}`}>
                    موجودی {row.sku}
                  </label>
                  <input
                    id={`stock-${row.variantId}`}
                    type="number"
                    min={0}
                    className={cn(inputClass, 'w-24')}
                    value={draft.stock}
                    onChange={(event) => setDraft(row.variantId, { stock: event.target.value })}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        void saveStock(row);
                      }
                    }}
                  />
                </Td>
                <Td>{formatToman(effectivePrice(row))}</Td>
                <Td>
                  <label className="sr-only" htmlFor={`price-${row.variantId}`}>
                    قیمت اختصاصی {row.sku}
                  </label>
                  <input
                    id={`price-${row.variantId}`}
                    type="number"
                    min={0}
                    placeholder="بدون قیمت اختصاصی"
                    className={cn(inputClass, 'w-32')}
                    value={draft.price}
                    onChange={(event) => setDraft(row.variantId, { price: event.target.value })}
                    onKeyDown={(event) => {
                      if (event.key === 'Enter') {
                        event.preventDefault();
                        void savePrice(row);
                      }
                    }}
                  />
                </Td>
                <Td>
                  <span className="flex items-center gap-1">
                    <button
                      type="button"
                      className={buttonClass.neutral}
                      aria-label={`ذخیرهٔ موجودی ${row.sku}`}
                      onClick={() => void saveStock(row)}
                      disabled={saving[`${row.variantId}:stock`] === true}
                    >
                      {saving[`${row.variantId}:stock`] ? (
                        <Loader2 aria-hidden="true" size={14} />
                      ) : (
                        <Save aria-hidden="true" size={14} />
                      )}
                      موجودی
                    </button>
                    <button
                      type="button"
                      className={buttonClass.neutral}
                      aria-label={`ذخیرهٔ قیمت ${row.sku}`}
                      onClick={() => void savePrice(row)}
                      disabled={saving[`${row.variantId}:price`] === true}
                    >
                      {saving[`${row.variantId}:price`] ? (
                        <Loader2 aria-hidden="true" size={14} />
                      ) : (
                        <Save aria-hidden="true" size={14} />
                      )}
                      قیمت
                    </button>
                  </span>
                  {message ? (
                    <span
                      role="status"
                      className={cn(
                        'mt-1 flex items-center gap-1 text-cp-caption',
                        message.tone === 'ok' ? 'text-success' : 'text-danger',
                      )}
                    >
                      {message.tone === 'ok' ? <Check aria-hidden="true" size={12} /> : null}
                      {message.text}
                    </span>
                  ) : null}
                </Td>
              </tr>
            );
          })}
        </Table>
      )}
    </Card>
  );
}
