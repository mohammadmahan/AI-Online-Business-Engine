import type {
  CartAvailabilityLine,
  CartLine,
  CheckoutDraft,
  OrderRefused,
  PlaceOrderResult,
} from '@/contracts/storefront';
import { formatCountFa, formatToman } from '@/lib/format';
import { validateCheckoutCustomer } from '@/lib/validation';

/**
 * D-172 §3.4 — the checkout form's SUBMISSION PIPELINE, as a PURE module.
 *
 * The order of operations is the contract, and it is the reason this lives
 * outside the component:
 *
 *  1. the customer block is validated with the very same rules the server
 *     applies (`@/lib/validation`) — a typo costs no round trip;
 *  2. the cart is PRE-FLIGHTED (§3.3), an optimistic and NON-authoritative read
 *     that refuses BEFORE an order can be written, and reports a changed server
 *     price instead of silently substituting it;
 *  3. the order is submitted through the server action, which re-resolves
 *     prices, stock, the coupon and the totals inside its transaction.
 *
 * Two failure modes are what the extracted shape buys. Both were previously
 * invisible:
 *
 *  - a REFUSAL now carries the notes the customer was shown, so a price warning
 *    survives a later refusal instead of vanishing;
 *  - a THROWN call — the server restarted, the network dropped, the action
 *    answered with a 5xx — becomes `status: 'error'` with a message that claims
 *    NOTHING about the order. Before this the rejection escaped an `async`
 *    submit handler invoked with `void`, so the customer got no feedback at all
 *    and could not tell whether an order existed. A submission whose outcome is
 *    unknown must never read like a success — and must not claim a definite
 *    failure either, because the write may have committed before the response
 *    was lost.
 *
 * Nothing here decides a price, a total or a status. The ports are injected
 * (`checkCartAvailabilityAction`, `placeOrderAction` in the app), which is what
 * makes every branch testable without a browser or a database.
 */

/** The four fields the customer types; mirror of the form's own state. */
export interface CheckoutCustomerInput {
  fullName: string;
  phoneNumber: string;
  address: string;
  postalCode: string;
}

export type CheckoutFieldErrors = Partial<
  Record<'fullName' | 'phoneNumber' | 'address' | 'postalCode', string>
>;

/** The shape both the pre-flight action and the draft's lines use. */
export interface CheckoutLineInput {
  variantId: string;
  quantity: number;
}

export interface CheckoutSubmissionInput {
  customer: CheckoutCustomerInput;
  /** Raw input from the form; normalised here so the rule is testable. */
  couponCode: string;
  shippingMethodId: string;
  /** The cart's own lines, used only to NOTICE a price the server changed. */
  cartLines: CartLine[];
  /**
   * Browser-owned intent id. Reused across a retry/reload of the same cart and
   * rotated by the caller when the intent changes.
   */
  idempotencyKey: string;
}

/** The two server actions, injected so the pipeline needs no Next runtime. */
export interface CheckoutPorts {
  checkAvailability(
    lines: CheckoutLineInput[],
  ): Promise<{ ok: true; lines: CartAvailabilityLine[] } | OrderRefused>;
  placeOrder(draft: CheckoutDraft): Promise<PlaceOrderResult>;
}

export type CheckoutPlaced = Extract<PlaceOrderResult, { ok: true }>;

export type CheckoutSubmission =
  | { status: 'invalid'; errors: CheckoutFieldErrors }
  | { status: 'refused'; result: OrderRefused; notes: string[] }
  | { status: 'placed'; result: CheckoutPlaced; notes: string[] }
  | { status: 'error'; message: string };

/**
 * Shown when a submission's outcome is UNKNOWN (transport failure).
 *
 * Deliberately says neither "saved" nor "not saved": the order may have been
 * committed before the answer was lost, so the customer is told the truth — the
 * confirmation did not arrive — and is pointed at the shop rather than at a
 * second submission that could create a duplicate order.
 */
export const CHECKOUT_TRANSPORT_ERROR_MESSAGE =
  'ارتباط با سرور برقرار نشد، بنابراین ثبت سفارش تأیید نشد. اگر سفارش شما ثبت شده باشد، فروشگاه آن را بررسی می‌کند؛ پیش از تلاش دوباره با فروشگاه تماس بگیرید.';

