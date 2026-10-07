'use client';

import { CalendarRange, Filter, ListFilter, X } from 'lucide-react';
import { useState } from 'react';

import {
  FULFILLMENT_STATUS_META,
  PAYMENT_STATUS_META,
} from '@/components/commerce/commerce-meta';
import { cn } from '@/lib/utils';
import type { FulfillmentStatus, Order, PaymentStatus } from '@/types/commerce';

const PAYMENT_STATUSES: PaymentStatus[] = ['PAID', 'PENDING_PAYMENT', 'FAILED', 'REFUNDED'];
const FULFILLMENT_STATUSES: FulfillmentStatus[] = [
  'UNFULFILLED',
  'PROCESSING',
  'SHIPPED',
  'DELIVERED',
  'CANCELLED',
];

/** Filters are a client concern: they never change what the server rendered. */
export interface OrderFilterState {
  /** Free-text query matched against order id, WooCommerce id and customer name. */
  query: string;
  payments: PaymentStatus[];
  fulfillments: FulfillmentStatus[];
  /** Raw `YYYY-MM-DD` strings — parsed strictly, so an empty string never widens the range. */
  fromDate: string;
  toDate: string;
}

export const EMPTY_ORDER_FILTERS: OrderFilterState = {
  query: '',
  payments: [],
  fulfillments: [],
  fromDate: '',
  toDate: '',
};

const DATE_RE = /^\d{4}-\d{2}-\d{2}$/;

/**
 * Parse the placed-at date range.
 *
 * A malformed or inverted range is reported as `invalid` instead of being
 * silently ignored: applying "no filter" to a range the operator typed would
 * show orders that look like they matched it (fail-closed, D-171 §2.2).
 * Order instants are ISO-8601 UTC, so the date part is compared as text.
 */
export function parsePlacedRange(filters: OrderFilterState): {
  from: string | null;
  to: string | null;
  invalid: boolean;
} {
  const fromRaw = filters.fromDate.trim();
  const toRaw = filters.toDate.trim();
  const badFrom = fromRaw !== '' && !DATE_RE.test(fromRaw);
  const badTo = toRaw !== '' && !DATE_RE.test(toRaw);
  const from = fromRaw === '' || badFrom ? null : fromRaw;
  const to = toRaw === '' || badTo ? null : toRaw;
  const invalid = badFrom || badTo || (from !== null && to !== null && from > to);
  return { from, to, invalid };
}

/** Apply the filter state to a row list. An invalid range yields no rows. */
export function applyOrderFilters(orders: Order[], filters: OrderFilterState): Order[] {
  const { from, to, invalid } = parsePlacedRange(filters);
  if (invalid) return [];

  const needle = filters.query.trim().toLowerCase();
  return orders.filter((order) => {
    if (filters.payments.length > 0 && !filters.payments.includes(order.paymentStatus)) {
      return false;
    }
    if (
      filters.fulfillments.length > 0 &&
      !filters.fulfillments.includes(order.fulfillmentStatus)
    ) {
      return false;
    }
    const placedDate = order.placedAtUtc.slice(0, 10);
    if (from !== null && placedDate < from) return false;
    if (to !== null && placedDate > to) return false;
    if (needle.length > 0) {
      const haystack = [
        order.orderId,
        order.wooOrderId === null ? '' : String(order.wooOrderId),
        order.customerNameFa,
      ]
        .join(' ')
        .toLowerCase();
      if (!haystack.includes(needle)) return false;
    }
    return true;
  });
}

/**
 * Search & filters (D-171 §5.6): order id / customer search, payment status,
 * fulfillment status and a placed-at date range.
 *
 * Filtering is purely presentational — it cannot pay, ship, refund or issue
 * anything. The shown/total count and the active-filter count are stated in
 * words as well as visually, so the operator always knows what is hidden.
 */
