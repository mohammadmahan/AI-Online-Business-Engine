import assert from 'node:assert/strict';
import { before, describe, it } from 'node:test';

import type { ProductCreatePayload } from '@/contracts/catalog';
import type { CheckoutDraft } from '@/contracts/storefront';
import { EMPTY_CATALOG_FILTERS } from '@/contracts/storefront';
import { CART_STORAGE_KEY, parseStoredCart } from '@/lib/cart-rules';
import { addCartLine, clearCart, getCartSnapshot, setCartLineQuantity } from '@/lib/cart-store';
import { applyFilters } from '@/lib/catalog-filters';
import { computeCheckoutTotals } from '@/lib/checkout-rules';
import { filterInventory, inventorySummary, stockState } from '@/lib/inventory-rules';
import { DEFAULT_SHIPPING_METHOD_ID, shippingAmountFor } from '@/lib/shipping';
import {
  canAddVariant,
  colorOptions,
  defaultColor,
  findVariant,
  selectionCap,
  selectionLevel,
  sizeOptions,
  toCartLine,
} from '@/lib/variant-selection';
import { placeOrderAction } from '@/server/actions/storefront';
import { DB_NOT_CONFIGURED_MESSAGE } from '@/server/db-context';
import { mockPaymentGateway } from '@/server/payments/gateway';
import { createMemoryRepository } from '@/server/repository-memory';
import type { CommerceRepository, InventoryRow } from '@/server/repository';
import { checkAvailability, placeCheckoutOrder } from '@/server/services/checkout';
import {
  MERCHANT_TRANSITION,
  getOrder,
  transitionOrder,
} from '@/server/services/orders';
import { createProduct } from '@/server/services/products';
import { getPublishedProduct, listPublishedProducts } from '@/server/services/storefront';

/**
 * D-172 §3 — the CUSTOMER FUNNEL, end to end, without a browser.
 *
 * The live suite (`__tests__/live-db/phase3-storefront-live.test.ts`) proves the
 * same journey against real PostgreSQL; this one runs on every `npm test` and
 * walks the stages in the order a customer meets them:
 *
 *   catalog read → facet filter → PDP (colour × size matrix) → cart line in the
 *   persisted drawer store → pre-flight check → `placeCheckoutOrder` → order row
 *   → MERCHANT INVENTORY RECONCILIATION → cancellation → inventory restored.
 *
 * Two things make this more than a scripted happy path. First, the stages hand
 * off through the REAL seams rather than through hand-built fixtures: the cart
 * line comes from `toCartLine`, the draft is built from what the cart STORE
 * holds (including the round trip through `localStorage`), and the last stage
 * reads the merchant grid's own rules (`inventorySummary`, `stockState`,
 * `filterInventory`) — so a variant that the customer bought out is seen as
 * «ناموجود» by the merchant without a reload, and a cancellation puts it back.
 * Second, the quantities are chosen so the order crosses two stock thresholds:
 * the basket empties one variant and drops another to «موجودی محدود».
 *
 * Hermetic by construction: the in-memory repository is the test double of the
 * live schema (the same mappers build the read models), and `localStorage` is
 * stubbed the way `cart-store.test.ts` stubs it. No database, no network, no
 * Next runtime — except the LAST assertion, which drives the real
 * `placeOrderAction` entry point to prove the funnel refuses loudly when no
 * canonical connection is configured (and only then).
 */

/* ---------------------------------------------------------------- the drawer */

type StorageListener = (event: { key: string | null }) => void;

const store = new Map<string, string>();
const listeners = new Map<string, StorageListener[]>();

const stubWindow = {
  localStorage: {
    getItem: (key: string) => store.get(key) ?? null,
    setItem: (key: string, value: string) => {
      store.set(key, value);
    },
    removeItem: (key: string) => {
      store.delete(key);
    },
  },
  addEventListener: (type: string, handler: StorageListener) => {
    listeners.set(type, [...(listeners.get(type) ?? []), handler]);
  },
};

// The cart store reads `window.localStorage` at call time, so stubbing the
// global before any store function runs is enough (same approach as
// `cart-store.test.ts` — the store is a process-wide singleton).
(globalThis as unknown as { window: unknown }).window = stubWindow;

/* ------------------------------------------------------------------ fixtures */

const MANTO_SLUG = 'funnel-manto';
const SHOMIZ_SLUG = 'funnel-shomiz';
const DRAFT_SLUG = 'funnel-draft';
const COUPON_CODE = 'FUNNEL10';

