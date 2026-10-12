'use client';

import { createContext, useCallback, useContext, useMemo, useState, useSyncExternalStore } from 'react';
import type { ReactNode } from 'react';

import type { CartLine } from '@/contracts/storefront';
import { cartCount, cartSubtotal } from '@/lib/cart-rules';
import {
  addCartLine,
  clearCart,
  getCartSnapshot,
  getServerCartSnapshot,
  removeCartLine,
  setCartLineQuantity,
  subscribeToCart,
} from '@/lib/cart-store';

/**
 * D-172 §3.2/§3.4 — the cart, as client state.
 *
 * Why a provider rather than local state per component: the drawer, the header
 * badge, the PDP's add button and the checkout page all read the same basket, and
 * one owner is the only way they can agree.
 *
 * Hydration discipline (the same class of bug the root layout guards against):
 * the stored basket is NOT component state. `localStorage` does not exist on the
 * server and is written by other tabs, so it is an EXTERNAL store and is read
 * through `useSyncExternalStore` in `@/lib/cart-store` — the server render and
 * the hydrating client render both see the empty basket, and React re-reads the
 * real one immediately afterwards. `hydrated` is exposed so the header can
 * render its badge only once the stored basket is known — a "0" that later
 * becomes "2" is a visible lie, while "nothing yet" is not.
 *
 * Rejecting the obvious alternative is deliberate: reading storage in an effect
 * and calling `setState` there is a cascading render on every mount, and it also
 * loses the distinction between "no basket yet" and "an empty basket".
 */

interface CartContextValue {
  lines: CartLine[];
  count: number;
  /** Display-only sum. The authoritative total is computed server-side. */
  subtotal: number;
  hydrated: boolean;
  isOpen: boolean;
  openCart: () => void;
  closeCart: () => void;
  add: (line: CartLine) => void;
  setQuantity: (variantId: string, quantity: number) => void;
  remove: (variantId: string) => void;
  clear: () => void;
}

const CartContext = createContext<CartContextValue | null>(null);

export function CartProvider({ children }: { children: ReactNode }) {
  const { lines, hydrated } = useSyncExternalStore(
    subscribeToCart,
    getCartSnapshot,
    getServerCartSnapshot,
  );
  const [isOpen, setIsOpen] = useState(false);

  const openCart = useCallback(() => setIsOpen(true), []);
  const closeCart = useCallback(() => setIsOpen(false), []);
  // Every mutation goes to the store, which persists the parsed basket and
  // notifies React: there is no second write path that could disagree with it.
  const add = useCallback((line: CartLine) => addCartLine(line), []);
  const setQuantity = useCallback(
    (variantId: string, quantity: number) => setCartLineQuantity(variantId, quantity),
    [],
  );
  const remove = useCallback((variantId: string) => removeCartLine(variantId), []);
  const clear = useCallback(() => clearCart(), []);

  const value = useMemo<CartContextValue>(
    () => ({
      lines,
      count: cartCount(lines),
      subtotal: cartSubtotal(lines),
      hydrated,
      isOpen,
      openCart,
      closeCart,
      add,
      setQuantity,
      remove,
      clear,
    }),
    [lines, hydrated, isOpen, openCart, closeCart, add, setQuantity, remove, clear],
  );

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

/** Fails loudly rather than returning an empty cart that looks real. */
export function useCart(): CartContextValue {
  const value = useContext(CartContext);
  if (value === null) {
    throw new Error('useCart must be used inside <CartProvider>');
  }
  return value;
}
