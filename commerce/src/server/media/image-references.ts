import type { ValidationIssue } from '@/lib/validation';

import {
  MEDIA_NOT_CONFIGURED_MESSAGE,
  mediaPublicPrefix,
  type MediaEnvironment,
} from '../media';
import { validateStoredImageReference } from './reference';

/**
 * D-172 §2.1 — the ONE media-reference gate every product image write uses.
 *
 * Creation, product updates and the gallery editor all submit path/url pairs
 * from the browser, so they must agree on exactly what this store produced. A
 * gallery row is accepted only when its path is a content address written by
 * the upload edge AND its public URL is exactly the URL the configured provider
 * publishes for that path. Empty lists are allowed (media is optional); a
 * submitted reference is never trusted on its shape alone.
 */
export interface ProductImageReferenceInput {
  storagePath: string;
  publicUrl: string;
  /** The gallery slot this reference occupies, used in the field-level error. */
  displayOrder?: number;
}

export type ProductImageReferenceValidation =
  | { ok: true }
  | {
      ok: false;
      code: 'MEDIA_NOT_CONFIGURED' | 'VALIDATION_ERROR';
      issues: ValidationIssue[];
    };

export function validateImageReferences(
  images: readonly ProductImageReferenceInput[],
  env: MediaEnvironment = process.env,
): ProductImageReferenceValidation {
  if (images.length === 0) {
    return { ok: true };
  }
  if (mediaPublicPrefix(env) === null) {
    return {
      ok: false,
      code: 'MEDIA_NOT_CONFIGURED',
      issues: [{ field: 'images', message: MEDIA_NOT_CONFIGURED_MESSAGE }],
    };
  }

  const issues: ValidationIssue[] = [];
  images.forEach((image, index) => {
    const verdict = validateStoredImageReference(image.storagePath, image.publicUrl, env);
    if (!verdict.ok) {
      const slot = image.displayOrder ?? index;
      issues.push({ field: `images.${slot}.publicUrl`, message: verdict.message });
    }
  });

  return issues.length === 0
    ? { ok: true }
    : { ok: false, code: 'VALIDATION_ERROR', issues };
}
