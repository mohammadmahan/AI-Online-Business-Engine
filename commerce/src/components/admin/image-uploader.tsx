'use client';

import { ArrowDown, ArrowUp, Image as ImageIcon, Star, Trash2, Upload } from 'lucide-react';
import { useRef, useState } from 'react';

import type { ProductImagePayload } from '@/contracts/catalog';
import { formatCountFa } from '@/lib/format';
import { formatByteSize, compressImage } from '@/lib/image';
import { cn } from '@/lib/utils';
import { Banner, Badge, Field, buttonClass, inputClass } from '@/components/ui/primitives';

/**
 * D-172 §2.1 — multi-image uploader.
 *
 * Two halves, and the difference between them is the honest part:
 *
 *  1. **Selection** (works today): files are compressed in the browser —
 *     longest edge capped, aspect ratio preserved, JPEG re-encode — and shown as
 *     previews the merchant can order and pick a primary from. Nothing leaves
 *     the machine.
 *  2. **Storage** (blocked): the bytes cannot be written anywhere because
 *     **G-5 (media storage) is still OPEN**. The submit path therefore REFUSES
 *     while compressed files are pending, instead of inventing a provider or
 *     writing gallery rows that point at images which do not exist.
 *
 * A merchant who already hosts images elsewhere can attach them by path + URL;
 * that path persists today and goes through the normal §1.4 contract.
 */

export interface CompressedPreview {
  id: string;
  fileName: string;
  dataUrl: string;
  width: number;
  height: number;
  bytes: number;
}

