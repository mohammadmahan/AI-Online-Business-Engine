ALTER TABLE "commerce"."orders" ADD COLUMN "idempotency_key" uuid;--> statement-breakpoint
CREATE UNIQUE INDEX "orders_idempotency_key_unique" ON "commerce"."orders" USING btree ("idempotency_key");