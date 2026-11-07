import type { Metadata } from 'next';

import { CategoryManager } from '@/components/admin/category-manager';
import { ConnectionMissing } from '@/components/admin/connection-notice';
import { PageHeader } from '@/components/ui/primitives';
import { listCategoryAdminRows } from '@/server/services/categories';
import { getRepository } from '@/server/db-context';

/**
 * D-172 §1.1 — category management.
 *
 * Categories are read on the server; the create form posts a Server Action that
 * revalidates this page AND the product form, so a new category is immediately
 * selectable where a merchant needs it. An absent database is stated, never
 * rendered as an empty table that would look like "no categories exist".
 */

export const metadata: Metadata = { title: 'دسته‌بندی‌ها' };
export const dynamic = 'force-dynamic';

export default async function CategoriesPage() {
  const repository = getRepository();
  if (repository === null) {
    return (
      <>
        <PageHeader
          title="دسته‌بندی‌ها"
          description="دسته‌های فروشگاه؛ پیش‌نیاز ثبت محصول."
        />
        <ConnectionMissing what="فهرست دسته‌بندی‌ها" />
      </>
    );
  }

  const categories = await listCategoryAdminRows(repository);

  return (
    <>
      <PageHeader
        title="دسته‌بندی‌ها"
        description="دسته‌ای بسازید تا محصول بتواند به آن تعلق بگیرد. نشانی دسته، آدرس فیلتر فروشگاه است."
      />
      <CategoryManager categories={categories} />
    </>
  );
}