export function OrderFilters({
  filters,
  onChange,
  shown,
  total,
}: {
  filters: OrderFilterState;
  onChange: (next: OrderFilterState) => void;
  shown: number;
  total: number;
}) {
  const [open, setOpen] = useState(false);

  const activeCount =
    filters.payments.length +
    filters.fulfillments.length +
    (filters.query.trim() ? 1 : 0) +
    (filters.fromDate.trim() || filters.toDate.trim() ? 1 : 0);

  const range = parsePlacedRange(filters);

  const togglePayment = (status: PaymentStatus) => {
    const next = filters.payments.includes(status)
      ? filters.payments.filter((value) => value !== status)
      : [...filters.payments, status];
    onChange({ ...filters, payments: next });
  };

  const toggleFulfillment = (status: FulfillmentStatus) => {
    const next = filters.fulfillments.includes(status)
      ? filters.fulfillments.filter((value) => value !== status)
      : [...filters.fulfillments, status];
    onChange({ ...filters, fulfillments: next });
  };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={() => setOpen((value) => !value)}
          aria-expanded={open}
          aria-controls="orders-filter-panel"
          className={cn(
            'cp-target inline-flex items-center gap-2 rounded-[--radius-cp]',
            'border border-edge-strong bg-surface px-3 py-2',
            'text-cp-label font-medium text-ink hover:bg-surface-muted',
          )}
        >
          <Filter aria-hidden="true" className="size-4" />
          فیلترها
          {activeCount > 0 ? (
            <span className="rounded-full bg-primary px-2 text-cp-caption font-semibold text-on-primary tabular-nums">
              {activeCount}
            </span>
          ) : null}
        </button>

        <label className="flex items-center gap-2">
          <span className="sr-only">جست‌وجو بر اساس شناسهٔ سفارش، شناسهٔ ووکامرس یا نام مشتری</span>
          <input
            type="search"
            value={filters.query}
            onChange={(event) => onChange({ ...filters, query: event.target.value })}
            placeholder="جست‌وجو در شناسه یا نام مشتری…"
            className={cn(
              'cp-target w-64 max-w-full rounded-[--radius-cp] border border-edge-strong',
              'bg-surface px-3 py-2 text-cp-label text-ink placeholder:text-ink-muted',
            )}
          />
        </label>

        <p className="text-cp-caption text-ink-muted" role="status">
          نمایش <span className="tabular-nums">{shown}</span> از{' '}
          <span className="tabular-nums">{total}</span> سفارش
        </p>

        {activeCount > 0 ? (
          <button
            type="button"
            onClick={() => onChange(EMPTY_ORDER_FILTERS)}
            className="cp-target inline-flex items-center gap-1 rounded-[--radius-cp] px-2 py-1 text-cp-caption font-medium text-primary hover:underline"
          >
            <X aria-hidden="true" className="size-4" />
            پاک‌کردن فیلترها
          </button>
        ) : null}
      </div>

      {open ? (
        <div
          id="orders-filter-panel"
          className="flex flex-col gap-4 rounded-[--radius-cp] border border-edge bg-surface-muted p-3"
        >
          <fieldset className="flex flex-col gap-2">
            <legend className="flex items-center gap-2 text-cp-label font-semibold text-ink">
              <ListFilter aria-hidden="true" className="size-4" />
              وضعیت پرداخت
            </legend>
            <div className="flex flex-wrap gap-2">
              {PAYMENT_STATUSES.map((status) => {
                const meta = PAYMENT_STATUS_META[status];
                const active = filters.payments.includes(status);
                return (
                  <button
                    key={status}
                    type="button"
                    onClick={() => togglePayment(status)}
                    aria-pressed={active}
                    className={cn(
                      'cp-target rounded-full border px-3 py-1 text-cp-caption font-medium',
                      active
                        ? 'border-primary bg-primary text-on-primary'
                        : 'border-edge-strong bg-surface text-ink hover:bg-surface-muted',
                    )}
                  >
                    {meta.label} ({meta.code})
                  </button>
                );
              })}
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-2">
            <legend className="text-cp-label font-semibold text-ink">وضعیت تأمین</legend>
            <div className="flex flex-wrap gap-2">
              {FULFILLMENT_STATUSES.map((status) => {
                const meta = FULFILLMENT_STATUS_META[status];
                const active = filters.fulfillments.includes(status);
                return (
                  <button
                    key={status}
                    type="button"
                    onClick={() => toggleFulfillment(status)}
                    aria-pressed={active}
                    className={cn(
                      'cp-target rounded-full border px-3 py-1 text-cp-caption font-medium',
                      active
                        ? 'border-primary bg-primary text-on-primary'
                        : 'border-edge-strong bg-surface text-ink hover:bg-surface-muted',
                    )}
                  >
                    {meta.label} ({meta.code})
                  </button>
                );
              })}
            </div>
          </fieldset>

          <fieldset className="flex flex-col gap-2">
            <legend className="flex items-center gap-2 text-cp-label font-semibold text-ink">
              <CalendarRange aria-hidden="true" className="size-4" />
              بازهٔ زمان ثبت (UTC)
            </legend>
            <div className="flex flex-wrap items-end gap-3">
              <label className="flex flex-col gap-1">
                <span className="text-cp-caption text-ink-muted">از تاریخ</span>
                <input
                  type="date"
                  value={filters.fromDate}
                  onChange={(event) => onChange({ ...filters, fromDate: event.target.value })}
                  className={cn(
                    'cp-target rounded-[--radius-cp] border border-edge-strong',
                    'bg-surface px-3 py-2 text-cp-label text-ink tabular-nums',
                  )}
                />
              </label>
              <label className="flex flex-col gap-1">
                <span className="text-cp-caption text-ink-muted">تا تاریخ</span>
                <input
                  type="date"
                  value={filters.toDate}
                  onChange={(event) => onChange({ ...filters, toDate: event.target.value })}
                  className={cn(
                    'cp-target rounded-[--radius-cp] border border-edge-strong',
                    'bg-surface px-3 py-2 text-cp-label text-ink tabular-nums',
                  )}
                />
              </label>
            </div>
            {range.invalid ? (
              <p
                role="alert"
                className="rounded-[--radius-cp] border border-danger bg-surface p-2 text-cp-caption text-danger"
              >
                بازهٔ تاریخ نامعتبر است (قالب نادرست یا تاریخ شروع بعد از پایان)؛ تا اصلاح آن هیچ
                سفارشی نمایش داده نمی‌شود.
              </p>
            ) : null}
          </fieldset>
        </div>
      ) : null}
    </div>
  );
}
