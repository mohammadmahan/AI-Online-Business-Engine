import { createHmac, timingSafeEqual } from 'node:crypto';

/**
 * D-172 Phase 4 transition / §6.1 — the INBOUND callback's authenticity gate.
 *
 * An async payment callback is the only request in this track that arrives
 * without a session, so it is also the only one that has to prove who it is.
 * This module is that proof, and it is deliberately a PURE function of three
 * inputs — the raw body, the signature header and the shared secret — so the
 * refusal rules can be exercised without a server, a network or a provider:
 *
 *   - NO SECRET configured → refuse, ALWAYS. An unconfigured seam is a refusal,
 *     never a pass (D-171 §2.2); there is no "development mode" that accepts an
 *     unsigned payload, because the code path that would exist only in
 *     development is the one an operator would later mistake for a feature.
 *   - MISSING or MALFORMED header → refuse without ever calling the comparison.
 *   - MISMATCH → refuse. Comparison is constant-time over the full digest, so a
 *     caller cannot learn a correct signature a byte at a time.
 *
 * The scheme (HMAC-SHA256 over the RAW body, lowercase hex, optional `sha256=`
 * prefix) is OURS on purpose. The provider is an open owner decision (G-4 /
 * decision 10) and every Iranian gateway signs differently — the choice would be
 * invented today and rewritten the moment a provider is picked. Phase 6.1
 * adapts THIS seam to the real scheme rather than replacing the seam itself, and
 * when it does, the algorithm identifier below is what a stored signature will
 * be checked against. Nothing here holds a credential, contacts a network or
 * knows a provider name; the secret arrives from the environment at call time
 * (D-045/D-124).
 */

/** The header a callback must carry. Lower-case: `Headers` normalises names. */
export const WEBHOOK_SIGNATURE_HEADER = 'x-commerce-signature';

/** The environment variable holding the shared secret. Placeholder in `.env.example`. */
export const WEBHOOK_SECRET_ENV = 'COMMERCE_PAYMENT_WEBHOOK_SECRET';

export const WEBHOOK_SIGNATURE_ALGORITHM = 'sha256';

export type SignatureRefusalCode =
  | 'WEBHOOK_NOT_CONFIGURED'
  | 'SIGNATURE_MISSING'
  | 'SIGNATURE_MALFORMED'
  | 'SIGNATURE_MISMATCH';

export type SignatureVerdict =
  | { ok: true; algorithm: typeof WEBHOOK_SIGNATURE_ALGORITHM }
  | { ok: false; code: SignatureRefusalCode; message: string };

/**
 * The refusal messages a caller may return. They state a RULE, never a hint: a
 * caller must not be able to tell "the secret is unset" from "your signature is
 * wrong" beyond the one distinction an operator needs (not configured → 503,
 * rejected → 401), and no message ever echoes a secret, a digest or a body.
 */
const REFUSAL_MESSAGES: Record<SignatureRefusalCode, string> = {
  WEBHOOK_NOT_CONFIGURED:
    'درگاه پرداخت و کلید امضای بازگشت آن هنوز تنظیم نشده است؛ بنابراین هیچ بازگشتی پردازش نمی‌شود.',
  SIGNATURE_MISSING: 'امضای درخواست یافت نشد.',
  SIGNATURE_MALFORMED: 'قالب امضای درخواست معتبر نیست.',
  SIGNATURE_MISMATCH: 'امضای درخواست با بدنهٔ آن مطابقت ندارد.',
};

function refuse(code: SignatureRefusalCode): SignatureVerdict {
  return { ok: false, code, message: REFUSAL_MESSAGES[code] };
}

/** The configured secret, or `null`. Read at CALL time — never captured. */
export function webhookSecret(): string | null {
  const value = process.env[WEBHOOK_SECRET_ENV]?.trim();
  return value && value.length > 0 ? value : null;
}

/**
 * The signature a correct caller would send. Exported because it is the
 * SPECIFICATION of the scheme as much as a helper: a test, a future provider
 * adapter and a local simulator all sign through this one function, so the
 * verification below and the thing it verifies cannot drift apart.
 */
export function signWebhookBody(rawBody: string, secret: string): string {
  return createHmac(WEBHOOK_SIGNATURE_ALGORITHM, secret).update(rawBody, 'utf8').digest('hex');
}

/** Strips an optional `sha256=` prefix; anything else at that position is malformed. */
function digestOf(header: string): string | null {
  const trimmed = header.trim();
  const withoutAlgorithm = trimmed.includes('=') ? trimmed.slice(trimmed.indexOf('=') + 1) : trimmed;
  const digest = withoutAlgorithm.trim().toLowerCase();
  if (!/^[0-9a-f]{64}$/.test(digest)) {
    return null;
  }
  return digest;
}

export function verifyWebhookSignature(input: {
  rawBody: string;
  header: string | null;
  secret: string | null;
}): SignatureVerdict {
  // Order matters: the configuration gate is FIRST, so a deployment without a
  // secret refuses loudly instead of quietly rejecting every real callback.
  if (input.secret === null || input.secret.trim().length === 0) {
    return refuse('WEBHOOK_NOT_CONFIGURED');
  }
  if (input.header === null || input.header.trim().length === 0) {
    return refuse('SIGNATURE_MISSING');
  }
  const presented = digestOf(input.header);
  if (presented === null) {
    return refuse('SIGNATURE_MALFORMED');
  }

  const expected = signWebhookBody(input.rawBody, input.secret);
  // Both sides are 64 hex characters by construction, so `timingSafeEqual`'s
  // equal-length requirement is satisfied; the guard is still here because the
  // digest above is the only thing keeping a length mismatch from throwing.
  const expectedBuffer = Buffer.from(expected, 'utf8');
  const presentedBuffer = Buffer.from(presented, 'utf8');
  if (
    expectedBuffer.length !== presentedBuffer.length ||
    !timingSafeEqual(expectedBuffer, presentedBuffer)
  ) {
    return refuse('SIGNATURE_MISMATCH');
  }

  return { ok: true, algorithm: WEBHOOK_SIGNATURE_ALGORITHM };
}