export function ImageUploader({
  uploadBlocked,
  images,
  imagesChange,
  pending,
  pendingChange,
}: {
  uploadBlocked: boolean;
  images: ProductImagePayload[];
  imagesChange: (images: ProductImagePayload[]) => void;
  pending: CompressedPreview[];
  pendingChange: (pending: CompressedPreview[]) => void;
}) {
  const fileInput = useRef<HTMLInputElement>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [manualOpen, setManualOpen] = useState(false);
  const [manualPath, setManualPath] = useState('');
  const [manualUrl, setManualUrl] = useState('');

  async function handleFiles(fileList: FileList | null) {
    if (!fileList || fileList.length === 0) {
      return;
    }
    setBusy(true);
    setNotice(null);
    try {
      const compressed: CompressedPreview[] = [];
      for (const file of Array.from(fileList)) {
        if (!file.type.startsWith('image/')) {
          setNotice(`پروندهٔ «${file.name}» تصویر نیست و نادیده گرفته شد.`);
          continue;
        }
        const result = await compressImage(file);
        compressed.push({
          id: `${file.name}-${compressed.length}-${Date.now()}`,
          fileName: file.name,
          ...result,
        });
      }
      pendingChange([...pending, ...compressed]);
    } catch {
      // Fail closed: a browser that cannot decode the image gets a message, not
      // a half-added gallery entry.
      setNotice('فشرده‌سازی تصویر در این مرورگر انجام نشد؛ تصویر اضافه نشد.');
    } finally {
      setBusy(false);
      if (fileInput.current) {
        fileInput.current.value = '';
      }
    }
  }

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
    imagesChange(next.map((image, order) => ({ ...image, displayOrder: order })));
  }

  function setPrimary(index: number) {
    imagesChange(images.map((image, order) => ({ ...image, isPrimary: order === index })));
  }

  function addManual() {
    if (manualPath.trim().length === 0 || manualUrl.trim().length === 0) {
      setNotice('برای افزودن تصویر بیرونی، مسیر ذخیره‌سازی و نشانی هر دو لازم است.');
      return;
    }
    imagesChange([
      ...images,
      {
        storagePath: manualPath.trim(),
        publicUrl: manualUrl.trim(),
        displayOrder: images.length,
        isPrimary: images.length === 0,
      },
    ]);
    setManualPath('');
    setManualUrl('');
    setNotice(null);
  }

  return (
    <div className="flex flex-col gap-3">
      {uploadBlocked ? (
        <Banner tone="warning" title="بارگذاری فایل تصویر فعلاً غیرفعال است (تصمیم باز G-5)">
          ذخیره‌سازی رسانهٔ فروشگاه هنوز توسط مالک تعیین نشده است. تصویرها فقط در همین مرورگر
          فشرده و پیش‌نمایش می‌شوند؛ تا آن زمان محصول بدون تصویر ثبت می‌شود یا می‌توانید تصویرِ
          میزبانی‌شدهٔ خودتان را با «نشانی بیرونی» پیوست کنید.
        </Banner>
      ) : null}

      <div className="flex flex-wrap items-center gap-3">
        <label className={buttonClass.neutral} htmlFor="image-files">
          <Upload aria-hidden="true" size={16} /> انتخاب تصویر
        </label>
        <input
          ref={fileInput}
          id="image-files"
          type="file"
          accept="image/*"
          multiple
          className="sr-only"
          onChange={(event) => void handleFiles(event.target.files)}
        />
        <span className="text-cp-caption text-ink-muted">
          {busy
            ? 'در حال فشرده‌سازی…'
            : `فشرده‌سازی در مرورگر: بلندترین ضلع حداکثر ۱٬۶۰۰ پیکسل، نسبت تصویر حفظ می‌شود.`}
        </span>
      </div>

      {notice ? (
        <p className="text-cp-label font-medium text-danger" role="alert">
          {notice}
        </p>
      ) : null}

      {pending.length > 0 ? (
        <section className="rounded-[--radius-cp] border border-warning p-3">
          <h3 className="text-cp-label font-semibold text-ink">
            پیش‌نمایش فشرده‌شده ({formatCountFa(pending.length)} تصویر — ذخیره نشده)
          </h3>
          <ul className="mt-2 flex flex-wrap gap-3">
            {pending.map((preview) => (
              <li key={preview.id} className="w-40">
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img
                  src={preview.dataUrl}
                  alt={`پیش‌نمایش ${preview.fileName}`}
                  className="h-28 w-40 rounded-[--radius-cp] border border-edge object-cover"
                />
                <p className="mt-1 truncate text-cp-caption text-ink-muted">{preview.fileName}</p>
                <p className="text-cp-caption text-ink-muted">
                  {formatCountFa(preview.width)}×{formatCountFa(preview.height)} ·{' '}
                  {formatByteSize(preview.bytes)}
                </p>
                <button
                  type="button"
                  className={buttonClass.neutral}
                  onClick={() => pendingChange(pending.filter((entry) => entry.id !== preview.id))}
                >
                  <Trash2 aria-hidden="true" size={14} /> حذف
                </button>
              </li>
            ))}
          </ul>
        </section>
      ) : null}

      <section>
        <h3 className="text-cp-label font-semibold text-ink">
          گالری محصول ({formatCountFa(images.length)} تصویر پیوست‌شده)
        </h3>
        {images.length === 0 ? (
          <p className="mt-2 rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-3 text-cp-label text-ink-muted">
            تصویری پیوست نشده است؛ تصویر برای این مرحله اختیاری است (D-172 §1.4).
          </p>
        ) : (
          <ul className="mt-2 flex flex-col gap-2">
            {images.map((image, index) => (
              <li
                key={`${image.storagePath}-${index}`}
                className="flex flex-wrap items-center justify-between gap-2 rounded-[--radius-cp] border border-edge p-2"
              >
                <span className="flex items-center gap-2 text-cp-label">
                  <ImageIcon aria-hidden="true" size={16} />
                  <span className="cp-code">{image.storagePath}</span>
                  {image.isPrimary ? (
                    <Badge tone="primary">
                      <Star aria-hidden="true" size={12} /> تصویر اصلی
                    </Badge>
                  ) : null}
                </span>
                <span className="flex items-center gap-2">
                  <button
                    type="button"
                    className={buttonClass.neutral}
                    aria-label={`انتقال تصویر ${formatCountFa(index + 1)} به بالا`}
                    onClick={() => move(index, -1)}
                  >
                    <ArrowUp aria-hidden="true" size={14} />
                  </button>
                  <button
                    type="button"
                    className={buttonClass.neutral}
                    aria-label={`انتقال تصویر ${formatCountFa(index + 1)} به پایین`}
                    onClick={() => move(index, 1)}
                  >
                    <ArrowDown aria-hidden="true" size={14} />
                  </button>
                  <button
                    type="button"
                    className={cn(buttonClass.neutral, image.isPrimary && 'border-primary')}
                    aria-pressed={image.isPrimary ?? false}
                    onClick={() => setPrimary(index)}
                  >
                    تصویر اصلی
                  </button>
                  <button
                    type="button"
                    className={buttonClass.neutral}
                    aria-label={`حذف تصویر ${formatCountFa(index + 1)}`}
                    onClick={() =>
                      imagesChange(
                        images
                          .filter((_, position) => position !== index)
                          .map((entry, order) => ({ ...entry, displayOrder: order })),
                      )
                    }
                  >
                    <Trash2 aria-hidden="true" size={14} />
                  </button>
                </span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <div>
        <button
          type="button"
          className={buttonClass.neutral}
          aria-expanded={manualOpen}
          onClick={() => setManualOpen(!manualOpen)}
        >
          افزودن تصویر با نشانی بیرونی
        </button>
        {manualOpen ? (
          <div className="mt-2 flex flex-wrap items-end gap-2">
            <Field label="مسیر ذخیره‌سازی" htmlFor="manual-path" hint="مثال: products/manto/1.jpg">
              <input
                id="manual-path"
                className={cn(inputClass, 'cp-code')}
                value={manualPath}
                onChange={(event) => setManualPath(event.target.value)}
              />
            </Field>
            <Field label="نشانی عمومی تصویر" htmlFor="manual-url">
              <input
                id="manual-url"
                className={cn(inputClass, 'cp-code')}
                dir="ltr"
                value={manualUrl}
                onChange={(event) => setManualUrl(event.target.value)}
                placeholder="https://…"
              />
            </Field>
            <button type="button" className={buttonClass.primary} onClick={addManual}>
              پیوست
            </button>
          </div>
        ) : null}
      </div>
    </div>
  );
}
