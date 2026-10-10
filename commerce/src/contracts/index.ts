/**
 * D-172 Phase 1 — public contract surface of the E-Commerce track's data core.
 *
 * Consumers (merchant admin, storefront, automation) import entity models and
 * write payloads from here; nothing in this module performs I/O.
 */
export * from './catalog';
export * from './ordering';

export type {
  OrderStatus,
  ProductStatus,
} from '../db/schema';
