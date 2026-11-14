import type { Metadata } from 'next';

import { CheckoutForm } from '@/components/storefront/checkout-form';
import { SectionEyebrow } from '@/components/storefront/storefront-primitives';
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
 *
 * D-177 Phase 2D: the shell uses the editorial storefront layer (`--sf-*`). No
 * checkout, validation, shipping, payment or server-action behavior changed.
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
      <header className="border-b border-sf-edge pb-8">
        <SectionEyebrow>فروشگاه پوشاک · تسویه</SectionEyebrow>
        <h1 className="mt-3 font-display text-sf-title font-semibold leading-tight text-sf-ink">
          تسویهٔ خرید
        </h1>
        <p className="mt-3 max-w-2xl text-sf-body leading-relaxed text-sf-ink-muted">
          اطلاعات گیرنده، روش ارسال و کد تخفیف. مبلغ نهایی و موجودی روی سرور بررسی و محاسبه
          می‌شود.
        </p>
      </header>
      {repository === null ? (
        <div className="mt-8">
          <StorefrontUnavailable what="فرم تسویهٔ خرید" />
        </div>
      ) : shippingConfig === null ? (
        <div className="mt-8">
          <StorefrontUnavailable what="روش‌های ارسال" />
        </div>
      ) : (
        <CheckoutForm shippingConfig={shippingConfig} />
      )}
    </>
  );
}
