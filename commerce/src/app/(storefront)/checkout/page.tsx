import type { Metadata } from 'next';

import { CheckoutForm } from '@/components/storefront/checkout-form';
import { StorefrontUnavailable } from '@/components/storefront/storefront-unavailable';
import type { ShippingConfig } from '@/lib/shipping';
import { getRepository } from '@/server/db-context';
import { getShippingConfig } from '@/server/shipping/config';

/**
 * D-172 §3.4 — the one-step checkout.
 *
 * The form itself is the client component (`CheckoutForm`); this page only decides
 * whether the surface can do its job at all. With no canonical connection it says
 * so and renders no form — a checkout that accepted a customer's details and then
 * failed to write them would be the worst possible failure mode here.
 */

export const metadata: Metadata = {
  title: 'تسویهٔ خرید',
  description: 'ثبت اطلاعات گیرنده، روش ارسال و ثبت سفارش.',
  robots: { index: false, follow: false },
};

export const dynamic = 'force-dynamic';

export default function CheckoutPage() {
  const repository = getRepository();
  let shippingConfig: ShippingConfig | null = null;
  if (repository !== null) {
    try {
      shippingConfig = getShippingConfig();
    } catch (error) {
      // The startup guard should already have refused; this keeps a later bad
      // runtime configuration from rendering a form that cannot price shipping.
      console.error('[commerce] shipping configuration unavailable', {
        name: error instanceof Error ? error.name : 'UnknownError',
      });
    }
  }

  return (
    <>
      <h1 className="text-cp-display font-bold text-ink">تسویهٔ خرید</h1>
      <p className="mt-1 text-cp-label text-ink-muted">
        اطلاعات گیرنده، روش ارسال و کد تخفیف. مبلغ نهایی و موجودی روی سرور بررسی و محاسبه می‌شود.
      </p>
      {repository === null ? (
        <div className="mt-6">
          <StorefrontUnavailable what="فرم تسویهٔ خرید" />
        </div>
      ) : shippingConfig === null ? (
        <div className="mt-6">
          <StorefrontUnavailable what="روش‌های ارسال" />
        </div>
      ) : (
        <CheckoutForm shippingConfig={shippingConfig} />
      )}
    </>
  );
}
