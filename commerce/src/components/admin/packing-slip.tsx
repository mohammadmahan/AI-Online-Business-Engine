import { formatCountFa, formatDateFa, formatMachineCode, formatToman } from '@/lib/format';
import { ORDER_STATUS_LABELS, computeTotals } from '@/lib/order-rules';
import type { OrderDetail } from '@/server/repository';
import { Banner } from '@/components/ui/primitives';

/**
 * D-172 §2.3 — printable packing slip / invoice (فاکتور استاندارد بسته‌بندی).
 *
 * A server component: it renders the stored order, computes the totals from the
 * lines, and prints. The arithmetic is the pure `computeTotals`, shared with the
 * order list, and when the recomputed payable disagrees with the stored total the
 * slip SAYS SO at the top — a printed document must never quietly show a number
 * that does not reconcile.
 *
 * Print rules live in `globals.css` (`.cp-no-print`, `.cp-slip`): the browser's
 * print dialog produces the slip alone, without navigation or buttons.
 */
export function PackingSlip({ order }: { order: OrderDetail }) {
  const totals = computeTotals(order);

  return (
    <article className="cp-slip rounded-[--radius-cp] border border-edge bg-surface p-6">
      <header className="flex flex-wrap items-start justify-between gap-4 border-b border-edge pb-4">
        <div>
          <h1 className="text-cp-heading font-bold text-ink">فاکتور بسته‌بندی</h1>
          <p className="mt-1 text-cp-label text-ink-muted">
            شمارهٔ سفارش: <span className="cp-code">{order.id}</span>
          </p>
          <p className="text-cp-label text-ink-muted">
            تاریخ ثبت: {formatDateFa(order.createdAt)}
          </p>
        </div>
        <div className="text-cp-label">
          <p className="font-semibold text-ink">وضعیت سفارش</p>
          <p className="text-ink-muted">
            {ORDER_STATUS_LABELS[order.status]} <span className="cp-code">{order.status}</span>
          </p>
          <p className="mt-2 font-semibold text-ink">کد رهگیری</p>
          <p className="cp-code text-ink-muted">{formatMachineCode(order.trackingCode)}</p>
        </div>
      </header>

      {!totals.consistent ? (
        <div className="mt-4">
          <Banner tone="danger" title="مبلغ ثبت‌شدهٔ سفارش با جمع اقلام هم‌خوان نیست">
            جمع محاسبه‌شده: {formatToman(totals.payable)} — مبلغ ثبت‌شده:{' '}
            {formatToman(totals.storedTotal)}. پیش از ارسال، این اختلاف را در سفارش بررسی کنید.
          </Banner>
        </div>
      ) : null}

      <section className="mt-4 grid gap-4 sm:grid-cols-2">
        <div>
          <h2 className="text-cp-label font-semibold text-ink">گیرنده</h2>
          <p className="text-cp-label text-ink">{order.customerName}</p>
          <p className="cp-code text-cp-label text-ink-muted">{order.customerPhone}</p>
          <p className="mt-1 text-cp-label text-ink">{order.shippingAddress}</p>
          <p className="text-cp-label text-ink-muted">
            کد پستی: <span className="cp-code">{order.postalCode}</span>
          </p>
        </div>
        <div>
          <h2 className="text-cp-label font-semibold text-ink">پرداخت</h2>
          <p className="text-cp-label text-ink-muted">
            مرجع پرداخت: <span className="cp-code">{formatMachineCode(order.paymentRefId)}</span>
          </p>
          <p className="text-cp-caption text-ink-muted">
            مبالغ به تومان و عدد صحیح ثبت می‌شوند (D-010).
          </p>
        </div>
      </section>

      <table className="mt-6 w-full border-collapse text-cp-label">
        <caption className="sr-only">اقلام سفارش</caption>
        <thead className="bg-surface-muted">
          <tr>
            <th scope="col" className="border-b border-edge px-3 py-2 text-start">
              ردیف
            </th>
            <th scope="col" className="border-b border-edge px-3 py-2 text-start">
              کالا
            </th>
            <th scope="col" className="border-b border-edge px-3 py-2 text-start">
              کد کالا
            </th>
            <th scope="col" className="border-b border-edge px-3 py-2 text-start">
              سایز / رنگ
            </th>
            <th scope="col" className="border-b border-edge px-3 py-2 text-start">
              تعداد
            </th>
            <th scope="col" className="border-b border-edge px-3 py-2 text-start">
              قیمت واحد
            </th>
            <th scope="col" className="border-b border-edge px-3 py-2 text-start">
              جمع
            </th>
          </tr>
        </thead>
        <tbody>
          {order.items.map((item, index) => (
            <tr key={item.id}>
              <td className="border-b border-edge px-3 py-2">{formatCountFa(index + 1)}</td>
              <td className="border-b border-edge px-3 py-2">{item.productTitle}</td>
              <td className="border-b border-edge px-3 py-2">
                <span className="cp-code">{item.sku}</span>
              </td>
              <td className="border-b border-edge px-3 py-2">
                <span className="cp-code">{item.size}</span> / {item.colorName}
              </td>
              <td className="border-b border-edge px-3 py-2">{formatCountFa(item.quantity)}</td>
              <td className="border-b border-edge px-3 py-2">{formatToman(item.unitPrice)}</td>
              <td className="border-b border-edge px-3 py-2">
                {formatToman(item.unitPrice * item.quantity)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>

      <section className="mt-4 flex justify-end">
        <dl className="w-full max-w-sm text-cp-label">
          <div className="flex justify-between border-b border-edge py-1">
            <dt className="text-ink-muted">جمع اقلام</dt>
            <dd className="text-ink">{formatToman(totals.itemsTotal)}</dd>
          </div>
          <div className="flex justify-between border-b border-edge py-1">
            <dt className="text-ink-muted">تخفیف</dt>
            <dd className="text-ink">− {formatToman(totals.discountAmount)}</dd>
          </div>
          <div className="flex justify-between border-b border-edge py-1">
            <dt className="text-ink-muted">هزینهٔ ارسال</dt>
            <dd className="text-ink">{formatToman(totals.shippingAmount)}</dd>
          </div>
          <div className="flex justify-between py-2 text-cp-body font-bold">
            <dt className="text-ink">قابل پرداخت</dt>
            <dd className="text-ink">{formatToman(totals.payable)}</dd>
          </div>
        </dl>
      </section>

      <footer className="mt-6 border-t border-edge pt-3 text-cp-caption text-ink-muted">
        این برگه برای بسته‌بندی و ارسال چاپ می‌شود. مشخصات تماس خریدار فقط در همین برگه استفاده
        می‌شود و در هیچ گزارش یا اشتراکی منتشر نمی‌شود (D-114/D-124).
      </footer>
    </article>
  );
}
