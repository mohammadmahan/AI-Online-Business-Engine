import type { CommerceActionResult } from '../db-context';
import { withRepository } from '../db-context';
import type { CommerceRepository } from '../repository';
import { ADMIN_REQUIRED_MESSAGE } from './admin-auth';
import { hasAdminSession } from './admin-request';

/**
 * D-172 Phase 4 — the repository gate every ADMIN server action goes through.
 *
 * The proxy already refuses an unauthenticated request, so in the normal flow
 * this is a second check. It exists because a Server Action has its own entry
 * point: an action id is a global URL, and the proxy's path rule alone does not
 * describe which repository operation a POST is allowed to perform. Stating the
 * requirement next to the write means the guard cannot be lost by adding a new
 * action or by moving one under a different route.
 *
 * Storefront actions keep plain `withRepository`: a customer placing an order is
 * not an admin.
 */
export async function withAdminRepository<T>(
  fn: (repository: CommerceRepository) => Promise<CommerceActionResult<T>>,
): Promise<CommerceActionResult<T>> {
  if (!(await hasAdminSession())) {
    return { ok: false, code: 'UNAUTHORIZED', message: ADMIN_REQUIRED_MESSAGE };
  }
  return withRepository(fn);
}
