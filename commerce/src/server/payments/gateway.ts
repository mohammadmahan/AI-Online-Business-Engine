import type { PaymentAttempt } from '@/contracts/storefront';

/**
 * D-172 §3.4 / AC-8 — the payment gateway adapter seam.
 *
 * The order lifecycle requires an authorisation step between placing an order and
 * marking it paid, and the roadmap's payment provider is an OPEN owner decision
 * (decision 10, D-172 G-4). So this module defines the SEAM and ships a mock
 * whose default answer is a refusal:
 *
 *   - `UNAVAILABLE` — the default. Nothing has been charged, no order is marked
 *     paid, and the customer is told the payment step is not connected yet. This
 *     is the fail-closed state (D-171 §2.2): an unconfigured provider is a
 *     refusal, never a simulated success.
 *   - `AUTHORIZED` / `DECLINED` — reachable only when a caller explicitly
 *     constructs the mock with that outcome, which is how the order path's
 *     handling of a real gateway is exercised by tests. The reference such an
 *     attempt returns is prefixed `MOCK-` so it can never be mistaken for a
 *     provider reference in the database or in the admin panel.
 *
 * What this module deliberately does NOT do: hold a credential, contact a
 * network, store a card number or PAN, or move an order out of `PENDING`. Phase
 * 6.1 replaces the mock behind this interface once the owner selects a provider
 * — the order write path does not change.
 */

export interface PaymentAuthorizationRequest {
  orderId: string;
  /** Integer Iranian Toman (D-010). */
  amount: number;
  /** Merchant-facing description; carries no customer PII. */
  description: string;
}

export interface PaymentCallbackPayload {
  /** Provider reference from a callback; `null` when the provider sent none. */
  reference: string | null;
}

export interface PaymentGateway {
  /** Stable identifier recorded in logs; the mock is named as such. */
  readonly id: string;
  authorize(request: PaymentAuthorizationRequest): Promise<PaymentAttempt>;
  verifyCallback(payload: PaymentCallbackPayload): Promise<PaymentAttempt>;
}

export type MockPaymentOutcome = 'UNAVAILABLE' | 'AUTHORIZED' | 'DECLINED';

const PROVIDER_NOT_SELECTED: PaymentAttempt = {
  status: 'UNAVAILABLE',
  code: 'PROVIDER_NOT_SELECTED',
  message:
    'درگاه پرداخت هنوز انتخاب نشده است، بنابراین هیچ مبلغی از مشتری دریافت نمی‌شود. سفارش با وضعیت «در انتظار پرداخت» ثبت شده است.',
  reference: null,
};

function declined(reason: string): PaymentAttempt {
  return {
    status: 'DECLINED',
    code: 'MOCK_DECLINED',
    message: `پرداخت تأیید نشد (${reason}). سفارش ثبت شده اما پرداخت‌نشده باقی می‌ماند.`,
    reference: null,
  };
}

function authorized(orderId: string): PaymentAttempt {
  return {
    status: 'AUTHORIZED',
    code: 'MOCK_AUTHORIZED',
    message:
      'این یک تأیید آزمایشی است؛ هیچ درگاه واقعی در این مسیر وجود ندارد و سفارش باید توسط پنل مدیریت بررسی شود.',
    // Prefixed so a mock reference can never be mistaken for a real one.
    reference: `MOCK-${orderId}`,
  };
}

export interface MockPaymentGatewayOptions {
  outcome?: MockPaymentOutcome;
  /**
   * DEMO ONLY: where an authorised mock attempt sends the browser, with
   * `{reference}` substituted (URL-encoded). Unset by default — the generic mock
   * knows no route. The runtime supplies the mock return path, and that route is
   * itself gated on `PAYMENT_MODE=mock`, so a template alone opens nothing.
   */
  redirectUrlTemplate?: string;
}

/**
 * The mock adapter. `UNAVAILABLE` unless a caller deliberately asks for another
 * outcome — so the deployed storefront can only ever refuse to charge.
 */
export function createMockPaymentGateway(
  options?: MockPaymentGatewayOptions,
): PaymentGateway {
  const outcome: MockPaymentOutcome = options?.outcome ?? 'UNAVAILABLE';
  const redirectUrlTemplate = options?.redirectUrlTemplate;

  return {
    id: 'mock',

    async authorize(request: PaymentAuthorizationRequest): Promise<PaymentAttempt> {
      if (!Number.isInteger(request.amount) || request.amount < 0) {
        return declined('مبلغ نامعتبر');
      }
      if (request.orderId.trim().length === 0) {
        return declined('شناسهٔ سفارش نامعتبر');
      }
      if (outcome === 'AUTHORIZED') {
        const attempt = authorized(request.orderId);
        if (redirectUrlTemplate === undefined) {
          return attempt;
        }
        return {
          ...attempt,
          redirectUrl: redirectUrlTemplate.replace(
            '{reference}',
            encodeURIComponent(attempt.reference ?? ''),
          ),
        };
      }
      if (outcome === 'DECLINED') {
        return declined('پاسخ آزمایشی درگاه');
      }
      return PROVIDER_NOT_SELECTED;
    },

    async verifyCallback(payload: PaymentCallbackPayload): Promise<PaymentAttempt> {
      if (payload.reference === null || payload.reference.trim().length === 0) {
        return declined('بازگشت بدون شناسهٔ پرداخت');
      }
      if (outcome === 'AUTHORIZED') {
        return authorized(payload.reference);
      }
      return PROVIDER_NOT_SELECTED;
    },
  };
}

/** The instance the application wires: it can only refuse. */
export const mockPaymentGateway: PaymentGateway = createMockPaymentGateway();
