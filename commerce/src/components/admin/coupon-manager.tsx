'use client';

import { useState } from 'react';

import type { CouponCreatePayload, CouponView } from '@/contracts/promotions';
import {
  COUPON_STATE_LABELS,
  COUPON_STATE_TONE,
  describeDiscount,
} from '@/lib/coupon-rules';
import { formatCountFa, formatDateFa, formatToman } from '@/lib/format';
import { cn } from '@/lib/utils';
import { createCouponAction, setCouponActiveAction } from '@/server/actions/coupons';
import { Banner, Badge, Card, CardHeader, Field, Table, Td, Th, buttonClass, inputClass } from '@/components/ui/primitives';

/**
 * D-172 §2.4 — promotions & discounts.
 *
 * Percentage vs fixed amount is a single control rather than two forms, and the
 * value's meaning follows the choice (٪ or تومان) so a merchant cannot enter a
 * "500" percentage. The displayed state is derived by `@/lib/coupon-rules`, so an
 * expired or exhausted coupon can never look active here.
 */

type Result =
  | { kind: 'idle' }
  | { kind: 'ok'; code: string }
  | { kind: 'error'; message: string; field?: string };

export function CouponManager({ coupons }: { coupons: CouponView[] }) {
  const [code, setCode] = useState('');
  const [discountType, setDiscountType] = useState<'PERCENT' | 'FIXED'>('PERCENT');
  const [discountValue, setDiscountValue] = useState<number | ''>('');
  const [minSpend, setMinSpend] = useState<number | ''>('');
  const [expiresAt, setExpiresAt] = useState('');
  const [usageLimit, setUsageLimit] = useState<number | ''>('');
  const [description, setDescription] = useState('');
  const [result, setResult] = useState<Result>({ kind: 'idle' });
  const [busy, setBusy] = useState<Record<string, boolean>>({});
  const [rowMessages, setRowMessages] = useState<Record<string, string>>({});

  async function submit() {
    const payload: CouponCreatePayload = {
      code,
      discountType,
      discountValue: discountValue === '' ? Number.NaN : Number(discountValue),
      minSpend: minSpend === '' ? 0 : Number(minSpend),
      // A datetime-local value is local time; the service converts it to an
      // instant and refuses anything that is not a real future date.
      expiresAt: expiresAt === '' ? null : new Date(expiresAt).toISOString(),
      usageLimit: usageLimit === '' ? null : Number(usageLimit),
      description: description === '' ? null : description,
      isActive: true,
    };
    const response = await createCouponAction(payload);
    if (response.ok) {
      setResult({ kind: 'ok', code: response.data.code });
      setCode('');
      setDiscountValue('');
      setMinSpend('');
      setExpiresAt('');
      setUsageLimit('');
      setDescription('');
      return;
    }
    setResult({ kind: 'error', message: response.message, field: response.field });
  }

  async function toggle(coupon: CouponView) {
    setBusy((current) => ({ ...current, [coupon.id]: true }));
    const response = await setCouponActiveAction({
      couponId: coupon.id,
      isActive: coupon.state === 'INACTIVE',
    });
    setBusy((current) => ({ ...current, [coupon.id]: false }));
    setRowMessages((current) => ({
      ...current,
      [coupon.id]: response.ok
        ? coupon.state === 'INACTIVE'
          ? 'کد تخفیف فعال شد.'
          : 'کد تخفیف غیرفعال شد.'
        : response.message,
    }));
  }

  return (
    <div className="flex flex-col gap-4">
      {result.kind === 'ok' ? (
        <Banner tone="success" title="کد تخفیف ثبت شد">
          کد <span className="cp-code">{result.code}</span> ساخته شد.
        </Banner>
      ) : null}
      {result.kind === 'error' ? (
        <Banner tone="danger" title="ثبت کد تخفیف انجام نشد">
          {result.message}
          {result.field ? <span className="cp-code"> [{result.field}]</span> : null}
        </Banner>
      ) : null}

      <Card>
        <CardHeader title="کد تخفیف جدید" description="درصدی یا مبلغ ثابت، با تاریخ انقضا و حداقل خرید." />
        <div className="grid gap-4 md:grid-cols-3">
          <Field label="کد" htmlFor="coupon-code" required hint="حروف بزرگ لاتین و رقم، مثال: NOROOZ1405">
            <input
              id="coupon-code"
              className={cn(inputClass, 'cp-code')}
              dir="ltr"
              value={code}
              onChange={(event) => setCode(event.target.value.toUpperCase())}
            />
          </Field>
          <Field label="نوع تخفیف" htmlFor="coupon-type" required>
            <select
              id="coupon-type"
              className={inputClass}
              value={discountType}
              onChange={(event) =>
                setDiscountType(event.target.value === 'FIXED' ? 'FIXED' : 'PERCENT')
              }
            >
              <option value="PERCENT">درصدی (٪)</option>
              <option value="FIXED">مبلغ ثابت (تومان)</option>
            </select>
          </Field>
          <Field
            label={discountType === 'PERCENT' ? 'درصد تخفیف' : 'مبلغ تخفیف (تومان)'}
            htmlFor="coupon-value"
            required
            hint={discountType === 'PERCENT' ? '۱ تا ۱۰۰' : 'عدد صحیح بزرگ‌تر از صفر'}
          >
            <input
              id="coupon-value"
              type="number"
              min={1}
              max={discountType === 'PERCENT' ? 100 : undefined}
              className={inputClass}
              value={discountValue}
              onChange={(event) =>
                setDiscountValue(event.target.value === '' ? '' : Number(event.target.value))
              }
            />
          </Field>
          <Field label="حداقل مبلغ خرید (تومان)" htmlFor="coupon-min" hint="اختیاری — پیش‌فرض صفر">
            <input
              id="coupon-min"
              type="number"
              min={0}
              className={inputClass}
              value={minSpend}
              onChange={(event) =>
                setMinSpend(event.target.value === '' ? '' : Number(event.target.value))
              }
            />
          </Field>
          <Field label="تاریخ انقضا" htmlFor="coupon-expiry" hint="اختیاری — باید در آینده باشد">
            <input
              id="coupon-expiry"
              type="datetime-local"
              className={inputClass}
              value={expiresAt}
              onChange={(event) => setExpiresAt(event.target.value)}
            />
          </Field>
          <Field label="سقف استفاده" htmlFor="coupon-limit" hint="اختیاری — خالی یعنی نامحدود">
            <input
              id="coupon-limit"
              type="number"
              min={1}
              className={inputClass}
              value={usageLimit}
              onChange={(event) =>
                setUsageLimit(event.target.value === '' ? '' : Number(event.target.value))
              }
            />
          </Field>
          <Field label="توضیح داخلی" htmlFor="coupon-desc" hint="اختیاری">
            <input
              id="coupon-desc"
              className={inputClass}
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </Field>
        </div>
        <div className="mt-4">
          <button type="button" className={buttonClass.primary} onClick={() => void submit()}>
            ثبت کد تخفیف
          </button>
        </div>
      </Card>

      <Card>
        <CardHeader title="کدهای تخفیف" description="وضعیت هر کد از تاریخ انقضا و سقف استفاده محاسبه می‌شود." />
        {coupons.length === 0 ? (
          <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
            هنوز کد تخفیفی ثبت نشده است.
          </p>
        ) : (
          <Table
            caption="فهرست کدهای تخفیف"
            head={
              <tr>
                <Th>کد</Th>
                <Th>تخفیف</Th>
                <Th>حداقل خرید</Th>
                <Th>انقضا</Th>
                <Th>استفاده</Th>
                <Th>وضعیت</Th>
                <Th>عملیات</Th>
              </tr>
            }
          >
            {coupons.map((coupon) => {
              const discount = describeDiscount(coupon);
              return (
                <tr key={coupon.id}>
                  <Td>
                    <span className="cp-code">{coupon.code}</span>
                    {coupon.description ? (
                      <span className="block text-cp-caption text-ink-muted">
                        {coupon.description}
                      </span>
                    ) : null}
                  </Td>
                  <Td>
                    {discount.label} <span className="cp-code">({discount.code})</span>
                  </Td>
                  <Td>{coupon.minSpend === 0 ? '—' : formatToman(coupon.minSpend)}</Td>
                  <Td>{coupon.expiresAt === null ? 'بدون انقضا' : formatDateFa(coupon.expiresAt)}</Td>
                  <Td>
                    {formatCountFa(coupon.usedCount)} /{' '}
                    {coupon.usageLimit === null ? 'نامحدود' : formatCountFa(coupon.usageLimit)}
                  </Td>
                  <Td>
                    <Badge tone={COUPON_STATE_TONE[coupon.state]}>
                      {COUPON_STATE_LABELS[coupon.state]}{' '}
                      <span className="cp-code">{coupon.state}</span>
                    </Badge>
                  </Td>
                  <Td>
                    <button
                      type="button"
                      className={buttonClass.neutral}
                      disabled={busy[coupon.id] === true}
                      onClick={() => void toggle(coupon)}
                    >
                      {coupon.state === 'INACTIVE' ? 'فعال‌سازی' : 'غیرفعال‌سازی'}
                    </button>
                    {rowMessages[coupon.id] ? (
                      <span role="status" className="mt-1 block text-cp-caption text-ink-muted">
                        {rowMessages[coupon.id]}
                      </span>
                    ) : null}
                  </Td>
                </tr>
              );
            })}
          </Table>
        )}
      </Card>
    </div>
  );
}
