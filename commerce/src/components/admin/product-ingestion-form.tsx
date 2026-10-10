'use client';

import { useState } from 'react';

import type { ProductCreatePayload, ProductImagePayload, VariantPayload } from '@/contracts/catalog';
import { formatCountFa } from '@/lib/format';
import { createProductAction } from '@/server/actions/products';
import { Banner, Card, CardHeader, Field, buttonClass, inputClass } from '@/components/ui/primitives';
import type { CompressedPreview } from '@/components/admin/image-uploader';
import { ImageUploader } from '@/components/admin/image-uploader';
import { VariantMatrixGenerator } from '@/components/admin/variant-matrix-generator';

/**
 * D-172 §2.1 — smart product ingestion.
 *
 * One form, three inputs the roadmap asks for: the merchant's own fields, the
 * colour × size matrix, and the media. It submits through ONE server action, and
 * it renders the server's refusal verbatim — including the fail-closed case
 * where the canonical database is not configured and the case where image bytes
 * cannot be stored yet (G-5). No optimistic success, no fabricated product id.
 */

export interface CategoryOption {
  id: string;
  name: string;
}

export function ProductIngestionForm({
  categories,
  mediaUploadBlocked,
}: {
  categories: CategoryOption[];
  mediaUploadBlocked: boolean;
}) {
  const [title, setTitle] = useState('');
  const [slug, setSlug] = useState('');
  const [categoryId, setCategoryId] = useState(categories[0]?.id ?? '');
  const [basePrice, setBasePrice] = useState<number | ''>('');
  const [discountPrice, setDiscountPrice] = useState<number | ''>('');
  const [fabricType, setFabricType] = useState('');
  const [season, setSeason] = useState('');
  const [careInstructions, setCareInstructions] = useState('');
  const [descriptionRaw, setDescriptionRaw] = useState('');
  const [status, setStatus] = useState<'DRAFT' | 'PUBLISHED'>('DRAFT');
  const [rows, setRows] = useState<VariantPayload[]>([]);
  const [images, setImages] = useState<ProductImagePayload[]>([]);
  const [pending, setPending] = useState<CompressedPreview[]>([]);
  const [result, setResult] = useState<
    | { kind: 'idle' }
    | { kind: 'busy' }
    | { kind: 'ok'; productId: string; variants: number }
    | { kind: 'error'; message: string; field?: string }
  >({ kind: 'idle' });

  function suggestSlug() {
    const candidate = title
      .trim()
      .toLowerCase()
      .replace(/\s+/g, '-')
      .replace(/[^a-z0-9-]/g, '')
      .replace(/-+/g, '-')
      .replace(/^-|-$/g, '');
    if (candidate.length === 0) {
      setResult({
        kind: 'error',
        message: 'برای عنوان فارسی، نشانی را دستی وارد کنید (حروف کوچک لاتین، عدد و خط تیره).',
        field: 'slug',
      });
      return;
    }
    setSlug(candidate);
    setResult({ kind: 'idle' });
  }

  async function submit() {
    setResult({ kind: 'busy' });
    const payload: ProductCreatePayload = {
      categoryId,
      title,
      slug,
      basePrice: basePrice === '' ? Number.NaN : Number(basePrice),
      discountPrice: discountPrice === '' ? null : Number(discountPrice),
      descriptionRaw,
      // The rich text is generated server-side from the raw text until the AI
      // copy engine (Phase 4) provides a merchant-approved version.
      descriptionHtml: '',
      fabricType,
      season,
      careInstructions: careInstructions === '' ? null : careInstructions,
      status,
      variants: rows,
      images,
    };

    const response = await createProductAction({ product: payload, pendingUploads: pending.length });
    if (response.ok) {
      setResult({
        kind: 'ok',
        productId: response.data.productId,
        variants: response.data.variantIds.length,
      });
      setRows([]);
      setImages([]);
      setPending([]);
      return;
    }
    setResult({ kind: 'error', message: response.message, field: response.field });
  }

  const skuPrefix = (slug || 'SKU').toUpperCase().replace(/[^A-Z0-9]+/g, '-');

  return (
    <div className="flex flex-col gap-4">
      {result.kind === 'ok' ? (
        <Banner tone="success" title="محصول ثبت شد">
          شناسهٔ محصول: <span className="cp-code">{result.productId}</span> —{' '}
          {formatCountFa(result.variants)} ترکیب رنگ و سایز ساخته شد و در فهرست موجودی قابل ویرایش
          است.
        </Banner>
      ) : null}
      {result.kind === 'error' ? (
        <Banner tone="danger" title="ثبت محصول انجام نشد">
          {result.message}
          {result.field ? (
            <span className="cp-code"> [{result.field}]</span>
          ) : null}
        </Banner>
      ) : null}

      <Card>
        <CardHeader
          title="اطلاعات محصول"
          description="فیلدهای ستاره‌دار الزامی‌اند. قیمت‌ها به تومان و عدد صحیح وارد می‌شوند."
        />
        <div className="grid gap-4 md:grid-cols-2">
          <Field label="عنوان محصول" htmlFor="title" required>
            <input
              id="title"
              className={inputClass}
              value={title}
              onChange={(event) => setTitle(event.target.value)}
              placeholder="مثال: مانتو کتی لنین بهاره"
            />
          </Field>
          <Field label="نشانی محصول (slug)" htmlFor="slug" required hint="حروف کوچک لاتین، عدد و خط تیره">
            <span className="flex gap-2">
              <input
                id="slug"
                className={inputClass}
                dir="ltr"
                value={slug}
                onChange={(event) => setSlug(event.target.value)}
                placeholder="manto-keti-lenin"
              />
              <button type="button" className={buttonClass.neutral} onClick={suggestSlug}>
                پیشنهاد
              </button>
            </span>
          </Field>
          <Field label="دسته" htmlFor="category" required>
            <select
              id="category"
              className={inputClass}
              value={categoryId}
              onChange={(event) => setCategoryId(event.target.value)}
            >
              {categories.length === 0 ? <option value="">دسته‌ای ثبت نشده است</option> : null}
              {categories.map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </select>
          </Field>
          <Field label="وضعیت انتشار" htmlFor="status">
            <select
              id="status"
              className={inputClass}
              value={status}
              onChange={(event) => setStatus(event.target.value === 'PUBLISHED' ? 'PUBLISHED' : 'DRAFT')}
            >
              <option value="DRAFT">پیش‌نویس (DRAFT)</option>
              <option value="PUBLISHED">منتشرشده (PUBLISHED)</option>
            </select>
          </Field>
          <Field label="قیمت پایه (تومان)" htmlFor="base-price" required>
            <input
              id="base-price"
              type="number"
              min={0}
              className={inputClass}
              value={basePrice}
              onChange={(event) => setBasePrice(event.target.value === '' ? '' : Number(event.target.value))}
            />
          </Field>
          <Field label="قیمت تخفیف‌دار (تومان)" htmlFor="discount-price" hint="اختیاری">
            <input
              id="discount-price"
              type="number"
              min={0}
              className={inputClass}
              value={discountPrice}
              onChange={(event) =>
                setDiscountPrice(event.target.value === '' ? '' : Number(event.target.value))
              }
            />
          </Field>
          <Field label="نوع پارچه" htmlFor="fabric" required>
            <input
              id="fabric"
              className={inputClass}
              value={fabricType}
              onChange={(event) => setFabricType(event.target.value)}
              placeholder="مثال: لنین، کرپ، مازراتی"
            />
          </Field>
          <Field label="فصل" htmlFor="season" required>
            <input
              id="season"
              className={inputClass}
              value={season}
              onChange={(event) => setSeason(event.target.value)}
              placeholder="مثال: بهاره، تابستانه"
            />
          </Field>
          <Field label="توضیح خام (ورودی موتور هوش مصنوعی)" htmlFor="raw" required>
            <textarea
              id="raw"
              rows={4}
              className={inputClass}
              value={descriptionRaw}
              onChange={(event) => setDescriptionRaw(event.target.value)}
              placeholder="توضیح خودتان را بنویسید یا متن یادداشت صوتی را اینجا بگذارید."
            />
          </Field>
          <Field label="راهنمای نگهداری" htmlFor="care" hint="اختیاری">
            <input
              id="care"
              className={inputClass}
              value={careInstructions}
              onChange={(event) => setCareInstructions(event.target.value)}
            />
          </Field>
        </div>
      </Card>

      <Card>
        <CardHeader
          title="ماتریس رنگ و سایز"
          description="رنگ‌ها و سایزها را انتخاب کنید؛ سطرها ساخته و قابل ویرایش می‌شوند."
        />
        <VariantMatrixGenerator skuPrefix={skuPrefix} rows={rows} onRowsChange={setRows} />
      </Card>

      <Card>
        <CardHeader title="تصویرهای محصول" description="ترتیب و تصویر اصلی قابل تعیین است." />
        <ImageUploader
          uploadBlocked={mediaUploadBlocked}
          images={images}
          imagesChange={setImages}
          pending={pending}
          pendingChange={setPending}
        />
      </Card>

      <div className="flex flex-wrap items-center gap-3">
        <button
          type="button"
          className={buttonClass.primary}
          onClick={() => void submit()}
          disabled={result.kind === 'busy'}
        >
          {result.kind === 'busy' ? 'در حال ثبت…' : 'ثبت محصول'}
        </button>
        <span className="text-cp-caption text-ink-muted">
          {formatCountFa(rows.length)} ترکیب آمادهٔ ثبت · {formatCountFa(images.length)} تصویر پیوست
        </span>
      </div>
    </div>
  );
}
