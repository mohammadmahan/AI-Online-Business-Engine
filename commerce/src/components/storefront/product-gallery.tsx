'use client';

import { Search, ZoomIn, ZoomOut } from 'lucide-react';
import { useState } from 'react';

import type { StorefrontImageRef } from '@/contracts/storefront';
import { buttonClass } from '@/components/ui/primitives';
import { cn } from '@/lib/utils';

/**
 * D-172 §3.3 — the PDP gallery.
 *
 * Three parts of the roadmap live here: a swipeable strip (the thumbnail rail
 * scrolls horizontally and snaps, so a phone swipes it), a client-side viewer
 * with zoom (no image service, no request: the browser scales what it already
 * has), and colour awareness — the parent passes only the photos that belong to
 * the selected colour, and the `key` it sets on this component resets the viewer
 * when the colour changes so a stale index can never point past the new list.
 *
 * The rendered source is whatever URL the catalog stored; nothing is proxied or
 * resized here, because the media host is still an open owner decision
 * (D-172 G-5) and inventing a transform pipeline would imply one.
 */
export function ProductGallery({
  images,
  title,
  colorLabel,
}: {
  images: StorefrontImageRef[];
  title: string;
  colorLabel: string | null;
}) {
  const [index, setIndex] = useState(0);
  const [zoom, setZoom] = useState(false);
  const [origin, setOrigin] = useState({ x: 50, y: 50 });

  const current = images[index < images.length ? index : 0];

  if (!current) {
    return (
      <div className="flex aspect-square w-full items-center justify-center rounded-[--radius-cp] border border-dashed border-edge-strong bg-surface-muted p-4 text-center text-cp-label text-ink-muted">
        برای این محصول هنوز تصویری ثبت نشده است.
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-3">
      <div className="relative overflow-hidden rounded-[--radius-cp] border border-edge bg-surface-muted">
        {/* eslint-disable-next-line @next/next/no-img-element -- the media host is an open owner decision (D-172 G-5); next/image would need a remotePatterns entry for a host that does not exist yet. */}
        <img
          src={current.url}
          alt={
            colorLabel
              ? `${title} — رنگ ${colorLabel} — تصویر ${index + 1}`
              : `${title} — تصویر ${index + 1}`
          }
          className={cn(
            'aspect-square w-full object-cover transition-transform duration-200',
            zoom && 'scale-[2]',
          )}
          style={zoom ? { transformOrigin: `${origin.x}% ${origin.y}%` } : undefined}
          onMouseMove={(event) => {
            const box = event.currentTarget.getBoundingClientRect();
            setOrigin({
              x: ((event.clientX - box.left) / box.width) * 100,
              y: ((event.clientY - box.top) / box.height) * 100,
            });
          }}
        />
      </div>

      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1 text-cp-caption text-ink-muted">
          <Search aria-hidden="true" size={14} />
          تصویر <span className="cp-code">{index + 1}</span> از{' '}
          <span className="cp-code">{images.length}</span>
        </p>
        <button
          type="button"
          className={buttonClass.neutral}
          aria-pressed={zoom}
          onClick={() => setZoom((current) => !current)}
        >
          {zoom ? (
            <ZoomOut aria-hidden="true" size={16} />
          ) : (
            <ZoomIn aria-hidden="true" size={16} />
          )}
          {zoom ? 'بستن بزرگ‌نمایی' : 'بزرگ‌نمایی'}
        </button>
      </div>

      {images.length > 1 ? (
        <ul className="grid snap-x snap-mandatory grid-flow-col auto-cols-[5rem] gap-2 overflow-x-auto pb-2">
          {images.map((image, imageIndex) => (
            <li key={`${image.url}-${imageIndex}`} className="snap-start">
              <button
                type="button"
                className={cn(
                  'cp-target block w-20 overflow-hidden rounded-[--radius-cp] border',
                  imageIndex === index ? 'border-primary' : 'border-edge',
                )}
                aria-label={`نمایش تصویر ${imageIndex + 1}`}
                aria-current={imageIndex === index}
                onClick={() => {
                  setIndex(imageIndex);
                  setZoom(false);
                }}
              >
                {/* eslint-disable-next-line @next/next/no-img-element -- see above. */}
                <img
                  src={image.url}
                  alt=""
                  loading="lazy"
                  className="aspect-square w-full object-cover"
                />
              </button>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
