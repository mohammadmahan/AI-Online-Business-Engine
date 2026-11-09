'use client';

import { ArrowDown, ArrowUp, Image as ImageIcon, Star, Trash2, Upload } from 'lucide-react';
import { useRef, useState } from 'react';

import type { ProductImageSelectionEntry } from '@/contracts/catalog';
import { formatCountFa } from '@/lib/format';
import { compressImage } from '@/lib/image';
import { updateProductImagesAction } from '@/server/actions/products';
import { cn } from '@/lib/utils';
import { Banner, Badge, buttonClass } from '@/components/ui/primitives';

/**
 * D-172 §2.1 — gallery editor for an existing product (client half).
 *
 * Three deliberate differences from the ingestion uploader, each of them about
 * being an EDITOR rather than a picker:
 *
 *  1. **Uploads happen on selection, not on submit.** The merchant sees each
 *     photo appear with its real stored URL immediately, instead of holding
 *     compressed previews in memory until the whole form is saved.
 *  2. **Existing rows keep their identity.** A row the product already owns is
 *     sent back as an `id`, so reordering it does not delete and re-insert it,
 *     and a legacy gallery (attached before this feature) is never re-validated
 *     against a storage format it predates.
 *  3. **No "external URL" box.** The server only accepts references the
 *     configured media provider itself produced, so offering a free-text URL
 *     field would be a promise this build cannot keep.
 *
 * A removed row is an association removal only: the stored file is
 * content-addressed and may be shared, so nothing is deleted from disk.
 */

export interface EditorImageRow {
  id: string;
  storagePath: string;
  publicUrl: string;
  displayOrder: number;
  isPrimary: boolean;
}

interface EditorEntry {
  /** Stable React key: the row id, or the stored path for a fresh upload. */
  key: string;
  id?: string;
  storagePath: string;
  publicUrl: string;
  isPrimary: boolean;
}

type Result =
  | { kind: 'idle' }
  | { kind: 'busy' }
  | { kind: 'ok'; count: number }
  | { kind: 'error'; message: string; field?: string };

function toEntries(rows: readonly EditorImageRow[]): EditorEntry[] {
  return [...rows]
    .sort((left, right) => left.displayOrder - right.displayOrder)
    .map((row) => ({
      key: row.id,
      id: row.id,
      storagePath: row.storagePath,
      publicUrl: row.publicUrl,
      isPrimary: row.isPrimary,
    }));
}

