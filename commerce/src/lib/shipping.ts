import type { ShippingMethod } from '@/contracts/storefront';

/**
 * D-172 §3.4 — shipping method selection, as DATA.
 *
 * The roadmap names the three options a boutique actually offers (Express
 * Courier, Standard Post, Tipax). What is deliberately NOT here is a carrier
 * integration: shipping-provider selection is an OPEN owner decision (roadmap
 * decision 11, D-172 G-4), so no carrier API, credential or tracking hand-off is
 * implied or stubbed. These are fulfilment CHOICES the customer makes and the
 * order records — nothing dispatches, nothing is booked.
 *
 * Amounts are integer Toman (D-010). Tipax is the pay-on-delivery route: its
 * amount is 0 because the customer pays the carrier, and the description says
 * exactly that rather than inventing a fee.
 */

export const SHIPPING_METHODS: ShippingMethod[] = [
  {
    id: 'POST_PISHTAZ',
    label: 'پست پیشتاز',
    amount: 45_000,
    description: 'تحویل ۳ تا ۵ روز کاری در سراسر ایران.',
  },
  {
    id: 'EXPRESS_COURIER',
    label: 'پیک سریع',
    amount: 90_000,
    description: 'تحویل ۲۴ ساعته در تهران و کرج.',
  },
  {
    id: 'TIPAX_PAY_ON_DELIVERY',
    label: 'تیپاکس (هزینه با گیرنده)',
    amount: 0,
    description: 'هزینهٔ ارسال هنگام تحویل به تیپاکس پرداخت می‌شود؛ در جمع سفارش لحاظ نمی‌شود.',
  },
];

/** Pre-selected method — a default the customer can change, never a hidden one. */
export const DEFAULT_SHIPPING_METHOD_ID = 'POST_PISHTAZ';

export function shippingMethodById(id: string): ShippingMethod | undefined {
  return SHIPPING_METHODS.find((method) => method.id === id);
}

/**
 * The amount to store for a method id, or `null` for an id this module does not
 * define. `null` is a REFUSAL the caller must surface — an unknown shipping
 * method is never priced as 0 and never silently swapped for the default.
 */
export function shippingAmountFor(id: string): number | null {
  const method = shippingMethodById(id);
  return method ? method.amount : null;
}
