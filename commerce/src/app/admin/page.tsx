import type { Metadata } from 'next';
import Link from 'next/link';

import { ConnectionMissing } from '@/components/admin/connection-notice';
import { Badge, Card, CardHeader, PageHeader, Table, Td, Th, buttonClass } from '@/components/ui/primitives';
import { formatCountFa, formatToman } from '@/lib/format';
import { inventorySummary, LOW_STOCK_THRESHOLD } from '@/lib/inventory-rules';
import { getRepository } from '@/server/db-context';
import { listProducts } from '@/server/services/products';

/**
 * D-172 §2 — panel overview.
 *
 * A server component: it reads the repository directly and renders what is
 * actually stored. When no canonical connection exists it says so and shows
 * nothing else — the panel never renders zeros that would read as measurements
 * (D-171 §2.2).
 */

export const metadata: Metadata = { title: 'نمای کلی' };

// An admin surface is per-request by definition: its numbers must never be
// frozen into a build-time render.
export const dynamic = 'force-dynamic';

export default async function AdminOverviewPage() {
  const repository = getRepository();
  if (repository === null) {
    return (
      <>
        <PageHeader
          title="نمای کلی"
          description="وضعیت محصولات، موجودی و سفارش‌های فروشگاه."
        />
        <ConnectionMissing what="فهرست محصولات" />
      </>
    );
  }

  const [products, inventory] = await Promise.all([
    listProducts(repository),
    repository.listInventory(),
  ]);
  const summary = inventorySummary(inventory, LOW_STOCK_THRESHOLD);

  return (
    <>
      <PageHeader
        title="نمای کلی"
        description="وضعیت محصولات، موجودی و سفارش‌های فروشگاه."
      />

      <div className="mb-4 grid gap-4 sm:grid-cols-3">
        <Card>
          <CardHeader title="محصولات" description="تعداد محصولات ثبت‌شده." />
          <p className="text-cp-display font-bold text-ink">{formatCountFa(products.length)}</p>
          <Link className={buttonClass.neutral} href="/admin/products/new">
            افزودن محصول
          </Link>
        </Card>
        <Card>
          <CardHeader
            title="موجودی کم و ناموجود"
            description={`آستانهٔ هشدار: ${formatCountFa(LOW_STOCK_THRESHOLD)} عدد.`}
          />
          <p className="flex flex-wrap items-center gap-2">
            <Badge tone="warning">
              موجودی کم <span className="cp-code">{formatCountFa(summary.low)}</span>
            </Badge>
            <Badge tone="danger">
              ناموجود <span className="cp-code">{formatCountFa(summary.out)}</span>
            </Badge>
          </p>
          <Link className={buttonClass.neutral} href="/admin/inventory">
            ویرایش موجودی و قیمت
          </Link>
        </Card>
        <Card>
          <CardHeader title="پردازش سفارش‌ها" description="تغییر وضعیت، کد رهگیری و فاکتور." />
          <p className="text-cp-label text-ink-muted">
            مسیرهای مجاز تغییر وضعیت و ثبت کد رهگیری در همین بخش انجام می‌شود.
          </p>
          <Link className={buttonClass.neutral} href="/admin/orders">
            فهرست سفارش‌ها
          </Link>
        </Card>
      </div>

      <Card>
        <CardHeader
          title="محصولات"
          description="تعداد گونه‌ها و تصویرهای هر محصول."
          action={
            <Link className={buttonClass.neutral} href="/admin/promotions">
              کدهای تخفیف
            </Link>
          }
        />
        {products.length === 0 ? (
          <p className="rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
            هنوز محصولی ثبت نشده است؛ از «افزودن محصول» شروع کنید.
          </p>
        ) : (
          <Table
            caption="فهرست محصولات"
            head={
              <tr>
                <Th>عنوان</Th>
                <Th>نشانی</Th>
                <Th>وضعیت</Th>
                <Th>قیمت پایه</Th>
                <Th>قیمت تخفیف‌دار</Th>
                <Th>گونه‌ها</Th>
                <Th>تصویرها</Th>
              </tr>
            }
          >
            {products.map((product) => (
              <tr key={product.id}>
                <Td>{product.title}</Td>
                <Td>
                  <span className="cp-code">{product.slug}</span>
                </Td>
                <Td>
                  <Badge tone={product.status === 'PUBLISHED' ? 'success' : 'neutral'}>
                    {product.status === 'PUBLISHED' ? 'منتشرشده' : 'پیش‌نویس'}{' '}
                    <span className="cp-code">{product.status}</span>
                  </Badge>
                </Td>
                <Td>{formatToman(product.basePrice)}</Td>
                <Td>{product.discountPrice === null ? '—' : formatToman(product.discountPrice)}</Td>
                <Td>{formatCountFa(product.variantCount)}</Td>
                <Td>{formatCountFa(product.imageCount)}</Td>
              </tr>
            ))}
          </Table>
        )}
      </Card>
    </>
  );
}
