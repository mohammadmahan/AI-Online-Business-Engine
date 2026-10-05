'use client';

import { ChevronDown, ShieldQuestion } from 'lucide-react';
import { useState } from 'react';

import {
  CHANNEL_META,
  FULFILLMENT_STATUS_META,
  PAYMENT_STATUS_META,
  RISK_LEVEL_META,
} from '@/components/commerce/commerce-meta';
import { OrderDrawer } from '@/components/commerce/order-drawer';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatTimeUtc, formatToman } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Order } from '@/types/commerce';

/**
 * The dense orders table (D-171 §5.6).
 *
 * RTL and column-aligned, so it stays scannable; on narrow screens the wrapper
 * scrolls horizontally instead of reflowing the columns. Order id, WooCommerce
 * id, channel, integer-Toman total, payment, fulfillment and risk each get their
 * own column — nothing is collapsed into a composite that could hide a failed
 * payment behind a green-ish cell.
 *
 * Each row opens its detail drawer through a real `<button>` with
 * `aria-haspopup="dialog"`, so the drawer is reachable by keyboard and not by
 * hover alone.
 */
export function OrdersTable({
  orders,
  emptyMessage,
}: {
  orders: Order[];
  emptyMessage: string;
}) {
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selected = orders.find((order) => order.orderId === selectedId) ?? null;

  if (orders.length === 0) {
    return (
      <p className="flex items-center gap-2 rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
        <ShieldQuestion aria-hidden="true" className="size-4 shrink-0" />
        {emptyMessage}
      </p>
    );
  }

  return (
    <>
      <div className="overflow-x-auto rounded-[--radius-cp] border border-edge">
        <table className="w-full min-w-[1120px] border-collapse text-cp-label">
          <caption className="sr-only">
            فهرست سفارش‌ها با شناسه، مشتری، کانال، مبلغ به تومان، وضعیت پرداخت و تأمین، امتیاز
            ریسک و جزئیات
          </caption>
          <thead>
            <tr className="bg-surface-muted text-cp-caption text-ink-muted">
              <th scope="col" className="p-2 text-start font-medium">سفارش</th>
              <th scope="col" className="p-2 text-start font-medium">مشتری</th>
              <th scope="col" className="p-2 text-start font-medium">کانال</th>
              <th scope="col" className="p-2 text-start font-medium">مبلغ کل</th>
              <th scope="col" className="p-2 text-start font-medium">پرداخت</th>
              <th scope="col" className="p-2 text-start font-medium">تأمین</th>
              <th scope="col" className="p-2 text-start font-medium">ریسک</th>
              <th scope="col" className="p-2 text-start font-medium">زمان (UTC)</th>
              <th scope="col" className="p-2 text-start font-medium">جزئیات</th>
            </tr>
          </thead>
          <tbody>
            {orders.map((order) => {
              const payment = PAYMENT_STATUS_META[order.paymentStatus];
              const fulfillment = FULFILLMENT_STATUS_META[order.fulfillmentStatus];
              const risk = RISK_LEVEL_META[order.riskLevel];
              const channel = CHANNEL_META[order.channel];
              return (
                <tr key={order.orderId} className="border-t border-edge align-top">
                  <th scope="row" className="p-2 text-start font-normal">
                    <span dir="ltr" className="block font-mono text-cp-label text-ink">
                      {order.orderId}
                    </span>
                    <span className="mt-1 block text-cp-caption text-ink-muted">
                      Woo:{' '}
                      <span dir="ltr" className="font-mono">
                        {order.wooOrderId ?? '—'}
                      </span>
                    </span>
                  </th>
                  <td className="p-2 text-cp-label text-ink">{order.customerNameFa}</td>
                  <td className="p-2">
                    <ToneBadge
                      tone={channel.tone}
                      label={channel.label}
                      code={channel.code}
                      Icon={channel.Icon}
                    />
                  </td>
                  <td className="p-2 text-cp-label text-ink tabular-nums">
                    {formatToman(order.totalToman)}
                  </td>
                  <td className="p-2">
                    <ToneBadge
                      tone={payment.tone}
                      label={payment.label}
                      code={payment.code}
                      Icon={payment.Icon}
                    />
                  </td>
                  <td className="p-2">
                    <ToneBadge
                      tone={fulfillment.tone}
                      label={fulfillment.label}
                      code={fulfillment.code}
                      Icon={fulfillment.Icon}
                    />
                  </td>
                  <td className="p-2">
                    <ToneBadge
                      tone={risk.tone}
                      label={risk.label}
                      code={risk.code}
                      Icon={risk.Icon}
                      detail={`${order.riskScore}`}
                    />
                  </td>
                  <td className="p-2 text-cp-caption text-ink-muted">
                    <time dateTime={order.placedAtUtc} className="block tabular-nums">
                      ثبت: {formatTimeUtc(order.placedAtUtc)}
                    </time>
                    <time dateTime={order.lastUpdateUtc} className="mt-1 block tabular-nums">
                      آخرین به‌روزرسانی: {formatTimeUtc(order.lastUpdateUtc)}
                    </time>
                  </td>
                  <td className="p-2">
                    <button
                      type="button"
                      onClick={() => setSelectedId(order.orderId)}
                      aria-haspopup="dialog"
                      aria-label={`نمایش جزئیات، تاریخچه و گزارش پرداخت سفارش ${order.orderId}`}
                      className={cn(
                        'cp-target inline-flex items-center gap-1 rounded-[--radius-cp]',
                        'border border-edge-strong bg-surface px-2 py-1',
                        'text-cp-caption font-medium text-ink hover:bg-surface-muted',
                      )}
                    >
                      <ChevronDown aria-hidden="true" className="size-4" />
                      جزئیات
                    </button>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <OrderDrawer order={selected} onClose={() => setSelectedId(null)} />
    </>
  );
}
