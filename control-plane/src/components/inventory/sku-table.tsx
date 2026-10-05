'use client';

import { ChevronDown, ChevronUp, ShieldQuestion } from 'lucide-react';
import { Fragment, useState } from 'react';

import {
  LOCK_STATE_META,
  REVIEW_STATE_LABEL,
  SOURCE_TYPE_LABEL,
  STOCK_CATEGORY_META,
  SYNC_DIRECTION_LABEL,
  SYNC_OUTCOME_META,
  SYNC_STATUS_META,
} from '@/components/inventory/inventory-meta';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatNumber, formatToman } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { InventoryItem } from '@/types/inventory';

/** Shortened variant id for the dense row; the full value stays in `title`. */
function shortVariant(variantId: string): string {
  return `${variantId.slice(0, 8)}…${variantId.slice(-4)}`;
}

/** Expanded row: WooCommerce mapping, alert/lock/provenance and sync history. */
function SkuDetail({ item }: { item: InventoryItem }) {
  const stock = STOCK_CATEGORY_META[item.stockCategory];
  const lock = LOCK_STATE_META[item.lock.state];
  const provenance = SOURCE_TYPE_LABEL[item.provenance.sourceType];
  const review = REVIEW_STATE_LABEL[item.provenance.reviewState];

  return (
    <section
      aria-label={`جزئیات SKU ${item.sku}`}
      className="flex flex-col gap-4 text-cp-label"
    >
      <dl className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <div>
          <dt className="text-cp-caption text-ink-muted">شناسه WooCommerce (محصول)</dt>
          <dd className="font-mono text-ink" dir="ltr">
            {item.sync.woo.productId ?? '—'}
          </dd>
        </div>
        <div>
          <dt className="text-cp-caption text-ink-muted">شناسه WooCommerce (واریانت)</dt>
          <dd className="font-mono text-ink" dir="ltr">
            {item.sync.woo.variationId ?? '—'}
          </dd>
        </div>
        <div>
          <dt className="text-cp-caption text-ink-muted">مپینگ فعال (D-046)</dt>
          <dd className="text-ink">{item.sync.woo.active ? 'بله' : 'خیر'}</dd>
        </div>
        <div>
          <dt className="text-cp-caption text-ink-muted">آخرین تلاش همگام‌سازی</dt>
          <dd className="font-mono text-cp-caption text-ink" dir="ltr">
            {item.sync.lastAttemptLogical ?? '—'}
          </dd>
        </div>
      </dl>

      {item.alert !== null ? (
        <div className="rounded-[--radius-cp] border border-warning bg-surface p-3">
          <div className="flex flex-wrap items-center gap-2">
            <ToneBadge tone="warning" label="هشدار موجودی" code="LOW_STOCK_ALERT" Icon={ShieldQuestion} />
            <span className="font-mono text-cp-caption text-ink-muted" dir="ltr">
              {item.alert.raisedAtLogical}
            </span>
          </div>
          <p className="mt-2 text-cp-label text-ink">{item.alert.reason}</p>
        </div>
      ) : null}

      <div className="grid gap-3 sm:grid-cols-2">
        <div className="rounded-[--radius-cp] border border-edge p-3">
          <div className="flex flex-wrap items-center gap-2">
            <ToneBadge
              tone={lock.tone}
              label={lock.label}
              code={lock.code}
              Icon={lock.Icon}
            />
            <ToneBadge
              tone={stock.tone}
              label={stock.label}
              code={stock.code}
              Icon={stock.Icon}
            />
          </div>
          {item.lock.state === 'NONE' ? (
            <p className="mt-2 text-cp-caption text-ink-muted">
              قفل دستی روی این SKU وجود ندارد؛ نوشتن همگام‌سازی تنها از مسیر canonical مجاز است.
            </p>
          ) : (
            <p className="mt-2 text-cp-label text-ink">
              {item.lock.reason}{' '}
              <span className="font-mono text-cp-caption text-ink-muted" dir="ltr">
                ({item.lock.setAtLogical})
              </span>
            </p>
          )}
        </div>

        <div className="rounded-[--radius-cp] border border-edge p-3">
          <p className="text-cp-caption text-ink-muted">منبع داده (D-026)</p>
          <p className="mt-1 text-cp-label text-ink">
            {provenance.label}{' '}
            <span className="font-mono text-cp-caption text-ink-muted">({provenance.code})</span>
          </p>
          <p className="mt-1 text-cp-label text-ink">
            بازبینی: {review.label}{' '}
            <span className="font-mono text-cp-caption text-ink-muted">({review.code})</span>
          </p>
          <p className="mt-1 font-mono text-cp-caption text-ink-muted" dir="ltr">
            {item.provenance.actor}
          </p>
        </div>
      </div>

      <div className="flex flex-col gap-2">
        <h3 className="text-cp-label font-semibold text-ink">
          تاریخچه‌ی همگام‌سازی WooCommerce
        </h3>
        <div className="overflow-x-auto rounded-[--radius-cp] border border-edge">
          <table className="w-full border-collapse text-cp-caption">
            <caption className="sr-only">
              تاریخچه‌ی تلاش‌های همگام‌سازی برای SKU {item.sku}، از قدیم به جدید
            </caption>
            <thead>
              <tr className="bg-surface text-ink-muted">
                <th scope="col" className="p-2 text-start font-medium">گام</th>
                <th scope="col" className="p-2 text-start font-medium">زمان منطقی</th>
                <th scope="col" className="p-2 text-start font-medium">جهت</th>
                <th scope="col" className="p-2 text-start font-medium">نتیجه</th>
                <th scope="col" className="p-2 text-start font-medium">روایت</th>
                <th scope="col" className="p-2 text-start font-medium">رد (D-121)</th>
              </tr>
            </thead>
            <tbody>
              {item.sync.history.map((entry) => {
                const direction = SYNC_DIRECTION_LABEL[entry.direction];
                const outcome = SYNC_OUTCOME_META[entry.outcome];
                return (
                  <tr key={entry.seq} className="border-t border-edge align-top">
                    <td className="p-2 font-mono text-ink tabular-nums">{entry.seq}</td>
                    <td className="p-2 font-mono text-ink-muted" dir="ltr">
                      {entry.atLogical}
                    </td>
                    <td className="p-2 text-ink">
                      {direction.label}{' '}
                      <span className="font-mono text-ink-muted">({direction.code})</span>
                    </td>
                    <td className="p-2">
                      <ToneBadge
                        tone={outcome.tone}
                        label={outcome.label}
                        code={outcome.code}
                        Icon={outcome.Icon}
                      />
                    </td>
                    <td className="p-2 text-ink">{entry.detail}</td>
                    <td className="p-2 font-mono text-ink-muted" dir="ltr">
                      {entry.traceId}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="text-cp-caption text-ink-muted">
          تاریخچه از رویدادهای ماندگار بازسازی می‌شود و هر گام رد D-121 خود را دارد؛ هیچ
          زنجیره‌ی خام یا مقدار ساختگی نمایش داده نمی‌شود.
        </p>
      </div>
    </section>
  );
}

/**
 * The dense SKU table (D-171 §5.3).
 *
 * RTL and column-aligned, so it stays scannable; on narrow screens the wrapper
 * scrolls horizontally instead of reflowing the columns. Product ID, Variant ID
 * and SKU each get their OWN column (D-015 — never derived from one another for
 * display). Each row exposes its WooCommerce sync history through a real
 * `<button>` with `aria-expanded`/`aria-controls`, so the detail row is
 * reachable by keyboard and not by hover alone.
 */
export function SkuTable({
  items,
  emptyMessage,
}: {
  items: InventoryItem[];
  emptyMessage: string;
}) {
  const [expandedSku, setExpandedSku] = useState<string | null>(null);

  if (items.length === 0) {
    return (
      <p className="flex items-center gap-2 rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
        <ShieldQuestion aria-hidden="true" className="size-4 shrink-0" />
        {emptyMessage}
      </p>
    );
  }

  return (
    <div className="overflow-x-auto rounded-[--radius-cp] border border-edge">
      <table className="w-full min-w-[1080px] border-collapse text-cp-label">
        <caption className="sr-only">
          فهرست SKUها؛ شناسه‌ی محصول، شناسه‌ی واریانت و SKU جداگانه نمایش داده می‌شوند (D-015)
        </caption>
        <thead>
          <tr className="bg-surface-muted text-cp-caption text-ink-muted">
            <th scope="col" className="p-2 text-start font-medium">محصول</th>
            <th scope="col" className="p-2 text-start font-medium">Product ID</th>
            <th scope="col" className="p-2 text-start font-medium">Variant ID</th>
            <th scope="col" className="p-2 text-start font-medium">SKU</th>
            <th scope="col" className="p-2 text-start font-medium">قیمت</th>
            <th scope="col" className="p-2 text-start font-medium">موجودی / آستانه</th>
            <th scope="col" className="p-2 text-start font-medium">وضعیت موجودی</th>
            <th scope="col" className="p-2 text-start font-medium">همگام‌سازی</th>
            <th scope="col" className="p-2 text-start font-medium">قفل</th>
            <th scope="col" className="p-2 text-start font-medium">جزئیات</th>
          </tr>
        </thead>
        <tbody>
          {items.map((item) => {
            const expanded = expandedSku === item.sku;
            const detailId = `sku-detail-${item.sku}`;
            const stock = STOCK_CATEGORY_META[item.stockCategory];
            const sync = SYNC_STATUS_META[item.sync.status];
            const lock = LOCK_STATE_META[item.lock.state];
            return (
              <Fragment key={item.sku}>
                <tr className="border-t border-edge align-top">
                  <th scope="row" className="p-2 text-start font-normal">
                    <span className="block text-cp-label text-ink">{item.nameFa}</span>
                    <span className="mt-1 block text-cp-caption text-ink-muted">
                      {item.categoryLabel}{' '}
                      <span className="font-mono opacity-80">({item.categoryCode})</span>
                    </span>
                  </th>
                  <td className="p-2 font-mono text-cp-caption text-ink" dir="ltr">
                    {item.product_id}
                  </td>
                  <td
                    className="p-2 font-mono text-cp-caption text-ink-muted"
                    dir="ltr"
                    title={item.variant_id}
                  >
                    {shortVariant(item.variant_id)}
                  </td>
                  <td className="p-2 font-mono text-cp-label text-ink" dir="ltr">
                    {item.sku}
                  </td>
                  <td className="p-2 text-cp-label text-ink tabular-nums">
                    {formatToman(item.price_toman)}
                  </td>
                  <td className="p-2 text-cp-label text-ink tabular-nums">
                    {formatNumber(item.stock_qty)} / {formatNumber(item.safe_threshold)}
                  </td>
                  <td className="p-2">
                    <ToneBadge
                      tone={stock.tone}
                      label={stock.label}
                      code={stock.code}
                      Icon={stock.Icon}
                    />
                  </td>
                  <td className="p-2">
                    <ToneBadge
                      tone={sync.tone}
                      label={sync.label}
                      code={sync.code}
                      Icon={sync.Icon}
                    />
                  </td>
                  <td className="p-2">
                    {item.lock.state === 'NONE' ? (
                      <span className="text-cp-caption text-ink-muted">—</span>
                    ) : (
                      <ToneBadge
                        tone={lock.tone}
                        label={lock.label}
                        code={lock.code}
                        Icon={lock.Icon}
                      />
                    )}
                  </td>
                  <td className="p-2">
                    <button
                      type="button"
                      onClick={() => setExpandedSku(expanded ? null : item.sku)}
                      aria-expanded={expanded}
                      aria-controls={detailId}
                      aria-label={`${expanded ? 'بستن' : 'نمایش'} جزئیات و تاریخچه‌ی همگام‌سازی ${item.sku}`}
                      className={cn(
                        'cp-target inline-flex items-center gap-1 rounded-[--radius-cp]',
                        'border border-edge-strong bg-surface px-2 py-1',
                        'text-cp-caption font-medium text-ink hover:bg-surface-muted',
                      )}
                    >
                      {expanded ? (
                        <ChevronUp aria-hidden="true" className="size-4" />
                      ) : (
                        <ChevronDown aria-hidden="true" className="size-4" />
                      )}
                      {expanded ? 'بستن' : 'جزئیات'}
                    </button>
                  </td>
                </tr>
                {expanded ? (
                  <tr id={detailId} className="border-t border-edge bg-surface-muted align-top">
                    <td colSpan={10} className="p-4">
                      <SkuDetail item={item} />
                    </td>
                  </tr>
                ) : null}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