const BASE_PRICE = 2_450_000;
const DISCOUNT_PRICE = 2_100_000;
const SHOMIZ_PRICE = 890_000;
const SHIPPING = shippingAmountFor(DEFAULT_SHIPPING_METHOD_ID) ?? 0;

/** SKU → the stock the boutique starts the day with. */
const STARTING_STOCK: Record<string, number> = {
  'FUN-BLK-S': 4,
  'FUN-BLK-M': 0,
  'FUN-WHT-S': 2,
  'FUN-SHZ-38': 5,
};

const MANTO_PAYLOAD: ProductCreatePayload = {
  categoryId: 'cat-1',
  title: 'مانتو کتان قیف',
  slug: MANTO_SLUG,
  basePrice: BASE_PRICE,
  discountPrice: DISCOUNT_PRICE,
  descriptionRaw: 'مانتو کتان با دوخت ساده.',
  descriptionHtml: '<p>مانتو کتان با دوخت ساده.</p>',
  fabricType: 'کتان',
  season: 'تابستان',
  status: 'PUBLISHED',
  variants: [
    { sku: 'FUN-BLK-S', colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 4 },
    { sku: 'FUN-BLK-M', colorName: 'مشکی', colorHex: '#111111', size: 'M', stockQuantity: 0 },
    { sku: 'FUN-WHT-S', colorName: 'سفید', colorHex: '#FFFFFF', size: 'S', stockQuantity: 2 },
  ],
  images: [
    {
      storagePath: 'commerce/funnel/main.jpg',
      publicUrl: 'https://example.invalid/funnel/main.jpg',
      displayOrder: 0,
      isPrimary: true,
    },
    {
      storagePath: 'commerce/funnel/detail.jpg',
      publicUrl: 'https://example.invalid/funnel/detail.jpg',
      displayOrder: 1,
    },
  ],
};

const SHOMIZ_PAYLOAD: ProductCreatePayload = {
  categoryId: 'cat-2',
  title: 'شومیز قیف',
  slug: SHOMIZ_SLUG,
  basePrice: SHOMIZ_PRICE,
  discountPrice: null,
  descriptionRaw: 'شومیز ساده.',
  descriptionHtml: '<p>شومیز ساده.</p>',
  fabricType: 'کرپ',
  season: 'بهار',
  status: 'PUBLISHED',
  variants: [
    { sku: 'FUN-SHZ-38', colorName: 'آبی', colorHex: '#0000FF', size: '38', stockQuantity: 5 },
  ],
  images: [],
};

