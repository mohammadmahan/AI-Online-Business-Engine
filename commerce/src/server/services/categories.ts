import type { CategoryCreatePayload } from '@/contracts/catalog';
import { issuesToMessage, validateCategory } from '@/lib/validation';

import type {
  CategoryAdminRow,
  CategoryRecord,
  CommerceRepository,
  NewCategoryInput,
} from '../repository';

/**
 * D-172 §1.1 — category management (server half).
 *
 * Categories are the ONE catalog dimension without a merchant surface before
 * Phase 4: the product form requires one, but the only way to create one was the
 * demo seed script (developer-only, and locked to the throwaway harness). This
 * service is the merchant-reachable path.
 *
 * The slug is the public URL identity (`/catalog?category=<slug>`), so it is
 * validated here AND unique in the database; both checks are kept because the
 * pre-check produces the field message and the UNIQUE constraint still holds if
 * two tabs submit the same slug at once.
 */

export type CategoryMutationResult =
  | { ok: true; category: CategoryRecord }
  | {
      ok: false;
      code: 'VALIDATION_ERROR' | 'CONFLICT';
      message: string;
      issues?: Array<{ field: string; message: string }>;
    };

export async function createCategory(
  repo: CommerceRepository,
  payload: CategoryCreatePayload,
): Promise<CategoryMutationResult> {
  const validation = validateCategory(payload);
  if (!validation.ok) {
    return {
      ok: false,
      code: 'VALIDATION_ERROR',
      message: issuesToMessage(validation.issues),
      issues: validation.issues,
    };
  }

  const name = payload.name.trim();
  const slug = payload.slug.trim();
  const description =
    typeof payload.description === 'string' && payload.description.trim() !== ''
      ? payload.description.trim()
      : null;

  const existing = await repo.findCategoryBySlug(slug);
  if (existing !== null) {
    return conflict(slug);
  }

  const input: NewCategoryInput = { name, slug, description };
  const category = await repo.createCategory(input);
  if (category === null) {
    // The database's UNIQUE constraint met a concurrent insert: same refusal.
    return conflict(slug);
  }
  return { ok: true, category };
}

function conflict(slug: string): CategoryMutationResult {
  return {
    ok: false,
    code: 'CONFLICT',
    message: `نشانی «${slug}» قبلاً برای دستهٔ دیگری ثبت شده است.`,
    issues: [{ field: 'slug', message: 'این نشانی تکراری است.' }],
  };
}

export async function listCategoryAdminRows(
  repo: CommerceRepository,
): Promise<CategoryAdminRow[]> {
  return repo.listCategoryAdminRows();
}
