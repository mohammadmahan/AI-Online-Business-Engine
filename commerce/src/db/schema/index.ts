/**
 * D-172 Phase 1 — schema entry point consumed by `drizzle.config.ts` and by the
 * application layer. Re-exports every table, enum, relation and inferred model
 * type so a consumer imports from one place.
 */
export { commerce } from './schema';
export { productStatus, orderStatus } from './enums';
export type { ProductStatus, OrderStatus } from './enums';
export { categories, products, productVariants, productImages } from './catalog';
export { customers, orders, orderItems } from './ordering';
export {
  categoriesRelations,
  productsRelations,
  productVariantsRelations,
  productImagesRelations,
  customersRelations,
  ordersRelations,
  orderItemsRelations,
} from './relations';
