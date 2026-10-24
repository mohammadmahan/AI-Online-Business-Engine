/**
 * D-172 — schema entry point consumed by `drizzle.config.ts` and by the
 * application layer. Re-exports every table, enum, relation and inferred model
 * type so a consumer imports from one place.
 */
export { commerce } from './schema';
export {
  productStatus,
  orderStatus,
  discountType,
  orderStatusSource,
  notificationChannel,
  notificationStatus,
} from './enums';
export type {
  ProductStatus,
  OrderStatus,
  DiscountType,
  OrderStatusSource,
  NotificationChannel,
  NotificationStatus,
} from './enums';
export { categories, products, productVariants, productImages } from './catalog';
export { customers, orders, orderItems, orderStatusHistory } from './ordering';
export { notificationOutbox } from './notifications';
export { coupons } from './promotions';
export {
  categoriesRelations,
  productsRelations,
  productVariantsRelations,
  productImagesRelations,
  customersRelations,
  ordersRelations,
  orderItemsRelations,
  orderStatusHistoryRelations,
} from './relations';