function fieldErrorsFrom(issues: Array<{ field: string; message: string }>): CheckoutFieldErrors {
  const errors: CheckoutFieldErrors = {};
  for (const issue of issues) {
    if (
      issue.field === 'fullName' ||
      issue.field === 'phoneNumber' ||
      issue.field === 'address' ||
      issue.field === 'postalCode'
    ) {
      errors[issue.field] = issue.message;
    }
  }
  return errors;
}

/** `''` and whitespace mean "no coupon"; anything else is upper-cased once. */
export function normalizeCouponInput(value: string): string | null {
  const trimmed = value.trim();
  return trimmed === '' ? null : trimmed.toUpperCase();
}

/**
 * Lines whose server price no longer matches what the cart displayed.
 *
 * Stated as a warning, never applied silently: the customer is told which line
 * moved and that the final total uses the server's figure.
 */
export function priceChangeNotes(
  lines: CartAvailabilityLine[],
  cartLines: CartLine[],
): string[] {
  const notes: string[] = [];
  for (const line of lines) {
    const stored = cartLines.find((entry) => entry.variantId === line.variantId);
    if (stored && line.effectivePrice !== null && line.effectivePrice !== stored.unitPrice) {
      notes.push(
        `${line.productTitle} (${line.colorName}/${line.size}): قیمت روی سرور ${formatToman(line.effectivePrice)} است و در محاسبهٔ نهایی همین مبلغ لحاظ می‌شود.`,
      );
    }
  }
  return notes;
}

export async function submitCheckout(
  input: CheckoutSubmissionInput,
  ports: CheckoutPorts,
): Promise<CheckoutSubmission> {
  const customerValidation = validateCheckoutCustomer({
    fullName: input.customer?.fullName,
    phoneNumber: input.customer?.phoneNumber,
    address: input.customer?.address,
    postalCode: input.customer?.postalCode,
  });
  if (!customerValidation.ok) {
    return { status: 'invalid', errors: fieldErrorsFrom(customerValidation.issues) };
  }

  const lines: CheckoutLineInput[] = input.cartLines.map((line) => ({
    variantId: line.variantId,
    quantity: line.quantity,
  }));

  try {
    const preflight = await ports.checkAvailability(lines);
    if (!preflight.ok) {
      // The pre-flight itself refused (malformed cart, unconfigured database):
      // its code and message are already the customer-facing vocabulary.
      return { status: 'refused', result: preflight, notes: [] };
    }

    const blocked = preflight.lines.filter((line) => !line.available);
    if (blocked.length > 0) {
      return {
        status: 'refused',
        notes: [],
        result: {
          ok: false,
          // A line with no server price is GONE (variant or product no longer
          // sellable); a priced line is merely short of stock.
          code: blocked.some((line) => line.effectivePrice === null)
            ? 'VARIANT_UNAVAILABLE'
            : 'STOCK_INSUFFICIENT',
          message: `${formatCountFa(blocked.length)} قلم از سبد خرید دیگر قابل سفارش نیست. تعداد یا انتخاب خود را اصلاح کنید؛ هیچ سفارشی ثبت نشد.`,
        },
      };
    }

    const notes = priceChangeNotes(preflight.lines, input.cartLines);

    const placed = await ports.placeOrder({
      customer: {
        fullName: input.customer.fullName,
        phoneNumber: input.customer.phoneNumber,
        address: input.customer.address,
        postalCode: input.customer.postalCode,
      },
      couponCode: normalizeCouponInput(input.couponCode),
      shippingMethodId: input.shippingMethodId,
      lines,
      idempotencyKey: input.idempotencyKey,
    });

    return placed.ok
      ? { status: 'placed', result: placed, notes }
      : { status: 'refused', result: placed, notes };
  } catch {
    // The call never produced a verdict. Nothing about the order is claimed.
    return { status: 'error', message: CHECKOUT_TRANSPORT_ERROR_MESSAGE };
  }
}

