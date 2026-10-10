import { createCommerceDb } from '@/db';

import { createPostgresRepository, type CommerceRepository } from './repository';

/**
 * D-172 Phase 2 — the fail-closed connection context.
 *
 * The admin panel has no credential of its own (D-045): it reads
 * `DATABASE_URL` from the environment at call time, and until that variable
 * exists every write/read path returns `DB_NOT_CONFIGURED` with a Persian
 * explanation for the owner. Nothing is faked, and no default instance is ever
 * guessed — an absent configuration is a refusal, never a pass (D-171 §2.2).
 *
 * The pool is cached per connection string: a Next server keeps one repository
 * for the process instead of opening a pool per action.
 */

export const DB_NOT_CONFIGURED_MESSAGE =
  'اتصال به پایگاهِ دادهٔ مرجع تنظیم نشده است. تا زمانی که متغیر محیطی DATABASE_URL تنظیم نشود، هیچ خواندن یا نوشتنی انجام نمی‌شود.';

export type CommerceActionFailureCode =
  | 'DB_NOT_CONFIGURED'
  | 'MEDIA_NOT_CONFIGURED'
  | 'VALIDATION_ERROR'
  | 'CONFLICT'
  | 'NOT_FOUND'
  | 'ILLEGAL_TRANSITION'
  | 'ILLEGAL_STATE'
  | 'UNEXPECTED';

export interface CommerceActionFailure {
  ok: false;
  code: CommerceActionFailureCode;
  message: string;
  field?: string;
}

export type CommerceActionResult<T> = { ok: true; data: T } | CommerceActionFailure;

let cached: { key: string; repository: CommerceRepository } | null = null;

export function isDatabaseConfigured(): boolean {
  return Boolean(process.env.DATABASE_URL?.trim());
}

/** The repository, or `null` when the environment has no canonical connection. */
export function getRepository(): CommerceRepository | null {
  const url = process.env.DATABASE_URL?.trim();
  if (!url) {
    return null;
  }
  if (cached === null || cached.key !== url) {
    const { db } = createCommerceDb(url);
    cached = { key: url, repository: createPostgresRepository(db) };
  }
  return cached.repository;
}

/**
 * Runs `fn` against the repository with the environment gate applied first.
 * Repository failures are reported by NAME/CODE only — never with the driver's
 * message, which can echo a connection string (D-114/D-124).
 */
export async function withRepository<T>(
  fn: (repository: CommerceRepository) => Promise<CommerceActionResult<T>>,
): Promise<CommerceActionResult<T>> {
  const repository = getRepository();
  if (repository === null) {
    return { ok: false, code: 'DB_NOT_CONFIGURED', message: DB_NOT_CONFIGURED_MESSAGE };
  }
  try {
    return await fn(repository);
  } catch (error) {
    const name = error instanceof Error ? error.name : 'UnknownError';
    const code =
      typeof error === 'object' && error !== null && 'code' in error
        ? String((error as { code: unknown }).code)
        : 'n/a';
    console.error('[commerce] repository call failed', { name, code });
    return {
      ok: false,
      code: 'UNEXPECTED',
      message: 'خطای غیرمنتظره در پایگاهِ داده رخ داد. عملیات انجام نشد.',
    };
  }
}