export function ProductImageEditor({
  productId,
  initialImages,
  uploadBlocked,
}: {
  productId: string;
  initialImages: EditorImageRow[];
  uploadBlocked: boolean;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [images, setImages] = useState<EditorEntry[]>(() => toEntries(initialImages));
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [result, setResult] = useState<Result>({ kind: 'idle' });

  function move(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= images.length) {
      return;
    }
    const next = [...images];
    const [entry] = next.splice(index, 1);
    if (entry) {
      next.splice(target, 0, entry);
    }
    setImages(next);
    setResult({ kind: 'idle' });
  }

  function setPrimary(index: number) {
    setImages(images.map((image, position) => ({ ...image, isPrimary: position === index })));
    setResult({ kind: 'idle' });
  }

  function remove(index: number) {
    const next = images.filter((_, position) => position !== index);
    // Keep exactly one primary: if the removed row was it, the first remaining
    // photo takes over, mirroring the server's own default.
    if (next.length > 0 && !next.some((image) => image.isPrimary)) {
      next[0] = { ...next[0]!, isPrimary: true };
    }
    setImages(next);
    setResult({ kind: 'idle' });
    setNotice(null);
  }

  async function handleFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) {
      return;
    }
    setBusy(true);
    setNotice(null);
    setResult({ kind: 'idle' });
    const added: EditorEntry[] = [];
    try {
      for (const file of Array.from(fileList)) {
        if (!file.type.startsWith('image/')) {
          setNotice(`پروندهٔ «${file.name}» تصویر نیست و نادیده گرفته شد.`);
          continue;
        }

        let blob: Blob;
        try {
          const compressed = await compressImage(file);
          blob = await (await fetch(compressed.dataUrl)).blob();
        } catch {
          setNotice(`فشرده‌سازی «${file.name}» انجام نشد؛ تصویر اضافه نشد.`);
          continue;
        }

        const body = new FormData();
        body.set('file', new File([blob], file.name, { type: blob.type || 'image/jpeg' }));

        let response: Response;
        try {
          response = await fetch('/api/admin/media', { method: 'POST', body });
        } catch {
          setNotice('ارتباط با ذخیره‌سازی محلی رسانه برقرار نشد.');
          continue;
        }

        const payload: unknown = await response.json().catch(() => null);
        const record =
          typeof payload === 'object' && payload !== null
            ? (payload as Record<string, unknown>)
            : null;
        const storagePath = record?.storagePath;
        const publicUrl = record?.publicUrl;
        if (
          !response.ok ||
          record?.ok !== true ||
          typeof storagePath !== 'string' ||
          typeof publicUrl !== 'string'
        ) {
          const message = typeof record?.message === 'string' ? record.message : null;
          setNotice(message ?? `بارگذاری «${file.name}» انجام نشد.`);
          continue;
        }

        added.push({
          key: `new:${storagePath}`,
          storagePath,
          publicUrl,
          isPrimary: false,
        });
      }

      if (added.length > 0) {
        setImages((current) => {
          const merged = [...current, ...added];
          if (!merged.some((image) => image.isPrimary)) {
            merged[0] = { ...merged[0]!, isPrimary: true };
          }
          return merged;
        });
      }
    } finally {
      setBusy(false);
      if (fileInput.current) {
        fileInput.current.value = '';
      }
    }
  }

  async function save() {
    setResult({ kind: 'busy' });
    setNotice(null);

    const payload: ProductImageSelectionEntry[] = images.map((image) =>
      image.id === undefined
        ? { storagePath: image.storagePath, publicUrl: image.publicUrl, isPrimary: image.isPrimary }
        : { id: image.id, isPrimary: image.isPrimary },
    );

    const response = await updateProductImagesAction({ productId, images: payload });
    if (!response.ok) {
      setResult({ kind: 'error', message: response.message, field: response.field });
      return;
    }

    // The server returns the gallery's ids in display order; adopt them so a
    // second save references the SAME rows instead of re-inserting them.
    const imageIds = response.data.imageIds;
    setImages((current) =>
      current.length === imageIds.length
        ? current.map((image, index) => ({
            ...image,
            id: imageIds[index] ?? image.id,
            key: imageIds[index] ?? image.key,
          }))
        : current,
    );
    setResult({ kind: 'ok', count: imageIds.length });
  }

  return (
    <div className="flex flex-col gap-3">
      {result.kind === 'ok' ? (
        <Banner tone="success" title="تصویرهای محصول ذخیره شد">
          گالری این محصول اکنون {formatCountFa(result.count)} تصویر دارد و در فروشگاه به همین ترتیب
          نمایش داده می‌شود.
        </Banner>
      ) : null}
      {result.kind === 'error' ? (
        <Banner tone="danger" title="ذخیرهٔ تصویرها انجام نشد">
          {result.message}
          {result.field ? <span className="cp-code"> [{result.field}]</span> : null}
        </Banner>
      ) : null}

      {uploadBlocked ? (
        <Banner tone="warning" title="بارگذاری فایل تصویر در این نصب فعال نیست">
          ذخیره‌سازی محلی رسانه پیکربندی نشده است، یا این یک بیلد تولیدی است. تصویر تازه‌ای اضافه
          نمی‌شود، اما ترتیب و حذف پیوست تصویرهای موجود همچنان قابل ذخیره است. انتخاب رسانهٔ تولیدی
          همچنان باز است (G-5).
        </Banner>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <label className={cn(buttonClass.neutral, uploadBlocked && 'opacity-50')}>
          <Upload aria-hidden="true" size={16} /> افزودن تصویر
          <input
            ref={fileInput}
            type="file"
            accept="image/*"
            multiple
            className="sr-only"
            disabled={busy || uploadBlocked}
            onChange={(event) => void handleFiles(event.target.files)}
          />
        </label>
        <span className="text-cp-caption text-ink-muted">
          {busy
            ? 'در حال فشرده‌سازی و بارگذاری…'
            : 'فشرده‌سازی در مرورگر: بلندترین ضلع حداکثر ۱٬۶۰۰ پیکسل، نسبت تصویر حفظ می‌شود.'}
        </span>
      </div>

      {notice ? (
        <p className="text-cp-label font-medium text-danger" role="alert">
          {notice}
        </p>
      ) : null}

      <section>
        <h3 className="text-cp-label font-semibold text-ink">
          گالری فعلی ({formatCountFa(images.length)} تصویر)
        </h3>
        {images.length === 0 ? (
          <p className="mt-2 rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
            این محصول تصویری ندارد؛ صرفه‌جویی با گالری خالی مجاز است (D-172 §1.4).
          </p>
        ) : (
          <ul className="mt-2 flex flex-col gap-2">
            {images.map((image, index) => (
              <li
                key={image.key}
                className="flex flex-wrap items-center justify-between gap-3 rounded-[--radius-cp] border border-edge p-2"
              >
                <span className="flex min-w-0 items-center gap-3">
                  {/* eslint-disable-next-line @next/next/no-img-element */}
                  <img
                    src={image.publicUrl}
                    alt={`تصویر ${formatCountFa(index + 1)}`}
                    className="h-16 w-16 rounded-[--radius-cp] border border-edge object-cover"
                  />
                  <span className="flex min-w-0 flex-col gap-1">
                    <span className="flex flex-wrap items-center gap-2 text-cp-label">
                      <ImageIcon aria-hidden="true" size={14} />
                      <span className="truncate cp-code text-cp-caption">{image.storagePath}</span>
                      {image.isPrimary ? (
                        <Badge tone="primary">
                          <Star aria-hidden="true" size={12} /> تصویر اصلی
                        </Badge>
                      ) : null}
                      {image.id === undefined ? (
                        <Badge tone="warning">ذخیره‌نشده</Badge>
                      ) : null}
                    </span>
                    <span className="text-cp-caption text-ink-muted">
                      ترتیب نمایش: {formatCountFa(index + 1)}
                      {index === 0 ? ' (اول گالری)' : ''}
                    </span>
                  </span>
                </span>
                <span className="flex flex-wrap items-center gap-2">
                  <button
                    type="button"
                    className={buttonClass.neutral}
                    aria-label={`انتقال تصویر ${formatCountFa(index + 1)} به بالا`}
                    disabled={index === 0}
                    onClick={() => move(index, -1)}
                  >
                    <ArrowUp aria-hidden="true" size={14} />
                  </button>
                  <button
                    type="button"
                    className={buttonClass.neutral}
                    aria-label={`انتقال تصویر ${formatCountFa(index + 1)} به پایین`}
                    disabled={index === images.length - 1}
                    onClick={() => move(index, 1)}
                  >
                    <ArrowDown aria-hidden="true" size={14} />
                  </button>
                  <button
                    type="button"
                    className={cn(buttonClass.neutral, image.isPrimary && 'border-primary')}
                    aria-pressed={image.isPrimary}
                    onClick={() => setPrimary(index)}
                  >
                    تصویر اصلی
                  </button>
                  <button
                    type="button"
                    className={buttonClass.neutral}
                    aria-label={`حذف پیوست تصویر ${formatCountFa(index + 1)}`}
                    onClick={() => remove(index)}
                  >
                    <Trash2 aria-hidden="true" size={14} /> حذف پیوست
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <p className="text-cp-caption text-ink-muted">
        حذف پیوست، فایل ذخیره‌شده را پاک نمی‌کند: کلیدها بر پایهٔ هش محتوا هستند و ممکن است میان
        محصول‌ها مشترک باشند. پاک‌سازی فایل‌های بی‌استفاده سیاست جداگانهٔ خود را دارد.
      </p>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={buttonClass.primary}
          onClick={() => void save()}
          disabled={result.kind === 'busy' || busy}
        >
          {result.kind === 'busy' ? 'در حال ذخیره…' : 'ذخیرهٔ تصویرها'}
        </button>
        <span className="text-cp-caption text-ink-muted">
          فقط پیوست تصویرها تغییر می‌کند؛ مشخصات، قیمت، گونه‌ها و موجودی دست‌نخورده می‌مانند.
        </span>
      </div>
    </div>
  );
}
