/**
 * D-172 §2.1 — client-side image compression.
 *
 * Browser-only (uses `createImageBitmap` + canvas). It is imported exclusively
 * by the uploader client component; nothing server-side may import this module.
 *
 * The rules come from §2.1: auto-compression and ASPECT RATIO LOCKING. The
 * longest edge is capped and both dimensions are scaled by the same factor, so
 * the preview the merchant approves is exactly the shape that will be uploaded
 * once a media provider exists (G-5).
 */

export const MAX_EDGE_PX = 1600;
export const JPEG_QUALITY = 0.8;

export interface CompressedImage {
  dataUrl: string;
  width: number;
  height: number;
  /** Approximate byte size of the encoded payload (base64 → bytes). */
  bytes: number;
}

export async function compressImage(
  file: File,
  maxEdge = MAX_EDGE_PX,
  quality = JPEG_QUALITY,
): Promise<CompressedImage> {
  const bitmap = await createImageBitmap(file);
  try {
    const longest = Math.max(bitmap.width, bitmap.height);
    const scale = longest > maxEdge ? maxEdge / longest : 1;
    const width = Math.max(1, Math.round(bitmap.width * scale));
    const height = Math.max(1, Math.round(bitmap.height * scale));

    const canvas = document.createElement('canvas');
    canvas.width = width;
    canvas.height = height;
    const context = canvas.getContext('2d');
    if (context === null) {
      throw new Error('canvas 2d context unavailable');
    }
    context.drawImage(bitmap, 0, 0, width, height);

    const dataUrl = canvas.toDataURL('image/jpeg', quality);
    const base64 = dataUrl.slice(dataUrl.indexOf(',') + 1);
    return { dataUrl, width, height, bytes: Math.round((base64.length * 3) / 4) };
  } finally {
    bitmap.close();
  }
}

/** Persian-digit byte size for the preview caption. */
export function formatByteSize(bytes: number): string {
  const units = ['بایت', 'کیلوبایت', 'مگابایت'];
  let value = bytes;
  let unit = 0;
  while (value >= 1024 && unit < units.length - 1) {
    value /= 1024;
    unit += 1;
  }
  const rounded = unit === 0 ? Math.round(value) : Math.round(value * 10) / 10;
  const text = rounded.toLocaleString('fa-IR');
  return `${text} ${units[unit] ?? 'بایت'}`;
}
