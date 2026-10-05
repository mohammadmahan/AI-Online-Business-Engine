'use client';

import { useMemo, useState } from 'react';

import {
  EMPTY_ORDER_FILTERS,
  OrderFilters,
  applyOrderFilters,
  parsePlacedRange,
  type OrderFilterState,
} from '@/components/commerce/orders-filters';
import { OrdersTable } from '@/components/commerce/orders-table';
import { FulfillmentOverrideGate } from '@/components/commerce/fulfillment-override-gate';
import { Card, CardHeader } from '@/components/ui/card';
import type { CommerceSnapshot } from '@/types/commerce';

/**
 * Client coordinator for the orders screen.
 *
 * The server renders the snapshot; this component owns only PRESENTATION state
 * (which filters are active, which drawer is open). It never mutates an order,
 * never calls a network endpoint, and every write path stays behind the
 * disabled gate. Keeping this boundary means live wiring replaces the data
 * source, not the interaction model.
 */
export function OrdersWorkspace({ snapshot }: { snapshot: CommerceSnapshot }) {
  const [filters, setFilters] = useState<OrderFilterState>(EMPTY_ORDER_FILTERS);

  const range = useMemo(() => parsePlacedRange(filters), [filters]);
  const rows = useMemo(() => applyOrderFilters(snapshot.orders, filters), [snapshot.orders, filters]);

  const emptyMessage = range.invalid
    ? 'بازه‌ی تاریخ نامعتبر است؛ تا اصلاح آن هیچ سفارشی نمایش داده نمی‌شود.'
    : 'هیچ سفارشی با این فیلترها وجود ندارد — و فهرست خالی هرگز به معنای درآمد سالم نیست.';

  return (
    <div className="flex flex-col gap-4">
      <Card>
        <OrderFilters
          filters={filters}
          onChange={setFilters}
          shown={rows.length}
          total={snapshot.orders.length}
        />
      </Card>

      <Card>
        <CardHeader
          title="سفارش‌ها"
          description="هر ردیف یک سفارش کاننیکال است: مبلغ عدد صحیح تومان (D-010)، چرخه‌ی D-081 در ستون تأمین، و گزارش پرداخت کاملاً ماسک‌شده در جزئیات (D-114/D-124)."
        />
        <OrdersTable orders={rows} emptyMessage={emptyMessage} />
      </Card>

      <Card>
        <FulfillmentOverrideGate actions={snapshot.actions} gate={snapshot.gate} />
      </Card>
    </div>
  );
}
