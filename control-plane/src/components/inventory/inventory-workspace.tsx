'use client';

import { useMemo, useState } from 'react';

import {
  EMPTY_INVENTORY_FILTERS,
  InventoryFilters,
  applyInventoryFilters,
  parsePriceRange,
  type InventoryFilterState,
} from '@/components/inventory/inventory-filters';
import { SkuTable } from '@/components/inventory/sku-table';
import { SyncOverrideGate } from '@/components/inventory/sync-override-gate';
import { Card } from '@/components/ui/card';
import { TechnicalOnly } from '@/components/ui/view-gate';
import type { InventorySnapshot } from '@/types/inventory';

/**
 * Client coordinator for the inventory screen.
 *
 * The server renders the snapshot; this component owns only PRESENTATION state
 * (which filters are active, which row is expanded). It never mutates a SKU,
 * never calls a network endpoint, and every write path stays behind the
 * disabled gate. Keeping this boundary means live wiring replaces the data
 * source, not the interaction model.
 */
export function InventoryWorkspace({ snapshot }: { snapshot: InventorySnapshot }) {
  const [filters, setFilters] = useState<InventoryFilterState>(EMPTY_INVENTORY_FILTERS);

  const price = useMemo(() => parsePriceRange(filters), [filters]);
  const rows = useMemo(
    () => applyInventoryFilters(snapshot.items, filters),
    [snapshot.items, filters],
  );

  const emptyMessage = price.invalid
    ? 'بازهٔ قیمت نامعتبر است؛ تا اصلاح آن هیچ SKUی نمایش داده نمی‌شود.'
    : 'هیچ SKUی با این فیلترها وجود ندارد — و فهرست خالی هرگز به معنای سلامت موجودی نیست.';

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <InventoryFilters
          filters={filters}
          onChange={setFilters}
          shown={rows.length}
          total={snapshot.items.length}
        />
      </Card>

      <Card>
        <SkuTable items={rows} emptyMessage={emptyMessage} />
      </Card>

      {/* Owner-token / canonical write-path gate internals are console assets. */}
      <TechnicalOnly surface="inventory-write-gate">
        <Card>
          <SyncOverrideGate actions={snapshot.actions} gate={snapshot.gate} />
        </Card>
      </TechnicalOnly>
    </div>
  );
}
