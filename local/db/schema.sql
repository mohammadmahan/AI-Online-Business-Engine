-- Canonical local database — initial schema (PostgreSQL)  [D-055 Approved]
-- Implements the approved logical model (DATA_MODEL §13) under:
--   D-014/D-015/D-017 identifiers · D-018 variant axes · D-021 minimums
--   D-022/D-023 lifecycle/publication · D-024/D-025 prices · D-026
--   provenance · D-027 events · D-029/D-031/D-032 vocabulary ·
--   D-046 mapping registry
--
-- Deliberately implementation-deferred: WooCommerce-side structures,
-- inventory (D-016.I open), audit-log system (provenance ≠ audit log),
-- SEO slug normalization (D-016.M open), exact Woo field-level mapping
-- (implementation-time verification points).

-- ================================================================== --
-- 0. Schema separation (D-055: logically separate stores, one local
--    physical instance; staging/production may split instances later
--    without schema change)
-- ================================================================== --

CREATE SCHEMA IF NOT EXISTS seed;
CREATE SCHEMA IF NOT EXISTS canonical;
CREATE SCHEMA IF NOT EXISTS registry;
CREATE SCHEMA IF NOT EXISTS events;
CREATE SCHEMA IF NOT EXISTS provenance;

-- ================================================================== --
-- 1. Controlled vocabulary (Registry v1 — D-029/D-031/D-032)
--    Human-owned (D-019): normal application flows never mutate these
--    tables; changes arrive only through owner decisions via the seed
--    script. No alias tables exist — the alias registry stays empty.
--    O/I/L-safe codes are enforced by CHECK (D-014 rule 7 / D-030).
-- ================================================================== --

CREATE TABLE IF NOT EXISTS seed.size_family (
    family_key   text PRIMARY KEY,
    label_fa     text NOT NULL UNIQUE,
    sort_order   int  NOT NULL
);

CREATE TABLE IF NOT EXISTS seed.size_term (
    family_key   text NOT NULL REFERENCES seed.size_family(family_key),
    display_fa   text NOT NULL,
    code         text NOT NULL
                 -- D-014 rule 7 / D-030 strict charset, plus the ONE
                 -- explicit owner-sanctioned exception: LRG (D-057,
                 -- register row 24). Any further exception requires its
                 -- own decision record added here — never silently.
                 CHECK (code ~ '^[A-Z0-9]+$'
                        AND ((code NOT LIKE '%O%' AND code NOT LIKE '%I%'
                              AND code NOT LIKE '%L%')
                             OR code = 'LRG')),
    PRIMARY KEY (family_key, display_fa),
    UNIQUE (family_key, code)
);

CREATE TABLE IF NOT EXISTS seed.color_term (
    display_fa   text PRIMARY KEY,
    code         text NOT NULL UNIQUE
                 CHECK (code ~ '^[A-Z0-9]+$'
                        AND code NOT LIKE '%O%' AND code NOT LIKE '%I%'
                        AND code NOT LIKE '%L%')
);

CREATE TABLE IF NOT EXISTS seed.category_term (
    primary_fa   text NOT NULL,
    leaf_fa      text NOT NULL,
    PRIMARY KEY (primary_fa, leaf_fa),
    CHECK (primary_fa IN ('پوشاک زنانه', 'پوشاک مردانه'))
);

-- ================================================================== --
-- 2. Provenance (D-026) — append-only; never overwritten
-- ================================================================== --

CREATE TABLE IF NOT EXISTS provenance.provenance_record (
    provenance_id    bigserial PRIMARY KEY,
    source_type      text NOT NULL CHECK (source_type IN (
        'HUMAN_ENTERED', 'SYSTEM_GENERATED', 'AI_GENERATED',
        'IMPORTED', 'EXTERNAL_SYNC')),
    actor            text NOT NULL,
    recorded_at      timestamptz NOT NULL DEFAULT now(),
    review_state     text NOT NULL DEFAULT 'PENDING' CHECK
        (review_state IN ('PENDING', 'HUMAN_REVIEWED', 'HUMAN_VERIFIED')),
    source_reference text,
    original_value   text,
    notes            text
);

-- Append-only enforcement: core fields immutable; only review_state
-- may advance (origin is never erased — D-026).
CREATE OR REPLACE FUNCTION provenance.reject_mutation() RETURNS trigger AS $$
BEGIN
    IF NEW.source_type <> OLD.source_type
       OR NEW.actor <> OLD.actor
       OR NEW.recorded_at <> OLD.recorded_at
       OR NEW.source_reference IS DISTINCT FROM OLD.source_reference
       OR NEW.original_value  IS DISTINCT FROM OLD.original_value
       OR NEW.notes           IS DISTINCT FROM OLD.notes THEN
        RAISE EXCEPTION
            'provenance is append-only (D-026): core fields are immutable';
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS provenance_append_only ON provenance.provenance_record;
CREATE TRIGGER provenance_append_only
    BEFORE UPDATE ON provenance.provenance_record
    FOR EACH ROW EXECUTE FUNCTION provenance.reject_mutation();

