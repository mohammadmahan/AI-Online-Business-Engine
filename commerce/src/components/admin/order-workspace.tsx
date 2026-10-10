'use client';

import { Loader2, Printer, Truck } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';

import type { OrderStatus } from '@/db/schema';
import { formatCountFa, formatDateTimeFa, formatMachineCode, formatToman } from '@/lib/format';
import {
  ORDER_STATUS_LABELS,
  canSetTracking,
  nextStatuses,
  transitionConfirmation,
} from '@/lib/order-rules';
import { cn } from '@/lib/utils';
import type { OrderListItem } from '@/server/repository';
import { setTrackingCodeAction, transitionOrderAction } from '@/server/actions/orders';
import { Modal } from '@/components/ui/dialog';
import { Badge, Card, CardHeader, Table, Td, Th, buttonClass, inputClass } from '@/components/ui/primitives';

/**
 * D-172 §2.3 — order list, status transitions and the tracking code.
 *
 * The dropdown offers ONLY the transitions `@/lib/order-rules` allows, and the
 * server re-checks the same map before writing. Every status change is then put
 * through a confirmation modal, because all of these transitions are one-way
 * and the roadmap requires a confirmation on every irreversible action
 * (cancellation additionally in the destructive style). Recording a tracking
 * code opens a validated modal rather than editing the cell inline, because the
 * roadmap makes that entry the trigger for the buyer notification — it
 * deserves an explicit confirm step.
 *
 * The SMS itself is a Phase 6 adapter and is NOT bound here; the panel says so
 * after a successful save instead of implying a message went out.
 */

type Message = { tone: 'ok' | 'error'; text: string };

