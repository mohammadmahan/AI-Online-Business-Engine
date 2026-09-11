PROJECT RULES

AI ECOMMERCE BUSINESS ENGINE

Version: 1.0
Status: Active

---

1. CORE PRINCIPLE

This project is a production-oriented ecommerce and automation system.

The agent must prioritize:

1. Correctness
2. Security
3. Simplicity
4. Maintainability
5. Cost efficiency
6. Scalability
7. Documentation

Do not optimize for speed at the expense of reliability.

---

2. READ BEFORE WORKING

Before performing any meaningful task, read:

- MASTER_PLAN.md
- PROJECT_RULES.md
- relevant documentation
- relevant architecture files
- current TODO.md

Do not assume the current state of the project.

---

3. DO NOT REBUILD EXISTING SYSTEMS

Before implementing a feature, determine whether it can be provided by:

1. WooCommerce
2. n8n
3. Notion
4. Existing open-source software
5. Existing APIs
6. An existing reusable workflow

Only build custom functionality when there is a clear reason.

---

4. DO NOT MAKE MAJOR ARCHITECTURAL DECISIONS SILENTLY

If a change affects:

- database architecture
- ecommerce architecture
- authentication
- payment
- security
- infrastructure
- API strategy
- data ownership
- vendor dependency

STOP before implementing the architectural change.

Explain:

- current architecture
- proposed architecture
- reason
- advantages
- disadvantages
- migration impact

Wait for human approval when required.

---

5. HUMAN AUTHORITY

The human owner has final authority over:

- business decisions
- major architecture
- financial decisions
- production deployment
- payment
- refunds
- destructive operations
- credentials
- security policies

The agent assists.

The agent does not own the business.

---

6. NEVER INVENT DATA

Never invent:

- product specifications
- product materials
- product colors
- sizes
- prices
- stock
- discounts
- shipping times
- payment status
- customer information

If information is unavailable:

Use:

UNKNOWN

or:

NOT PROVIDED

or ask for clarification.

---

7. AI DATA INTEGRITY

AI-generated information must be distinguishable from human-verified information.

Possible states:

AI_GENERATED
HUMAN_REVIEWED
HUMAN_VERIFIED

Never represent AI inference as verified fact.

---

8. OPTIONAL PRODUCT ATTRIBUTES

Product attributes are optional unless explicitly marked required.

The system must support incomplete products.

Example:

A product may have:

- name
- price
- category

without:

- brand
- fabric
- pattern
- season
- collar
- sleeve

Do not block product creation unnecessarily.

---

9. PRODUCT AND VARIANT RULES

A Product represents the general product.

A Variant represents a sellable combination.

Example:

Product:
T-shirt

Variants:

Black / M
Black / L
White / M
White / L

Variant-level fields may include:

- SKU
- color
- size
- price
- stock
- barcode
- weight

Do not duplicate product-level information unnecessarily inside Variants.

---

10. SKU RULES

SKU must be unique.

Never silently reuse an existing SKU.

Never generate a random SKU without following the project's SKU strategy.

SKU must remain stable after creation unless a human explicitly approves a change.

---

11. PRICE RULES

Currency:

Iranian Toman.

Store prices numerically.

Do not store:

"590,000 تومان"

as the primary numeric value.

Store:

590000

Currency should be represented separately when necessary.

Never modify a production price automatically without authorization.

---

12. INVENTORY RULES

Inventory must come from a verified source.

AI cannot estimate inventory.

Never decrement inventory twice because of duplicate events.

Inventory operations must be idempotent where possible.

---

13. SOURCE OF TRUTH

For ecommerce:

WooCommerce is the primary source of truth.

Notion is not the primary source for:

- inventory
- payment
- order state
- stock
- critical product availability

Excel is an import/management tool, not the permanent production database.

---

14. NOTION RULES

Use Notion for:

- documentation
- dashboards
- SOP
- knowledge
- planning
- business management

Do not use Notion as a replacement for a proper transactional database.

---

15. N8N RULES

Every workflow must h