import { commerce } from './schema';

/** D-172 §1.2 — product lifecycle: DRAFT → PUBLISHED → ARCHIVED. */
export const productStatus = commerce.enum('product_status', [
  'DRAFT',
  'PUBLISHED',
  'ARCHIVED',
]);

/** D-172 §1.5 — order lifecycle as specified for the fashion track. */
export const orderStatus = commerce.enum('order_status', [
  'PENDING',
  'PAID',
  'PROCESSING',
  'SHIPPED',
  'CANCELLED',
]);

/** D-172 §2.4 — coupon kind: percentage or fixed amount. */
export const discountType = commerce.enum('discount_type', ['PERCENT', 'FIXED']);

export type ProductStatus = (typeof productStatus.enumValues)[number];
export type OrderStatus = (typeof orderStatus.enumValues)[number];
export type DiscountType = (typeof discountType.enumValues)[number];
