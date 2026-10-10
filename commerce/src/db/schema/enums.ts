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

export type ProductStatus = (typeof productStatus.enumValues)[number];
export type OrderStatus = (typeof orderStatus.enumValues)[number];
