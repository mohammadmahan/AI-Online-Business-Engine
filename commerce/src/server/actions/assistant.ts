'use server';

import { hasAdminSession } from '../auth/admin-request';
import {
  handleAssistantRequest,
  type AssistantResult,
} from '../ai/assistant';

/**
 * D-172 §4.1 — the merchant's AI copy assistant.
 *
 * The proxy already guards `/admin/**`, but a Server Action id is a global URL:
 * the session is re-checked here before the bridge is contacted. The action is
 * read-only: it returns a dry-run proposal and never writes a product, order,
 * HITL row or file.
 */
export async function generateAssistantCopyAction(
  input: unknown,
): Promise<AssistantResult> {
  return handleAssistantRequest(input, { authorized: await hasAdminSession() });
}
