'use client';

import { Receipt, ScrollText, ShieldAlert, Truck, X } from 'lucide-react';
import { useEffect, useRef } from 'react';

import {
  CHANNEL_META,
  FULFILLMENT_STATUS_META,
  LIFECYCLE_STATE_META,
  PAYMENT_STATUS_META,
  RISK_LEVEL_META,
  SETTLEMENT_STATE_META,
} from '@/components/commerce/commerce-meta';
import { ToneBadge } from '@/components/ui/tone-badge';
import { formatNumber, formatTimeUtc, formatToman } from '@/lib/format';
import { cn } from '@/lib/utils';
import type { Order } from '@/types/commerce';

const AUDIT_OUTCOME_META = {
  OK: { tone: 'success', label: 'موفق', code: 'OK' },
  FAILED: { tone: 'danger', label: 'ناموفق', code: 'FAILED' },
  PENDING: { tone: 'warning', label: 'در انتظار', code: 'PENDING' },
} as const;

const RECEIPT_KIND_META = {
  ISSUED: { tone: 'success', label: 'رسید صادرشده', code: 'ISSUED' },
  REFUND: { tone: 'warning', label: 'رسید بازپرداخت', code: 'REFUND' },
} as const;

/**
 * Order detail drawer (D-171 §5.6).
 *
 * A native `<dialog>` is used rather than a hand-rolled overlay: focus
 * trapping, Escape-to-close and background inertness come from the platform,
 * so keyboard and screen-reader behaviour does not depend on our JavaScript
 * (same precedent as the HITL ticket and gate-audit drawers).
 *
 * The drawer is READ-ONLY and says so. It shows:
 *   - items bound to canonical SKUs with integer Toman line totals (D-010);
 *   - the D-081 status history, each transition with its D-121 trace;
 *   - the payment gateway log MASKED by construction (D-114/D-124): audit
 *     entries carry `GW-****NNNN` references — never a PAN, an auth code or a
 *     gateway key;
 *   - shipping with provider UNSELECTED (open decision 11);
 *   - D-084 receipts, integer Toman only.
 */
