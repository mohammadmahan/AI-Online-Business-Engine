import type { CartLine } from '@/contracts/storefront';

import {
  CART_STORAGE_KEY,
  addLine,
  parseStoredCart,
  removeLine,
  serializeCart,
  setLineQuantity,
} from './cart-rules';

/**
 * D-172 §3.2 — the cart as an EXTERNAL store, read through `useSyncExternalStore`.
 *
 * `localStorage` is not state React owns: it outlives the component, it is
 * written by other tabs, and it does not exist on the server. Modelling it as
 * component state means reading it in an effect and calling `setState` from that
 * effect — a cascading render, and a value that is momentarily "empty because
 * unknown" and then "empty because true" with nothing distinguishing them. Here
 * the store owns the read, React owns none of it, and the snapshot carries the
 * one thing a component cannot derive on its own: whether the stored basket has
 * actually been adopted yet (`hydrated`).
 *
 * Hydration discipline: `getServerCartSnapshot` returns the server's empty
 * basket, and React uses it for the server render AND the hydrating client
 * render, so the markup matches byte for byte. The real read happens in
 * `getClientCartSnapshot`, which React re-reads immediately after hydration —
 * the same mechanism the theme and view-mode bootstraps rely on.
 *
 * Everything that leaves this module has been through `parseStoredCart`: storage
 * is untrusted input, so a blob written by an older version, a half-finished
 * write or a hand edit degrades to a valid cart instead of a crashed page. What
 * is re-serialised is the PARSER's output, never the raw blob.
 */

export interface CartSnapshot {
  lines: CartLine[];
  /** False until the stored basket has been read on the client. */
  hydrated: boolean;
}

const SERVER_SNAPSHOT: CartSnapshot = { lines: [], hydrated: false };
/** Frozen and shared, so a server render can never disagree with itself. */
const SERVER_SNAPSHOT_REF = SERVER_SNAPSHOT;

let snapshot: CartSnapshot = SERVER_SNAPSHOT;
let adopted = false;
const listeners = new Set<() => void>();
let storageListenerBound = false;

function readStorage(): CartLine[] {
  try {
    return parseStoredCart(window.localStorage.getItem(CART_STORAGE_KEY));
  } catch {
    // Storage can be unavailable (private mode, blocked cookies). The cart still
    // works for this page view; it just does not survive a reload.
    return [];
  }
}

function writeStorage(lines: CartLine[]): void {
  try {
    window.localStorage.setItem(CART_STORAGE_KEY, serializeCart(lines));
  } catch {
    // A failed write must never break the page: the in-memory cart is intact.
  }
}

function notify(): void {
  for (const listener of listeners) {
    listener();
  }
}

/** Adopts whatever storage currently holds and tells React about it. */
function adoptStored(): void {
  adopted = true;
  snapshot = { lines: readStorage(), hydrated: true };
  notify();
}

function bindStorageListener(): void {
  if (storageListenerBound) {
    return;
  }
  storageListenerBound = true;
  window.addEventListener('storage', (event) => {
    // `key === null` means the whole store was cleared (`localStorage.clear()`),
    // which also invalidates our basket.
    if (event.key !== null && event.key !== CART_STORAGE_KEY) {
      return;
    }
    adoptStored();
  });
}

/**
 * React's subscription. The immediate `notify` is what makes the first
 * post-hydration render show the real basket even when nothing else notifies
 * (React would otherwise only re-read after this callback fires).
 */
export function subscribeToCart(listener: () => void): () => void {
  listeners.add(listener);
  bindStorageListener();
  if (!adopted) {
    adoptStored();
  }
  return () => {
    listeners.delete(listener);
  };
}

/** Client snapshot. Stable between changes, or React re-renders forever. */
export function getCartSnapshot(): CartSnapshot {
  if (!adopted) {
    adopted = true;
    snapshot = { lines: readStorage(), hydrated: true };
  }
  return snapshot;
}

/** Server snapshot: the same empty basket, always the same object. */
export function getServerCartSnapshot(): CartSnapshot {
  return SERVER_SNAPSHOT_REF;
}

function commit(lines: CartLine[]): void {
  adopted = true;
  snapshot = { lines, hydrated: true };
  writeStorage(lines);
  notify();
}

export function addCartLine(line: CartLine): void {
  commit(addLine(getCartSnapshot().lines, line));
}

export function setCartLineQuantity(variantId: string, quantity: number): void {
  commit(setLineQuantity(getCartSnapshot().lines, variantId, quantity));
}

export function removeCartLine(variantId: string): void {
  commit(removeLine(getCartSnapshot().lines, variantId));
}

export function clearCart(): void {
  commit([]);
}