-- Per-value provenance linkage (which provenance record backs which
-- field of which row). One active linkage per (table, row, field):
-- a superseding record replaces the linkage; old provenance rows are
-- never deleted (entries supersede rather than overwrite — D-026).
CREATE TABLE IF NOT EXISTS provenance.value_provenance (
    table_name     text NOT NULL,
    row_pk         text NOT NULL,
    field_name     text NOT NULL,
    provenance_id  bigint NOT NULL
        REFERENCES provenance.provenance_record(provenance_id),
    PRIMARY KEY (table_name, row_pk, field_name)
);

-- ================================================================== --
-- 3. Canonical data — products and variants
--    Identity separation (D-015/D-017):
--      product_id: business key, CHECK-pattern, NOT a surrogate
--      variant_id: UUIDv4 — the variant's identity
--      sku:        business/inventory identifier, UNIQUE but never
--                  the identity or a lookup key
-- ================================================================== --

CREATE TABLE IF NOT EXISTS canonical.product (
    product_id         text PRIMARY KEY
                       CHECK (product_id ~ '^P[0-9]{5}$'),
    name               text NOT NULL,
    name_en            text,
    primary_category   text NOT NULL,
    leaf_category      text NOT NULL,
    brand              text, material text, pattern text, style text,
    season             text, usage_ text, collar text, sleeve text,
    garment_length     text, closure text, fit text,
    description        text,
    short_description  text,
    seo_title          text,
    seo_description    text,
    seo_slug           text,
    list_price         bigint CHECK (list_price IS NULL OR list_price > 0),
    product_sale       bigint CHECK (product_sale IS NULL OR product_sale > 0),
    product_sale_until date,
    media_refs         text NOT NULL DEFAULT '',
    status             text NOT NULL
                       CHECK (status IN ('draft', 'active', 'archived')),
    publication_status text NOT NULL
                       CHECK (publication_status IN
                           ('unpublished', 'in_review', 'published',
                            'withdrawn')),
    created_date       date NOT NULL,
    updated_at         timestamptz NOT NULL DEFAULT now(),
    -- D-031/D-033: the leaf must belong to the chosen primary
    -- (primary-scoped validation; exact pair, no fuzzy matching).
    FOREIGN KEY (primary_category, leaf_category)
        REFERENCES seed.category_term(primary_fa, leaf_fa),
    -- D-025: a product-level sale requires a base and must be < base.
    CHECK (product_sale IS NULL OR list_price IS NOT NULL),
    CHECK (product_sale IS NULL OR list_price IS NULL
           OR product_sale < list_price)
);

-- D-021 publication minimum (enforced structurally): published ⇒ name,
-- resolvable price, ≥1 media reference, and — for products without a
-- list price — at least one priced variant.
-- Idempotent: PostgreSQL has no ADD CONSTRAINT IF NOT EXISTS, so the
-- guard lives in a DO block (re-apply = silent no-op, verified by the
-- live migration test).
DO $$ BEGIN
    ALTER TABLE canonical.product ADD CONSTRAINT product_publication_minimum
    CHECK (
        publication_status <> 'published'
        OR (
            btrim(name) <> ''
            AND btrim(media_refs) <> ''
            AND (
                list_price IS NOT NULL
                OR product_sale IS NOT NULL
            )
        )
    );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS canonical.variant (
    variant_id         uuid PRIMARY KEY,          -- UUIDv4 (D-017)
    product_id         text NOT NULL
                       REFERENCES canonical.product(product_id),
    sku                text UNIQUE
                       CHECK (sku ~ '^P[0-9]{5}(-[A-Z0-9]{1,4})*$'),
    color_code         text REFERENCES seed.color_term(code),
    size_family        text REFERENCES seed.size_family(family_key),
    size_code          text,
    price_override     bigint CHECK (price_override IS NULL
                                     OR price_override > 0),
    variant_sale       bigint CHECK (variant_sale IS NULL
                                     OR variant_sale > 0),
    variant_sale_until date,
    status             text NOT NULL
                       CHECK (status IN ('draft', 'active', 'archived')),
    created_at         timestamptz NOT NULL DEFAULT now(),
    updated_at         timestamptz NOT NULL DEFAULT now(),
    -- D-018: family and size term stand or fall together; a size
    -- code must belong to the declared family (family-scoped).
    CHECK ((size_family IS NULL) = (size_code IS NULL)),
    CHECK (size_family IS NULL OR size_code IS NOT NULL)
);