export function OrderDrawer({ order, onClose }: { order: Order | null; onClose: () => void }) {
  const dialogRef = useRef<HTMLDialogElement>(null);

  useEffect(() => {
    const dialog = dialogRef.current;
    if (!dialog) return;
    if (order && !dialog.open) dialog.showModal();
    if (!order && dialog.open) dialog.close();
  }, [order]);

  if (!order) return null;

  const payment = PAYMENT_STATUS_META[order.paymentStatus];
  const fulfillment = FULFILLMENT_STATUS_META[order.fulfillmentStatus];
  const risk = RISK_LEVEL_META[order.riskLevel];
  const settlement = SETTLEMENT_STATE_META[order.settlement];
  const channel = CHANNEL_META[order.channel];

  return (
    <dialog
      ref={dialogRef}
      onClose={onClose}
      onCancel={onClose}
      aria-labelledby="order-drawer-title"
      className={cn(
        'm-0 h-dvh max-h-none w-full max-w-2xl bg-surface text-ink',
        'ms-auto me-0 p-0 backdrop:bg-canvas/80',
        'border-s border-edge',
      )}
    >
      <div className="flex h-full flex-col">
        <header className="flex items-start justify-between gap-3 border-b border-edge p-4">
          <div className="flex flex-col gap-2">
            <div className="flex flex-wrap items-center gap-2">
              <ToneBadge
                tone={payment.tone}
                label={payment.label}
                code={payment.code}
                Icon={payment.Icon}
              />
              <ToneBadge
                tone={fulfillment.tone}
                label={fulfillment.label}
                code={fulfillment.code}
                Icon={fulfillment.Icon}
              />
              <ToneBadge tone={risk.tone} label={risk.label} code={risk.code} Icon={risk.Icon} />
            </div>
            <h2 id="order-drawer-title" className="text-cp-heading font-semibold text-ink">
              <span dir="ltr" className="font-mono">
                {order.orderId}
              </span>{' '}
              · {order.customerNameFa}
            </h2>
            <p className="flex flex-wrap items-center gap-2 text-cp-caption text-ink-muted">
              <ToneBadge
                tone={channel.tone}
                label={channel.label}
                code={channel.code}
                Icon={channel.Icon}
              />
              <span>
                ثبت:{' '}
                <time dateTime={order.placedAtUtc} className="tabular-nums">
                  {formatTimeUtc(order.placedAtUtc)}
                </time>{' '}
                UTC
              </span>
              <span>
                WooCommerce:{' '}
                <span dir="ltr" className="font-mono">
                  {order.wooOrderId ?? '—'}
                </span>
              </span>
            </p>
          </div>

          <button
            type="button"
            onClick={onClose}
            className={cn(
              'cp-target inline-flex items-center gap-1 rounded-[--radius-cp]',
              'border border-edge-strong bg-surface px-2 py-1',
              'text-cp-caption font-medium text-ink hover:bg-surface-muted',
            )}
          >
            <X aria-hidden="true" className="size-4" />
            بستن
          </button>
        </header>

        <div className="flex flex-1 flex-col gap-5 overflow-y-auto p-4">
          <section className="flex flex-col gap-2" aria-label="اقلام سفارش">
            <h3 className="text-cp-label font-semibold text-ink">اقلام (SKU کاننیکال)</h3>
            <div className="overflow-x-auto rounded-[--radius-cp] border border-edge">
              <table className="w-full border-collapse text-cp-caption">
                <caption className="sr-only">
                  اقلام سفارش {order.orderId} با SKU، تعداد و مبلغ خط، به تومان
                </caption>
                <thead>
                  <tr className="bg-surface-muted text-ink-muted">
                    <th scope="col" className="p-2 text-start font-medium">SKU</th>
                    <th scope="col" className="p-2 text-start font-medium">عنوان</th>
                    <th scope="col" className="p-2 text-start font-medium">تعداد</th>
                    <th scope="col" className="p-2 text-start font-medium">قیمت واحد</th>
                    <th scope="col" className="p-2 text-start font-medium">جمع خط</th>
                  </tr>
                </thead>
                <tbody>
                  {order.items.map((item) => (
                    <tr key={item.sku} className="border-t border-edge">
                      <td className="p-2 font-mono text-ink" dir="ltr">
                        {item.sku}
                      </td>
                      <td className="p-2 text-ink">{item.titleFa}</td>
                      <td className="p-2 text-ink tabular-nums">{formatNumber(item.quantity)}</td>
                      <td className="p-2 text-ink tabular-nums">{formatToman(item.unitPriceToman)}</td>
                      <td className="p-2 text-ink tabular-nums">{formatToman(item.lineTotalToman)}</td>
                    </tr>
                  ))}
                </tbody>
                <tfoot>
                  <tr className="border-t border-edge-strong bg-surface-muted">
                    <th scope="row" colSpan={4} className="p-2 text-start font-semibold text-ink">
                      جمع کل (عدد صحیح تومان)
                    </th>
                    <td className="p-2 font-semibold text-ink tabular-nums">
                      {formatToman(order.totalToman)}
                    </td>
                  </tr>
                </tfoot>
              </table>
            </div>
          </section>

          <section className="flex flex-col gap-2" aria-label="تاریخچه وضعیت">
            <h3 className="flex items-center gap-2 text-cp-label font-semibold text-ink">
              <ScrollText aria-hidden="true" className="size-4" />
              تاریخچه‌ی وضعیت (D-081) با رد D-121
            </h3>
            <ol className="flex flex-col gap-2">
              {order.history.map((entry) => {
                const meta = LIFECYCLE_STATE_META[entry.state];
                return (
                  <li
                    key={`${entry.state}-${entry.atUtc}`}
                    className="flex flex-col gap-1 rounded-[--radius-cp] border border-edge bg-surface-muted p-2"
                  >
                    <div className="flex flex-wrap items-center gap-2">
                      <ToneBadge
                        tone={meta.tone}
                        label={meta.label}
                        code={meta.code}
                        Icon={meta.Icon}
                      />
                      <time dateTime={entry.atUtc} className="text-cp-caption text-ink-muted tabular-nums">
                        {formatTimeUtc(entry.atUtc)} UTC
                      </time>
                      <span className="font-mono text-cp-caption text-ink-muted" dir="ltr">
                        {entry.traceId}
                      </span>
                    </div>
                    <p className="text-cp-caption text-ink">{entry.noteFa}</p>
                  </li>
                );
              })}
            </ol>
          </section>

          <section className="flex flex-col gap-2" aria-label="گزارش درگاه پرداخت (ماسک‌شده)">
            <h3 className="text-cp-label font-semibold text-ink">
              گزارش درگاه پرداخت — ماسک‌شده (D-114/D-124)
            </h3>
            <div className="overflow-x-auto rounded-[--radius-cp] border border-edge">
              <table className="w-full border-collapse text-cp-caption">
                <caption className="sr-only">
                  رخدادهای درگاه پرداخت سفارش {order.orderId}؛ مرجع هر رخداد ماسک‌شده است
                </caption>
                <thead>
                  <tr className="bg-surface-muted text-ink-muted">
                    <th scope="col" className="p-2 text-start font-medium">زمان (UTC)</th>
                    <th scope="col" className="p-2 text-start font-medium">رخداد</th>
                    <th scope="col" className="p-2 text-start font-medium">نتیجه</th>
                    <th scope="col" className="p-2 text-start font-medium">مرجع ماسک‌شده</th>
                    <th scope="col" className="p-2 text-start font-medium">مبلغ</th>
                    <th scope="col" className="p-2 text-start font-medium">رد (D-121)</th>
                  </tr>
                </thead>
                <tbody>
                  {order.paymentAudit.map((entry) => {
                    const outcome = AUDIT_OUTCOME_META[entry.outcome];
                    return (
                      <tr key={`${entry.outcome}-${entry.atUtc}`} className="border-t border-edge align-top">
                        <td className="p-2 text-ink-muted tabular-nums">
                          <time dateTime={entry.atUtc}>{formatTimeUtc(entry.atUtc)}</time>
                        </td>
                        <td className="p-2 text-ink">{entry.eventFa}</td>
                        <td className="p-2">
                          <ToneBadge tone={outcome.tone} label={outcome.label} code={outcome.code} />
                        </td>
                        <td className="p-2 font-mono text-ink" dir="ltr">
                          {entry.gatewayRefMasked}
                        </td>
                        <td className="p-2 text-ink tabular-nums">{formatToman(entry.amountToman)}</td>
                        <td className="p-2 font-mono text-ink-muted" dir="ltr">
                          {entry.traceId}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="flex items-start gap-2 rounded-[--radius-cp] border border-edge-strong bg-surface-muted p-2 text-cp-caption text-ink-muted">
              <ShieldAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
              این گزارش کاملاً ماسک‌شده است: هیچ PAN، کد تأیید یا کلید درگاهی — نه در داده و نه در
              این نما — وجود ندارد (D-114/D-124).
            </p>
          </section>

          <section className="flex flex-col gap-2" aria-label="ارسال و تسویه">
            <h3 className="flex items-center gap-2 text-cp-label font-semibold text-ink">
              <Truck aria-hidden="true" className="size-4" />
              ارسال و تسویه
            </h3>
            <div className="grid gap-2 text-cp-label sm:grid-cols-2">
              <div className="flex flex-col gap-1 rounded-[--radius-cp] border border-edge p-2">
                <span className="text-cp-caption text-ink-muted">ارائه‌دهنده‌ی ارسال</span>
                <ToneBadge tone="neutral" label="انتخاب‌نشده" code="UNSELECTED" Icon={Truck} />
                <p className="text-cp-caption text-ink-muted">
                  {order.shipping.statusFa} — ارائه‌دهنده‌ی ارسال هنوز انتخاب نشده است (تصمیم باز
                  ۱۱).
                </p>
                <p className="text-cp-caption text-ink-muted">
                  کد رهگیری:{' '}
                  {order.shipping.trackingNumber !== null ? (
                    <span dir="ltr" className="font-mono text-ink">
                      {order.shipping.trackingNumber}
                    </span>
                  ) : (
                    '—'
                  )}
                </p>
              </div>
              <div className="flex flex-col gap-1 rounded-[--radius-cp] border border-edge p-2">
                <span className="text-cp-caption text-ink-muted">وضعیت تسویه</span>
                <ToneBadge
                  tone={settlement.tone}
                  label={settlement.label}
                  code={settlement.code}
                  Icon={settlement.Icon}
                />
                <p className="text-cp-caption text-ink-muted">
                  پرداخت در حالت تمرینی (DRY-RUN) است؛ هیچ مسیر پرداخت واقعی در این نما وجود ندارد
                  (تصمیم باز ۱۰).
                </p>
              </div>
            </div>
          </section>

          <section className="flex flex-col gap-2" aria-label="رسیدهای D-084">
            <h3 className="flex items-center gap-2 text-cp-label font-semibold text-ink">
              <Receipt aria-hidden="true" className="size-4" />
              رسیدها (D-084)
            </h3>
            {order.receipts.length === 0 ? (
              <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-2 text-cp-caption text-ink-muted">
                برای این سفارش رسیدی صادر نشده است؛ رسید فقط برای سفارش‌های تکمیل‌شده یا
                بازپرداخت‌شده وجود دارد.
              </p>
            ) : (
              <ul className="flex flex-col gap-2">
                {order.receipts.map((receipt) => {
                  const kind = RECEIPT_KIND_META[receipt.kind];
                  return (
                    <li
                      key={receipt.receiptId}
                      className="flex flex-wrap items-center gap-2 rounded-[--radius-cp] border border-edge bg-surface-muted p-2 text-cp-caption"
                    >
                      <ToneBadge tone={kind.tone} label={kind.label} code={kind.code} />
                      <span className="font-mono text-ink" dir="ltr">
                        {receipt.receiptId}
                      </span>
                      <time dateTime={receipt.issuedAtUtc} className="text-ink-muted tabular-nums">
                        {formatTimeUtc(receipt.issuedAtUtc)} UTC
                      </time>
                      <span className="text-ink tabular-nums">{formatToman(receipt.totalToman)}</span>
                    </li>
                  );
                })}
              </ul>
            )}
          </section>

          <p className="rounded-[--radius-cp] border border-edge-strong bg-surface-muted p-2 text-cp-caption text-ink-muted">
            این نما فقط‌خواندنی است: هیچ خرید، ارسال، بازپرداخت یا صدور فاکتوری از اینجا انجام
            نمی‌شود. هر کنش واقعی نیازمند توکن یک‌بارمصرف مالک (D-146) و مسیر نوشتن امضاشده
            (D-171 §6) است.
          </p>
        </div>
      </div>
    </dialog>
  );
}
