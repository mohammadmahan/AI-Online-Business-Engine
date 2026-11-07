'use server';

import { revalidatePath } from 'next/cache';

import type { CategoryCreatePayload } from '@/contracts/catalog';

import { withAdminRepository } from '../auth/with-admin';
import type { CommerceActionResult } from '../db-context';
import { createCategory } from '../services/categories';

/**
 * D-172 §1.1 — the merchant's category write path.
 *
 * One action, because this surface deliberately supports creation only: renaming
 * a category is a copy change on the storefront, and deleting one is blocked by
 * the products that reference it (FK RESTRICT). Both deserve a design decision,
 * not a button added here by accident.
 */
export async function createCategoryAction(
  payload: CategoryCreatePayload,
): Promise<CommerceActionResult<{ categoryId: string; name: string; slug: string }>> {
  const result = await withAdminRepository(async (repository) => {
    const created = await createCategory(repository, payload);
    return created.ok
      ? {
          ok: true as const,
          data: {
            categoryId: created.category.id,
            name: created.category.name,
            slug: created.category.slug,
          },
        }
      : {
          ok: false as const,
          code: created.code,
          message: created.message,
          field: created.issues?.[0]?.field,
        };
  });

  if (result.ok) {
    revalidatePath('/admin/categories');
    // The product form's dropdown reads the same rows; without this the merchant
    // would create a category and still not find it one click away.
    revalidatePath('/admin/products/new');
    revalidatePath('/catalog');
  }
  return result;
}