-- D-025: a variant sale must be < the applicable base (override, else
-- the product list price). Enforced by trigger (CHECK constraints
-- cannot contain subqueries in PostgreSQL).
CREATE OR REPLACE FUNCTION canonical.variant_sale_base_check()
RETURNS trigger AS $$
DECLARE
    applicable_base bigint;
BEGIN
    IF NEW.variant_sale IS NULL THEN
        RETURN NEW;
    END IF;
    SELECT COALESCE(v.price_override, p.list_price)
      INTO applicable_base
      FROM canonical.variant v
      JOIN canonical.product p ON p.product_id = v.product_id
     WHERE v.variant_id = NEW.variant_id;
    IF applicable_base IS NULL THEN
        RAISE EXCEPTION
            'variant sale requires an applicable base price (D-024/D-025)';
    END IF;
    IF NEW.variant_sale >= applicable_base THEN
        RAISE EXCEPTION
            'variant sale % must be < applicable base % (D-025)',
            NEW.variant_sale, applicable_base;
    END IF;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS variant_sale_base_trigger ON canonical.variant;
CREATE TRIGGER variant_sale_base_trigger
    BEFORE INSERT OR UPDATE OF variant_sale ON canonical.variant
    FOR EACH ROW EXECUTE FUNCTION canonical.variant_sale_base_check();

-- D-014 rule 11: duplicate active-axis combinations rejected
-- (archived variants exempt — the combination may be recreated after
-- archive per D-022 semantics; uniqueness applies to live rows).
CREATE UNIQUE INDEX IF NOT EXISTS variant_active_combo_uq
    ON canonical.variant (product_id,
                          COALESCE(color_code, '~'),
                          COALESCE(size_code, '~'))
    WHERE status <> 'archived';

-- ================================================================== --
-- 4. Mapping registry (D-046)
--    Bidirectional 1:1; SKU stored as data (not here as identity);
--    Woo IDs write-once; stale/orphan/conflict surfaced, never
--    auto-resolved (no automatic re-linking exists).
-- ================================================================== --

CREATE TABLE IF NOT EXISTS registry.mapping_entry (
    entry_type       text NOT NULL CHECK (entry_type IN (
        'product', 'variation', 'category', 'color_term', 'size_term',
        'media_reference')),
    canonical_key    text NOT NULL,
    woo_id           text NOT NULL,
    woo_slug         text,
    status           text NOT NULL DEFAULT 'active' CHECK
        (status IN ('active', 'stale', 'orphaned')),
    created_at       timestamptz NOT NULL DEFAULT now(),
    last_verified_at timestamptz,
    notes            text,
    PRIMARY KEY (entry_type, canonical_key)
);

-- One active entry per Woo ID per type (bidirectional 1:1, D-046
-- §2.2); violation = MAPPING_CONFLICT surfaced to human review.
CREATE UNIQUE INDEX IF NOT EXISTS mapping_woo_id_active_uq
    ON registry.mapping_entry (entry_type, woo_id)
    WHERE status = 'active';

CREATE INDEX IF NOT EXISTS mapping_type_status_idx
    ON registry.mapping_entry (entry_type, status);

-- ================================================================== --
-- 5. Event store (D-027)
--    (source_system, event_id) composite key; payload_hash separates
--    identical repeats (skipped_duplicate) from conflicting ones
--    (integrity error → human review). Terminal states never
--    re-entered — enforced by application flow + this schema.
-- ================================================================== --

CREATE TABLE IF NOT EXISTS events.event_record (
    source_system     text NOT NULL,
    event_id          text NOT NULL,
    operation_type    text NOT NULL,
    received_at       timestamptz NOT NULL DEFAULT now(),
    -- Monotonic INSERTION sequence (M4 Phase-7 audit finding): VM
    -- wall-clock (now()) can step backward under NTP/host sync, so
    -- received_at must never be an ordering key. Event-sourced
    -- reconstruction orders by ingest_seq; received_at is audit
    -- metadata only. bigserial assigns on INSERT when omitted.
    ingest_seq        bigserial,
    processing_status text NOT NULL DEFAULT 'received' CHECK
        (processing_status IN ('received', 'processing', 'succeeded',
                               'failed', 'skipped_duplicate')),
    payload_hash      text NOT NULL,
    result_reference  text,
    retry_count       int NOT NULL DEFAULT 0,
    last_error_class  text,
    last_attempt_at   timestamptz,
    PRIMARY KEY (source_system, event_id)
);

-- ================================================================== --
-- Instagram publishing (Phase 9, D-070)
--    Exclusive double-publish lock: publish_key is the D-070
--    deterministic idempotency key; the PRIMARY KEY constraint IS
--    the lock — a second acquisition of the same key fails/reuses,
--    protecting against network retries AND concurrent dispatchers.
--    Locks are never released on success (protection outlives the
--    attempt).
-- ================================================================== --