export function OrderWorkspace({ orders }: { orders: OrderListItem[] }) {
  const [messages, setMessages] = useState<Record<string, Message>>({});
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [trackingOrderId, setTrackingOrderId] = useState<string | null>(null);
  const [trackingValue, setTrackingValue] = useState('');
  // A status change is confirmed before it is written: every transition in this
  // lifecycle is one-way, and the roadmap requires a confirmation on every
  // irreversible action (roadmap §UI/UX → merchant-panel-specific).
  const [pendingChange, setPendingChange] = useState<{
    orderId: string;
    status: OrderStatus;
    reference: string;
  } | null>(null);
  const [confirmBusy, setConfirmBusy] = useState(false);

  async function confirmStatusChange() {
    if (pendingChange === null) {
      return;
    }
    const { orderId, status } = pendingChange;
    setConfirmBusy(true);
    setBusy((current) => ({ ...current, [orderId]: true }));
    const response = await transitionOrderAction({ orderId, status });
    setConfirmBusy(false);
    setBusy((current) => ({ ...current, [orderId]: false }));
    setMessages((current) => ({
      ...current,
      [orderId]: response.ok
        ? { tone: 'ok', text: `وضعیت به «${ORDER_STATUS_LABELS[status]}» تغییر کرد.` }
        : { tone: 'error', text: response.message },
    }));
    // Closed on both outcomes: on success the change is recorded, on refusal the
    // server's message is already on the row — a modal left open would hide it.
    setPendingChange(null);
  }

  async function saveTracking() {
    if (trackingOrderId === null) {
      return;
    }
    const orderId = trackingOrderId;
    const response = await setTrackingCodeAction({ orderId, trackingCode: trackingValue });
    if (response.ok) {
      setMessages((current) => ({
        ...current,
        [orderId]: {
          tone: 'ok',
          text: 'کد رهگیری ثبت شد. پیامک اطلاع‌رسانی هنوز فعال نیست (فاز ۶).',
        },
      }));
      setTrackingOrderId(null);
      setTrackingValue('');
      return;
    }
    setMessages((current) => ({ ...current, [orderId]: { tone: 'error', text: response.message } }));
  }

  return (
    <Card>
      <CardHeader
        title="سفارش‌ها"
        description="تغییر وضعیت فقط در مسیرهای مجاز انجام می‌شود؛ فاکتور بسته‌بندی قابل چاپ است."
      />

      {orders.length === 0 ? (
        <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
          سفارشی ثبت نشده است.
        </p>
      ) : (
        <Table
          caption="فهرست سفارش‌ها"
          head={
            <tr>
              <Th>شمارهٔ سفارش</Th>
              <Th>مشتری</Th>
              <Th>وضعیت</Th>
              <Th>مبلغ کل</Th>
              <Th>اقلام</Th>
              <Th>تاریخ ثبت</Th>
              <Th>کد رهگیری</Th>
              <Th>عملیات</Th>
            </tr>
          }
        >
          {orders.map((order) => {
            const options = nextStatuses(order.status);
            const message = messages[order.id];
            return (
              <tr key={order.id}>
                <Td>
                  <span className="cp-code">{order.id.slice(0, 8)}</span>
                </Td>
                <Td>
                  {order.customerName}
                  <span className="block cp-code text-cp-caption text-ink-muted">
                    {order.customerPhone}
                  </span>
                </Td>
                <Td>
                  <Badge tone={order.status === 'CANCELLED' ? 'danger' : order.status === 'SHIPPED' ? 'success' : 'neutral'}>
                    {ORDER_STATUS_LABELS[order.status]} <span className="cp-code">{order.status}</span>
                  </Badge>
                </Td>
                <Td>{formatToman(order.totalAmount)}</Td>
                <Td>{formatCountFa(order.itemCount)}</Td>
                <Td>{formatDateTimeFa(order.createdAt)}</Td>
                <Td>
                  <span className="cp-code">{formatMachineCode(order.trackingCode)}</span>
                </Td>
                <Td>
                  <div className="flex flex-col gap-1">
                    {options.length === 0 ? (
                      <span className="text-cp-caption text-ink-muted">
                        وضعیت پایانی — تغییر مجاز نیست.
                      </span>
                    ) : (
                      <>
                        <label className="sr-only" htmlFor={`status-${order.id}`}>
                          تغییر وضعیت سفارش {order.id.slice(0, 8)}
                        </label>
                        <select
                          id={`status-${order.id}`}
                          className={inputClass}
                          value=""
                          disabled={busy[order.id] === true}
                          onChange={(event) => {
                            const value = event.target.value;
                            if (value.length > 0) {
                              setPendingChange({
                                orderId: order.id,
                                status: value as OrderStatus,
                                reference: order.id.slice(0, 8),
                              });
                            }
                          }}
                        >
                          <option value="">تغییر وضعیت…</option>
                          {options.map((status) => (
                            <option key={status} value={status}>
                              {ORDER_STATUS_LABELS[status]} ({status})
                            </option>
                          ))}
                        </select>
                      </>
                    )}

                    {canSetTracking(order.status) ? (
                      <button
                        type="button"
                        className={buttonClass.neutral}
                        onClick={() => {
                          setTrackingOrderId(order.id);
                          setTrackingValue(order.trackingCode ?? '');
                        }}
                      >
                        <Truck aria-hidden="true" size={14} /> ثبت کد رهگیری
                      </button>
                    ) : null}

                    <Link
                      href={`/admin/orders/${order.id}/slip`}
                      className={buttonClass.neutral}
                    >
                      <Printer aria-hidden="true" size={14} /> فاکتور بسته‌بندی
                    </Link>

                    {busy[order.id] === true ? (
                      <span className="flex items-center gap-1 text-cp-caption text-ink-muted">
                        <Loader2 aria-hidden="true" size={12} /> در حال ذخیره…
                      </span>
                    ) : null}
                    {message ? (
                      <span
                        role="status"
                        className={cn(
                          'text-cp-caption',
                          message.tone === 'ok' ? 'text-success' : 'text-danger',
                        )}
                      >
                        {message.text}
                      </span>
                    ) : null}
                  </div>
                </Td>
              </tr>
            );
          })}
        </Table>
      )}

      <Modal
        open={pendingChange !== null}
        onOpenChange={(open) => {
          if (!open) {
            setPendingChange(null);
          }
        }}
        title={
          pendingChange === null
            ? ''
            : `${transitionConfirmation(pendingChange.status).title} — سفارش ${pendingChange.reference}`
        }
        description="تغییر وضعیت سفارش پس از تأیید ثبت می‌شود."
      >
        {pendingChange === null ? null : (
          <>
            <p className="text-cp-label text-ink">
              {transitionConfirmation(pendingChange.status).body}
            </p>
            <p className="mt-2 flex flex-wrap items-center gap-2 text-cp-label">
              <span className="text-ink-muted">وضعیت جدید:</span>
              <Badge tone={transitionConfirmation(pendingChange.status).danger ? 'danger' : 'neutral'}>
                {ORDER_STATUS_LABELS[pendingChange.status]}{' '}
                <span className="cp-code">{pendingChange.status}</span>
              </Badge>
            </p>
            <div className="mt-4 flex gap-2">
              <button
                type="button"
                className={
                  transitionConfirmation(pendingChange.status).danger
                    ? buttonClass.danger
                    : buttonClass.primary
                }
                disabled={confirmBusy}
                onClick={() => void confirmStatusChange()}
              >
                تأیید و ثبت
              </button>
              <button
                type="button"
                className={buttonClass.neutral}
                onClick={() => setPendingChange(null)}
              >
                انصراف
              </button>
            </div>
          </>
        )}
      </Modal>

      <Modal
        open={trackingOrderId !== null}
        onOpenChange={(open) => {
          if (!open) {
            setTrackingOrderId(null);
          }
        }}
        title="ثبت کد رهگیری پستی"
        description="کد رهگیری ۸ تا ۲۴ نویسهٔ لاتین، رقم یا خط تیره است."
      >
        <label className="text-cp-label font-medium text-ink" htmlFor="tracking-code">
          کد رهگیری
        </label>
        <input
          id="tracking-code"
          className={cn(inputClass, 'cp-code mt-1')}
          dir="ltr"
          value={trackingValue}
          onChange={(event) => setTrackingValue(event.target.value)}
          placeholder="24IR1234567890"
        />
        <div className="mt-4 flex gap-2">
          <button type="button" className={buttonClass.primary} onClick={() => void saveTracking()}>
            ثبت کد
          </button>
          <button
            type="button"
            className={buttonClass.neutral}
            onClick={() => setTrackingOrderId(null)}
          >
            انصراف
          </button>
        </div>
      </Modal>
    </Card>
  );
}