describe('D-172 §3 — the storefront funnel, end to end (hermetic)', () => {
  const repository: CommerceRepository = createMemoryRepository({
    coupons: [
      { code: COUPON_CODE, discountType: 'PERCENT', discountValue: 10, usageLimit: 2 },
    ],
  });
  const variantIds: Record<string, string> = {};

  /** The merchant grid's row for a SKU — the same read the panel renders. */
  async function inventoryRow(sku: string): Promise<InventoryRow> {
    const rows = await repository.listInventory();
    const row = rows.find((entry) => entry.variantId === variantIds[sku]);
    assert.ok(row, `the merchant grid must have a row for ${sku}`);
    return row;
  }

  async function stockOf(sku: string): Promise<number> {
    return (await inventoryRow(sku)).stockQuantity;
  }

  /** The draft the checkout form builds: straight from the persisted cart. */
  function draftFromCart(overrides: Partial<CheckoutDraft> = {}): CheckoutDraft {
    return {
      customer: {
        fullName: 'زهرا محمدی',
        phoneNumber: '09123456789',
        address: 'تهران، خیابان ولیعصر، پلاک ۱۲، واحد ۳',
        postalCode: '1999999999',
      },
      couponCode: COUPON_CODE,
      shippingMethodId: DEFAULT_SHIPPING_METHOD_ID,
      lines: getCartSnapshot().lines.map((line) => ({
        variantId: line.variantId,
        quantity: line.quantity,
      })),
      ...overrides,
    };
  }

  before(async () => {
    for (const payload of [MANTO_PAYLOAD, SHOMIZ_PAYLOAD]) {
      const created = await createProduct(repository, payload);
      assert.ok(created.ok, `the fixture product must be written: ${JSON.stringify(created)}`);
      payload.variants.forEach((variant, index) => {
        const id = created.variantIds[index];
        assert.ok(id, `the fixture variant ${variant.sku} must have been created`);
        variantIds[variant.sku as string] = id;
      });
    }

    // A DRAFT product the customer must never meet, on any read path.
    const draft = await createProduct(repository, {
      ...MANTO_PAYLOAD,
      title: 'مانتو منتشرنشده',
      slug: DRAFT_SLUG,
      status: 'DRAFT',
      variants: [
        { sku: 'FUN-DRAFT-1', colorName: 'مشکی', colorHex: '#111111', size: 'S', stockQuantity: 9 },
      ],
      images: [],
    });
    assert.ok(draft.ok, 'the draft fixture must be written');
    variantIds['FUN-DRAFT-1'] = draft.variantIds[0] as string;
  });

  it('stage 1 — catalog: the grid lists it, the facets narrow to it, the draft is invisible', async () => {
    const cards = await listPublishedProducts(repository);
    assert.deepEqual(
      cards.map((card) => card.slug).sort(),
      [MANTO_SLUG, SHOMIZ_SLUG].sort(),
      'exactly the two published products',
    );

    const narrowed = applyFilters(cards, {
      ...EMPTY_CATALOG_FILTERS,
      category: 'مانتو',
      sizes: ['M'],
      onlyAvailable: true,
    });
    assert.deepEqual(narrowed.map((card) => card.slug), [MANTO_SLUG]);

    assert.deepEqual(
      applyFilters(cards, { ...EMPTY_CATALOG_FILTERS, query: 'شومیز' }).map((card) => card.slug),
      [SHOMIZ_SLUG],
    );
    assert.equal(await getPublishedProduct(repository, DRAFT_SLUG), null);
    assert.deepEqual(
      (await listPublishedProducts(repository)).map((card) => card.slug).includes(DRAFT_SLUG),
      false,
    );
  });

  it('stage 2 — PDP: the colour × size matrix opens on a sellable colour and disables the sold-out cell', async () => {
    const product = await getPublishedProduct(repository, MANTO_SLUG);
    assert.ok(product, 'the PDP read model must exist');

    const colors = colorOptions(product.variants);
    assert.deepEqual(colors.map((color) => color.name), ['مشکی', 'سفید']);
    assert.equal(colors[0]?.sellable, true);
    assert.equal(defaultColor(product.variants), 'مشکی', 'the first SELLABLE colour opens');

    const black = sizeOptions(product.sizes, product.variants, 'مشکی');
    assert.deepEqual(
      black.map((cell) => [cell.size, cell.variant?.level ?? null, cell.available]),
      [
        ['S', 'IN', true],
        ['M', 'OUT', false],
      ],
      'the sold-out M stays visible and disabled instead of disappearing',
    );
    assert.deepEqual(product.sizes, ['S', 'M']);
    assert.equal(selectionLevel(product.variants, 'مشکی', 'M'), 'OUT');
    assert.equal(canAddVariant(findVariant(product.variants, 'مشکی', 'M')), false);
    assert.equal(
      selectionCap(selectionLevel(product.variants, 'مشکی', 'M')),
      0,
      'a sold-out cell cannot be added at all',
    );

    const white = sizeOptions(product.sizes, product.variants, 'سفید');
    assert.deepEqual(
      white.map((cell) => [cell.size, cell.available]),
      [
        ['S', true],
        ['M', false],
      ],
      'this colour has no M, so that cell is empty — not merely sold out',
    );
    assert.equal(selectionLevel(product.variants, 'سفید', 'S'), 'LOW');
  });

  it('stage 3 — cart: the chosen cells become lines in the drawer, persisted and merged', async () => {
    const product = await getPublishedProduct(repository, MANTO_SLUG);
    assert.ok(product);

    const blackSmall = findVariant(product.variants, 'مشکی', 'S');
    const whiteSmall = findVariant(product.variants, 'سفید', 'S');
    assert.ok(blackSmall && whiteSmall, 'both chosen cells must exist');
    assert.equal(blackSmall.variantId, variantIds['FUN-BLK-S']);
    assert.equal(whiteSmall.variantId, variantIds['FUN-WHT-S']);

    addCartLine(toCartLine(product, blackSmall, 2));
    addCartLine(toCartLine(product, whiteSmall, 2));

    const snapshot = getCartSnapshot();
    assert.equal(snapshot.hydrated, true);
    assert.deepEqual(
      snapshot.lines.map((line) => [line.variantId, line.quantity, line.unitPrice]),
      [
        [variantIds['FUN-BLK-S'], 2, DISCOUNT_PRICE],
        [variantIds['FUN-WHT-S'], 2, DISCOUNT_PRICE],
      ],
      'the drawer holds what the PDP priced, at the server-resolved product price',
    );

    // Persistence: what a reload would read back is exactly what the drawer shows.
    assert.deepEqual(parseStoredCart(store.get(CART_STORAGE_KEY) ?? null), snapshot.lines);

    // Re-adding the same size merges into one line instead of duplicating it.
    addCartLine(toCartLine(product, blackSmall, 1));
    assert.equal(getCartSnapshot().lines.length, 2);
    assert.equal(getCartSnapshot().lines[0]?.quantity, 3);

    // The drawer's stepper can lower a line again, and checkout takes exactly
    // what the drawer shows — never the sum of an earlier path to the same cart.
    setCartLineQuantity(blackSmall.variantId, 2);
    assert.deepEqual(
      getCartSnapshot().lines.map((line) => line.quantity),
      [2, 2],
    );
  });

  it('stage 4 — pre-flight: the drawer is warned, non-authoritatively, and the cart is corrected', async () => {
    const product = await getPublishedProduct(repository, MANTO_SLUG);
    assert.ok(product);
    const whiteSmall = findVariant(product.variants, 'سفید', 'S');
    assert.ok(whiteSmall);

    // The customer asks for more of the «موجودی محدود» colour than exists. The
    // pre-flight is the only place that can say so BEFORE an order is written.
    const checked = await checkAvailability(repository, [
      { variantId: whiteSmall.variantId, quantity: 4 },
    ]);
    assert.ok(checked.ok, 'the pre-flight answers, it does not refuse');
    assert.equal(checked.lines[0]?.available, false);
    assert.equal(checked.lines[0]?.level, 'LOW');
    assert.equal(checked.lines[0]?.effectivePrice, DISCOUNT_PRICE);

    // It wrote nothing: the grid still shows the shelf as it was.
    assert.equal(await stockOf('FUN-WHT-S'), 2);
    assert.equal(await stockOf('FUN-BLK-S'), 4);

    setCartLineQuantity(whiteSmall.variantId, 2);
    const corrected = await checkAvailability(repository, [{ variantId: whiteSmall.variantId, quantity: 2 }]);
    assert.ok(corrected.ok);
    assert.equal(corrected.lines[0]?.available, true, 'the corrected quantity can be bought');
    assert.deepEqual(
      parseStoredCart(store.get(CART_STORAGE_KEY) ?? null),
      getCartSnapshot().lines,
      'the correction is persisted too',
    );
  });

  it('stage 5 — checkout: the order is written PENDING, priced server-side, and the stock is consumed', async () => {
    const placed = await placeCheckoutOrder(repository, mockPaymentGateway, draftFromCart());
    assert.ok(placed.ok, `the funnel must complete: ${JSON.stringify(placed)}`);

    const subtotal = DISCOUNT_PRICE * 4;
    const expected = computeCheckoutTotals({
      subtotal,
      discount: Math.floor(subtotal / 10),
      shipping: SHIPPING,
    });
    assert.deepEqual(placed.totals, expected, 'the browser computed none of these numbers');
    assert.equal(placed.couponApplied, true);
    assert.equal(placed.status, 'PENDING');
    assert.equal(
      placed.payment.status,
      'UNAVAILABLE',
      'no gateway is connected, so nothing is claimed to have been charged (AC-8)',
    );

    const order = await getOrder(repository, placed.orderId);
    assert.equal(order?.status, 'PENDING');
    assert.equal(order?.itemCount, 4);
    assert.deepEqual(
      order?.items.map((item) => [item.sku, item.quantity, item.unitPrice]).sort(),
      [
        ['FUN-BLK-S', 2, DISCOUNT_PRICE],
        ['FUN-WHT-S', 2, DISCOUNT_PRICE],
      ].sort(),
      'order_items carries the server-resolved price per line',
    );

    // Phase 4 transition: the order's audit trail opens with THIS checkout —
    // `fromStatus` NULL because nothing preceded it, and the STOREFRONT source
    // because the customer, not the merchant and not a callback, created it.
    assert.deepEqual(
      (await repository.listOrderStatusHistory(placed.orderId)).map((row) => [
        row.fromStatus,
        row.toStatus,
        row.source,
      ]),
      [[null, 'PENDING', 'STOREFRONT']],
    );

    // The confirmation screen empties the drawer, and storage agrees.
    clearCart();
    assert.deepEqual(getCartSnapshot().lines, []);
    assert.equal(store.get(CART_STORAGE_KEY), '[]');
  });

  it('stage 6 — reconciliation: the merchant grid shows the order immediately, and the badges follow', async () => {
    const soldOutCell = await inventoryRow('FUN-WHT-S');
    const reducedCell = await inventoryRow('FUN-BLK-S');

    assert.equal(soldOutCell.stockQuantity, 0, 'the basket emptied this variant');
    assert.equal(reducedCell.stockQuantity, 2, 'and reduced this one to its low-stock level');

    assert.equal(stockState(reducedCell).code, 'LOW_STOCK', '4 → 2 crosses INTO low stock');
    assert.equal(stockState(soldOutCell).code, 'OUT_OF_STOCK');
    assert.equal(stockState(soldOutCell).label, 'ناموجود');

    const rows = await repository.listInventory();
    // Five rows: the merchant grid also carries the DRAFT product's variant (a
    // draft is hidden from the storefront, never from its owner).
    assert.deepEqual(inventorySummary(rows), { total: 5, low: 1, out: 2, inactive: 0 });
    assert.deepEqual(
      filterInventory(rows, 'out')
        .map((row) => row.sku)
        .sort(),
      ['FUN-BLK-M', 'FUN-WHT-S'],
      'the «ناموجود» chip lists exactly the variants with nothing on the shelf',
    );

    // The same read the customer gets: the sold-out colour can no longer be
    // chosen, and the colour that was bought down now reads «موجودی محدود».
    const product = await getPublishedProduct(repository, MANTO_SLUG);
    assert.ok(product);
    const colors = colorOptions(product.variants);
    assert.deepEqual(
      colors.map((color) => [color.name, color.sellable]),
      [
        ['مشکی', true],
        ['سفید', false],
      ],
      'the storefront reconciles with the merchant grid from ONE stock read',
    );
    assert.deepEqual(
      sizeOptions(product.sizes, product.variants, 'سفید').map((cell) => [cell.size, cell.available]),
      [
        ['S', false],
        ['M', false],
      ],
    );
  });

  it('stage 7 — cancellation: the stock comes back to the grid, exactly once, and the coupon stays redeemed', async () => {
    const placed = (await repository.listOrders())[0];
    assert.ok(placed, 'the order from stage 5 must be listed');
    assert.deepEqual(await transitionOrder(repository, placed.id, 'CANCELLED', MERCHANT_TRANSITION), { ok: true });

    for (const [sku, quantity] of Object.entries(STARTING_STOCK)) {
      assert.equal(await stockOf(sku), quantity, `${sku} must be back to its opening quantity`);
    }
    assert.deepEqual(
      inventorySummary(await repository.listInventory()),
      { total: 5, low: 1, out: 1, inactive: 0 },
      'the grid returns to its pre-order state',
    );

    const again = await transitionOrder(repository, placed.id, 'CANCELLED', MERCHANT_TRANSITION);
    assert.ok(!again.ok, 'CANCELLED is terminal');
    assert.equal(await stockOf('FUN-WHT-S'), 2, 'a refused second cancellation restocks nothing');

    const coupon = await repository.findCouponByCode(COUPON_CODE);
    assert.equal(
      coupon?.usedCount,
      1,
      'a redeemed code stays redeemed: the discount counter is never refunded',
    );
    assert.equal((await getOrder(repository, placed.id))?.status, 'CANCELLED');

    // Phase 4 transition: the trail tells the whole story of this order — where
    // it began and who ended it — and the REFUSED second cancellation above added
    // nothing to it, which is what makes the trail trustworthy after a retry.
    assert.deepEqual(
      (await repository.listOrderStatusHistory(placed.id)).map((row) => [
        row.fromStatus,
        row.toStatus,
        row.source,
      ]),
      [
        [null, 'PENDING', 'STOREFRONT'],
        ['PENDING', 'CANCELLED', 'MERCHANT_PANEL'],
      ],
    );
  });

  it('stage 8 — fail-closed: with no canonical connection the funnel refuses loudly instead of faking an order', async (context) => {
    if (process.env.DATABASE_URL?.trim()) {
      context.skip('DATABASE_URL is set — this assertion covers the UNCONFIGURED path only');
      return;
    }

    const before = await repository.listOrders();
    // The REAL entry point the form calls, with the customer's own draft: the
    // environment gate runs BEFORE any rule, so an unconfigured storefront
    // refuses the submission instead of half-processing it.
    const refused = await placeOrderAction(draftFromCart());
    assert.ok(!refused.ok, 'an unconfigured storefront must not accept an order');
    assert.equal(refused.code, 'DB_NOT_CONFIGURED');
    assert.equal(refused.message, DB_NOT_CONFIGURED_MESSAGE);
    assert.equal((await repository.listOrders()).length, before.length, 'nothing was written');
  });
});