CREATE SCHEMA IF NOT EXISTS instagram;

CREATE TABLE IF NOT EXISTS instagram.publish_lock (
    publish_key       text PRIMARY KEY,
    attempt_ref       jsonb NOT NULL,
    locked_at         timestamptz NOT NULL DEFAULT now()
);

-- Phase 10 (D-074): Telegram idempotency vault — same PK-as-lock
-- semantics as instagram.publish_lock (D-070).
CREATE SCHEMA IF NOT EXISTS telegram;

CREATE TABLE IF NOT EXISTS telegram.publish_lock (
    publish_key       text PRIMARY KEY,
    attempt_ref       jsonb NOT NULL,
    locked_at         timestamptz NOT NULL DEFAULT now()
);

-- Phase 11 (D-079): coordinated fan-out anti-race lock. PRIMARY KEY
-- IS the lock: INSERT-once per fanout_key; never deleted on success
-- (double-trigger protection must outlive the attempt).
CREATE SCHEMA IF NOT EXISTS orchestration;

CREATE TABLE IF NOT EXISTS orchestration.fanout_lock (
    fanout_key        text PRIMARY KEY,
    claimant          text NOT NULL,
    locked_at         timestamptz NOT NULL DEFAULT now()
);

-- Phase 12 (D-082): OMS inventory. stock_key = SHA-256(variant_id, sku)
-- per D-082; the guarded conditional UPDATE ... WHERE stock >= qty is
-- the atomic row-level reservation (no oversell by construction).
CREATE SCHEMA IF NOT EXISTS oms;

CREATE TABLE IF NOT EXISTS oms.inventory (
    stock_key         text PRIMARY KEY,
    variant_id        text NOT NULL,
    sku               text NOT NULL,
    stock             integer NOT NULL CHECK (stock >= 0),
    reserved          integer NOT NULL DEFAULT 0 CHECK (reserved >= 0),
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- Reservation ledger (D-082/D-084): one row per reservation, released
-- explicitly; reconciliation uses it to return abandoned stock.
CREATE TABLE IF NOT EXISTS oms.reservation (
    reservation_key   text PRIMARY KEY,
    stock_key         text NOT NULL,
    order_key         text NOT NULL,
    quantity          integer NOT NULL CHECK (quantity > 0),
    state             text NOT NULL,
    created_at        timestamptz NOT NULL DEFAULT now()
);

-- Phase 13 (D-085/D-086): CQRS read model. The analytics schema owns
-- ONLY projections — the transactional domains are never touched.
CREATE SCHEMA IF NOT EXISTS analytics;

-- D-086 incremental cursor: the highest consumed ingest_seq.
CREATE TABLE IF NOT EXISTS analytics.cursor (
    id                integer PRIMARY KEY DEFAULT 1 CHECK (id = 1),
    last_seq          bigint NOT NULL DEFAULT 0,
    updated_at        timestamptz NOT NULL DEFAULT now()
);

-- D-085 metric rollups: kind × window × bucket.
CREATE TABLE IF NOT EXISTS analytics.metric_rollup (
    window_kind       text NOT NULL,
    bucket            text NOT NULL,
    metric_kind       text NOT NULL,
    value             bigint NOT NULL DEFAULT 0,
    count             bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (window_kind, metric_kind, bucket)
);

-- D-086 materialized snapshots: a full serialized rollup state per
-- (window, cursor) — heavy queries read this, not raw events.
CREATE TABLE IF NOT EXISTS analytics.snapshot (
    window_kind       text NOT NULL,
    last_seq          bigint NOT NULL,
    state             jsonb NOT NULL,
    built_at          timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY (window_kind, last_seq)
);

-- D-087 campaign attribution projection (read-model join).
CREATE TABLE IF NOT EXISTS analytics.campaign_attribution (
    campaign_id       text NOT NULL,
    window_kind       text NOT NULL,
    bucket            text NOT NULL,
    publications      bigint NOT NULL DEFAULT 0,
    orders            bigint NOT NULL DEFAULT 0,
    revenue_minor     bigint NOT NULL DEFAULT 0,
    PRIMARY KEY (campaign_id, window_kind, bucket)
);

-- D-088 report audit vault: one row per generated report.
CREATE TABLE IF NOT EXISTS analytics.report_audit (
    window_hash       text PRIMARY KEY,
    report_kind       text NOT NULL,
    window_grain      text NOT NULL,
    window_start      text NOT NULL,
    window_end        text NOT NULL,
    source_cursor     bigint NOT NULL,
    row_count         integer NOT NULL,
    payload           jsonb NOT NULL,
    generated_at      timestamptz NOT NULL DEFAULT now()
);
