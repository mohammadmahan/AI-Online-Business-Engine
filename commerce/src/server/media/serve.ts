import { readFile } from 'node:fs/promises';
import path from 'node:path';

/**
 * D-172 §2.1 — read side of the local media store (`GET /media/[...path]`).
 *
 * Public by necessity: a storefront customer must see the product photo without
 * a session. That is safe because the store is WRITE-ONLY from the outside (the
 * adapter derives every key from a content hash), and because this reader is
 * deliberately narrow:
 *
 *  - only `jpg`, `png` and `webp` are served, with a fixed content type — no
 *    extension guessing, no `text/html`, no SVG;
 *  - path segments are restricted to a conservative character set, and the
 *    resolved path must stay INSIDE the store (defence against `..` and against
 *    a symlinked-parent trick, which is why the check is on the resolved path);
 *  - a missing file, a directory, an oversized path or a traversal attempt is the
 *    same answer: 404, with no reason stated.
 *
 * Pure path/IO logic lives here (not in the route) so it is unit tested without
 * HTTP.
 */

const CONTENT_TYPES: Record<string, string> = {
  jpg: 'image/jpeg',
  png: 'image/png',
  webp: 'image/webp',
};

/** Deep enough for `products/sha256/ab/<hash>.jpg`, not for arbitrary trees. */
const MAX_SEGMENTS = 6;
const SEGMENT_RE = /^[A-Za-z0-9][A-Za-z0-9._-]*$/;

export interface ServedMedia {
  bytes: Buffer;
  contentType: string;
  byteLength: number;
}

function isSafeSegment(segment: string): boolean {
  return segment.length <= 128 && SEGMENT_RE.test(segment) && !segment.includes('..');
}

/**
 * Maps request segments to an absolute file inside `root`, or `null` when the
 * request is not a servable media path.
 */
export function resolveMediaFilePath(root: string, segments: readonly string[]): string | null {
  if (segments.length === 0 || segments.length > MAX_SEGMENTS) {
    return null;
  }
  if (!segments.every(isSafeSegment)) {
    return null;
  }

  const absoluteRoot = path.resolve(root);
  const resolved = path.resolve(absoluteRoot, ...segments);
  if (!resolved.startsWith(`${absoluteRoot}${path.sep}`)) {
    return null;
  }

  const extension = path.extname(resolved).slice(1).toLowerCase();
  if (!Object.prototype.hasOwnProperty.call(CONTENT_TYPES, extension)) {
    return null;
  }
  return resolved;
}

export function contentTypeForMediaPath(filePath: string): string | null {
  const extension = path.extname(filePath).slice(1).toLowerCase();
  return CONTENT_TYPES[extension] ?? null;
}

/** Reads a stored image, or `null` for anything the store should not answer. */
export async function readLocalMediaFile(
  root: string,
  segments: readonly string[],
): Promise<ServedMedia | null> {
  const filePath = resolveMediaFilePath(root, segments);
  if (filePath === null) {
    return null;
  }
  const contentType = contentTypeForMediaPath(filePath);
  if (contentType === null) {
    return null;
  }
  try {
    const bytes = await readFile(filePath);
    return { bytes, contentType, byteLength: bytes.byteLength };
  } catch {
    return null;
  }
}
