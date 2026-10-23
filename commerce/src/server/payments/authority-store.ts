import type { CommerceRepository } from '../repository';

/**
 * D-172 §6.1 — the DURABLE half of the payment seam.
 *
 * Why this port exists at all: a redirect-based provider issues an `authority`
 * at request time and requires the AMOUNT at verify time, but the callback
 * carries only the authority. Remembering that pair in the adapter's process
 * works until the process restarts or a second instance answers the callback —
 * then a real payment exists at the provider while this side has no idea what it
 * was for. So the adapter is given a store instead of a cache, and the store is
 * backed by the order row (G-1: PostgreSQL is the SSOT).
 *
 * The port is deliberately tiny and throws on failure rather than returning a
 * sentinel: the adapter's only sane reaction to "could not persist" or "could
 * not read" is to refuse/retry as `UNAVAILABLE`, never to guess. It also keeps
 * the adapter itself free of any database import, so its tests need no
 * connection.
 */
export interface PaymentAuthorizationStore {
  /**
   * Persists the provider authorisation against the order it belongs to.
   *
   * Throws when it could not be persisted — including when the order is no
   * longer `PENDING`, because an order that cannot be paid must not be sent to a
   * payment page.
   */
  save(record: {
    orderId: string;
    provider: string;
    authority: string;
    /** Integer Toman (D-010), the amount the provider was asked for. */
    amount: number;
  }): Promise<void>;

  /** The persisted record for provider + authority, or `null`. Throws on error. */
  find(
    provider: string,
    authority: string,
  ): Promise<{ orderId: string; provider: string; authority: string; amount: number } | null>;
}

/**
 * The production binding: the repository's order row is the store.
 *
 * The repository is resolved at CALL time (`getRepository()` can be `null` while
 * `DATABASE_URL` is unset), so an unconfigured deployment refuses at the moment
 * it tries to use it instead of failing while the module is being imported.
 */
export function createRepositoryPaymentAuthorizationStore(
  resolve: () => CommerceRepository | null,
): PaymentAuthorizationStore {
  function repository(): CommerceRepository {
    const found = resolve();
    if (found === null) {
      // No credential details in the message: the adapter maps this to a static
      // Persian refusal, and a driver string can echo a connection URL
      // (D-114/D-124).
      throw new Error('payment authorization store has no repository');
    }
    return found;
  }

  return {
    async save(record) {
      const written = await repository().recordPaymentAuthorization(record);
      if (!written) {
        throw new Error('payment authorization was not persisted');
      }
    },

    async find(provider, authority) {
      return repository().findPaymentAuthorization(provider, authority);
    },
  };
}
