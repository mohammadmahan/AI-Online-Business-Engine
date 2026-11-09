import type { ProductImageSelectionEntry } from '@/contracts/catalog';

/**
 * D-172 §2.1 — the gallery edit's PURE rules.
 *
 * The road map's multi-image uploader was written for NEW products only, so an
 * existing product's gallery could not be changed at all. Editing one means
 * mixing three kinds of slot in a single ordered list: a row the product already
 * owns (referenced by id), a freshly stored image (referenced by the pair the
 * upload edge returned), and nothing (a slot the merchant removed by leaving it
 * out). The browser and the server must agree on what that list means, so the
 * normalisation lives here, with no IO and no environment: the server adds the
 * media-provider check separately (`@/server/media/reference`).
 *
 * Why the distinction matters: an EXISTING row is never re-validated. A gallery
 * attached before this feature may hold a path+URL pair this build would not
 * produce (the pre-G-5 externally hosted mode), and refusing to save such a
 * product's gallery would be a regression, not a safety gain. New references are
 * checked strictly.
 */

export interface NormalizedImageKeep {
  id: string;
  displayOrder: number;
  isPrimary: boolean;
}

export interface NormalizedImageAdd {
  storagePath: string;
  publicUrl: string;
  displayOrder: number;
  isPrimary: boolean;
}

export interface NormalizedImageSelection {
  keep: NormalizedImageKeep[];
  add: NormalizedImageAdd[];
}

export type ImageSelectionResult =
  | { ok: true; selection: NormalizedImageSelection }
  | { ok: false; message: string; field: string };

function issue(field: string, message: string): ImageSelectionResult {
  return { ok: false, field, message };
}

/**
 * Splits the merchant's ordered slots into the rows to KEEP (with their new
 * order/primary flags) and the rows to ADD, or explains why the list is invalid.
 *
 * Rules, all of them refusals rather than repairs:
 *  - exactly one form per slot (id XOR storagePath+publicUrl);
 *  - the same existing row may not appear twice, and neither may the same stored
 *    object (a gallery showing one photo twice is a mistake, not a layout);
 *  - at most one primary;
 *  - an empty gallery is allowed — a merchant may remove every association, and
 *    the roadmap treats media as optional (§1.4).
 *
 * When no slot is marked primary and the list is not empty, the FIRST slot
 * becomes primary — the same default the create path already applies
 * (`createProduct` uses `index === 0`), so a gallery is never left with photos
 * but no primary.
 */
export function normalizeImageSelection(
  entries: readonly ProductImageSelectionEntry[],
): ImageSelectionResult {
  if (!Array.isArray(entries)) {
    return issue('images', 'فهرست تصویرها معتبر نیست.');
  }

  const keep: NormalizedImageKeep[] = [];
  const add: NormalizedImageAdd[] = [];
  const seenIds = new Set<string>();
  const seenPaths = new Set<string>();

  for (const [index, entry] of entries.entries()) {
    const object = typeof entry === 'object' && entry !== null ? entry : {};
    const id = typeof object.id === 'string' ? object.id.trim() : '';
    const storagePath = typeof object.storagePath === 'string' ? object.storagePath.trim() : '';
    const publicUrl = typeof object.publicUrl === 'string' ? object.publicUrl.trim() : '';

    if (id !== '' && (storagePath !== '' || publicUrl !== '')) {
      return issue(
        `images.${index}`,
        'یک تصویر نمی‌تواند هم شناسهٔ موجود داشته باشد و هم نشانی تازه؛ یکی را انتخاب کنید.',
      );
    }

    if (id === '') {
      if (storagePath === '' || publicUrl === '') {
        return issue(
          `images.${index}`,
          'هر تصویر تازه به مسیر ذخیره‌سازی و نشانی عمومی نیاز دارد.',
        );
      }
      if (seenPaths.has(storagePath)) {
        return issue(`images.${index}`, 'یک تصویر دو بار در گالری تکرار شده است.');
      }
      seenPaths.add(storagePath);
      add.push({ storagePath, publicUrl, displayOrder: index, isPrimary: false });
      continue;
    }

    if (seenIds.has(id)) {
      return issue(`images.${index}`, 'یک تصویر دو بار در گالری تکرار شده است.');
    }
    seenIds.add(id);
    keep.push({ id, displayOrder: index, isPrimary: false });
  }

  const flagged = entries.filter((entry) => entry?.isPrimary === true).length;
  if (flagged > 1) {
    return issue('images', 'فقط یک تصویر می‌تواند تصویر اصلی باشد.');
  }

  const primaryId =
    entries.find((entry) => entry?.isPrimary === true)?.id?.trim() ?? '';
  const primaryIndex = entries.findIndex((entry) => entry?.isPrimary === true);

  for (const entry of keep) {
    entry.isPrimary = primaryId !== '' && entry.id === primaryId;
  }
  for (const entry of add) {
    entry.isPrimary = primaryIndex >= 0 && entry.displayOrder === primaryIndex;
  }
  if (flagged === 0 && entries.length > 0) {
    if (keep.length > 0) {
      keep[0]!.isPrimary = true;
    } else if (add.length > 0) {
      add[0]!.isPrimary = true;
    }
  }

  return { ok: true, selection: { keep, add } };
}

/** The same slot order the gallery renders, so a test can assert it without SQL. */
export function orderedSlotKeys(selection: NormalizedImageSelection): string[] {
  return [...selection.keep, ...selection.add]
    .sort((left, right) => left.displayOrder - right.displayOrder)
    .map((entry) => ('id' in entry ? `id:${entry.id}` : `path:${entry.storagePath}`));
}
