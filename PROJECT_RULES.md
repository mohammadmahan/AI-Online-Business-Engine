# PROJECT RULES

# AI-First Online Business Engine

This document is the operational constitution of the project. Every AI
agent, developer, automation, or contributor must follow it.

## 1. Core Principles

Priority:

1.  Correctness
2.  Security
3.  Simplicity
4.  Maintainability
5.  Cost efficiency
6.  Scalability
7.  Documentation

Never sacrifice correctness or security for speed.

## 2. Read Before Work

Before meaningful work:

1.  Read `MASTER_PLAN.md`.
2.  Read `PROJECT_RULES.md`.
3.  Read relevant documentation.
4.  Identify the current phase.
5.  Read `TODO.md` when it exists.
6.  Read relevant architecture, data-model, and security documents when
    they exist.

If a document does not yet exist because its phase has not started, do
not invent it. Report that it is missing.

## 3. Human Authority

The human owner has final authority over:

-   Business decisions
-   Major architecture
-   Production infrastructure
-   Payment
-   Financial operations
-   Refunds
-   Credentials
-   Security
-   Deployment
-   Data deletion
-   Vendor selection
-   Major vendor dependencies

AI may recommend but must not silently make high-risk decisions.

## 4. Major Architecture Changes

STOP -\> EXPLAIN -\> APPROVAL is required for changes involving:

-   Database architecture
-   Ecommerce source of truth
-   Authentication
-   Payment
-   Security
-   Infrastructure
-   API strategy
-   Data ownership
-   Major vendor dependency
-   Production deployment

Do not silently replace a selected system.

## 5. Mature Systems

Prefer mature systems:

-   WooCommerce for ecommerce
-   n8n for orchestration
-   Notion for business knowledge/management
-   Official APIs for integrations

Custom development requires a clear reason.

## 6. Data Integrity

Never invent:

-   Product specifications
-   Material
-   Color
-   Size
-   Measurements
-   Price
-   Discount
-   Stock
-   Shipping time
-   Payment status
-   Order status
-   Customer information

Use `UNKNOWN` or `NOT_PROVIDED` when information is unavailable.

## 7. AI Provenance

AI-generated information must be distinguishable from verified
information.

Use:

``` text
AI_GENERATED
HUMAN_REVIEWED
HUMAN_VERIFIED
```

AI inference must never be presented as verified fact.

## 8. Product Rules

Product attributes are optional unless explicitly required.

Incomplete products are valid.

Never fill missing optional fields with guesses.

## 9. Variant Rules

A variant is a real independently sellable/stocked combination.

Do not create artificial variants for products that do not need
variants.

Support variant-level prices and inventory.

## 10. SKU Rules

SKU means Stock Keeping Unit.

Every independently stocked/sold variant needs a unique SKU.

Rules:

-   Unique
-   Deterministic
-   Stable
-   Never silently reused
-   Production changes require human approval
-   Duplicate SKUs are a blocking data-integrity error

Provisional example:

``` text
P0001-BLK-M
```

The final production convention requires approval.

## 11. Price Rules

Store Toman prices numerically, for example:

``` text
590000
```

Do not store formatted text such as `590,000 تومان` as the primary
value.

Production prices must not change automatically without authorization.

## 12. Inventory Rules

WooCommerce is the transactional inventory Source of Truth.

-   Use verified inventory.
-   Never estimate actual stock with AI.
-   Inventory changes must be idempotent.
-   Duplicate events must not double-decrement stock.
-   Changes must be auditable.
-   Retry logic must be safe.
-   Recovery must be possible.

## 13. WooCommerce Rules

WooCommerce is the transactional Source of Truth for:

-   Products
-   Variants
-   SKUs
-   Prices
-   Inventory
-   Orders
-   Customers
-   Coupons
-   Store state

Notion is not the transactional source of truth.

Excel is an import/cleanup tool, not the production database.

## 14. n8n Rules

Every workflow must define:

-   Name
-   Purpose
-   Trigger
-   Inputs
-   Outputs
-   Error handling
-   Retry strategy
-   Idempotency where needed
-   Logging
-   Credentials
-   Human approval where required

Prefer small, composable workflows.

Avoid hidden side effects.

## 15. API and Integration Rules

Prefer:

1.  Official API
2.  Mature supported integration
3.  Reliable open-source adapter
4.  Custom adapter
5.  Browser automation only when justified and reviewed

Critical production systems should not depend on undocumented APIs
without explicit review.

Every integration must define authentication, inputs, outputs, errors,
rate limits, retries, idempotency, and recovery.

## 16. Secrets and Credentials

Never place secrets in:

-   Source code
-   Git
-   Markdown
-   README
-   Screenshots
-   Logs
-   Public repositories
-   Hard-coded workflow nodes

Use secure credential storage or environment variables.

If a secret is exposed, STOP and report it immediately and rotate it
when appropriate.

## 17. Least Privilege

Grant only necessary permissions.

Do not grant broad production access for convenience.

Freebuff and AI agents must not receive unrestricted production
credentials by default.

## 18. Environment Separation

Prefer:

``` text
Development
-> Testing/Staging
-> Production
```

Do not test experimental code against production payment, inventory, or
customer systems.

## 19. Git Rules

Use Git for project history.

Commit meaningful milestones.

Never commit secrets, passwords, API keys, tokens, private credentials,
or unnecessary sensitive customer data.

Destructive Git operations require explicit approval.

## 20. File Safety

Before changing important files:

-   Understand their purpose.
-   Check whether they are tracked.
-   Preserve existing information.
-   Avoid unnecessary rewrites.
-   Do not silently overwrite user work.

For conversion, create a safe copy first unless replacement is
explicitly approved.

## 21. Database Safety

Before database-structure changes:

-   Explain the change.
-   Check compatibility.
-   Consider migration.
-   Consider backup.
-   Consider rollback.
-   Obtain approval for major production changes.

Never casually run destructive production database commands.

## 22. Destructive Operations

Examples:

-   Delete database data
-   Delete customer records
-   Delete products
-   Delete files
-   Drop tables
-   Reset production
-   Revoke credentials
-   Rewrite Git history
-   Replace production configuration

Require explicit human approval.

## 23. Testing

Test:

-   Normal cases
-   Empty input
-   Missing fields
-   Invalid input
-   Duplicate events
-   API failures
-   Timeouts
-   Authentication failures
-   Rate limits
-   Partial failures
-   Malformed AI output
-   Human rejection
-   Retry
-   Recovery

Financial, payment, inventory, and order workflows require failure
testing before production.

## 24. Error Handling

Never hide errors.

Important workflows must detect, log, safely retry when appropriate,
escalate when necessary, and support recovery.

Never swallow errors merely to make a workflow appear successful.

## 25. Idempotency

Webhook, retry, scheduled, and external events must not create harmful
duplicate effects.

Examples:

-   Same event must not create duplicate orders.
-   Same event must not decrement inventory twice.
-   Same event must not trigger duplicate financial action.

Use stable event IDs or idempotency keys where available.

## 26. Rollback and Recovery

Important production changes require a recovery strategy.

Before high-risk changes identify:

-   Backup
-   Rollback method
-   Recovery owner
-   Failure modes

Undoing code does not automatically undo external side effects.

## 27. Logging and Observability

Important systems must allow us to determine:

-   What happened
-   When
-   Which workflow
-   Which event
-   Which system
-   Success/failure
-   Retry status
-   Human involvement

Never log secrets.

Minimize sensitive customer data in logs.

## 28. Customer Data Minimization

Collect only necessary customer information.

Do not duplicate personal information without reason.

Minimize operational copies in Notion.

Expose customer data to AI only when necessary.

## 29. Instagram

Prefer official Meta/Instagram APIs and supported integrations.

Avoid fragile unofficial automation for critical production workflows
when a supported API exists.

Customer-facing AI must use verified product and order data.

Escalate when the model is uncertain, information is unavailable, the
issue is financially sensitive, or the action is irreversible/high risk.

## 30. Payment

Payment status must be verified server-side.

Before production:

-   Provider selected
-   Callback behavior tested
-   Verification implemented
-   Duplicate callbacks handled
-   Failed payments handled
-   Logging implemented
-   Human approval obtained

Do not issue refunds automatically without an approved safe workflow.

## 31. Shipping

Shipping data must come from verified business/provider data.

Never invent:

-   Shipping price
-   Delivery date
-   Tracking number
-   Shipment status

## 32. AI Autonomy

### Green --- autonomous

-   Classification
-   Formatting
-   Drafts
-   Internal summaries
-   Low-risk transformations

### Yellow --- monitored

-   Customer reply drafts
-   Product descriptions
-   Lead classification
-   Marketing drafts
-   Recommendations

### Red --- human approval

-   Refunds
-   Financial actions
-   Production price changes
-   Credential changes
-   Security changes
-   Destructive operations
-   Permanent deletion
-   High-impact disputes
-   High-risk production deployment

## 33. AI Output Validation

Validate structured AI output before it affects business systems.

Never directly trust model output for:

-   Price
-   Inventory
-   Payment
-   Refunds
-   Customer identity
-   Order status
-   Destructive operations

Prefer schemas and deterministic validation.

## 34. Cost Control

Before adding a paid service:

1.  Check existing capabilities.
2.  Check open source.
3.  Check self-hosting.
4.  Check n8n.
5.  Check Freebuff/custom tooling.
6.  Calculate total cost.
7.  Consider maintenance.
8.  Consider vendor lock-in.
9.  Compare business value.

Include hosting, API, AI, storage, bandwidth, maintenance, domain,
payment, and provider costs.

## 35. Vendor Lock-in

Keep important provider integrations replaceable where practical.

Use clear boundaries such as:

``` text
AIProvider
PaymentProvider
ShippingProvider
InstagramProvider
```

## 36. Custom Development

Before custom development ask:

1.  What problem does it solve?
2.  Does an existing system solve it?
3.  Can n8n solve it?
4.  Can WooCommerce solve it?
5.  Can Notion solve it?
6.  Can open source solve it?
7.  What is maintenance cost?
8.  Is it reusable?

If unclear, evaluate before building.

## 37. Documentation

Update documentation when architecture, data ownership, API behavior,
security, deployment, workflow behavior, or important business rules
change.

Do not allow documentation to become silently false.

## 38. Definition of Done

A meaningful task is done when:

-   Correct implementation exists.
-   Relevant tests/checks pass.
-   Failure cases are considered.
-   Security is considered.
-   Documentation is updated when needed.
-   Git state is understandable.
-   Required approval exists.
-   No known critical failure is hidden.

## 39. Freebuff Execution Protocol

For every meaningful task:

1.  Read `MASTER_PLAN.md`.
2.  Read `PROJECT_RULES.md`.
3.  Read relevant documentation.
4.  Identify current phase.
5.  State the plan before major changes.
6.  Make the smallest safe change.
7.  Do not expand scope without approval.
8.  Run checks/tests.
9.  Review changes.
10. Update documentation.
11. Update `TODO.md` when it exists.
12. Report files changed, reasons, tests, results, risks, remaining
    work, and next step.

For high-risk architecture or production changes, STOP and request
approval.

## 40. Unclear Tasks

If ambiguity can cause data loss, financial impact, security risk,
outage, vendor lock-in, or architectural damage, do not guess.

For low-risk ambiguity, choose the simplest reversible option and report
the assumption.

## 41. No Hidden Failure

Never claim success if a command, test, API call, file operation, or
workflow partially failed.

Report partial success honestly.

## 42. No Unrelated Refactoring

Do not refactor unrelated code during a focused task.

Keep changes small, reviewable, reversible, and relevant.

Large refactors require separate planning.

## 43. Production Rule

Use:

``` text
Development
-> Test
-> Review
-> Approval
-> Production
```

Do not use:

``` text
Development
-> Production
```

for high-risk changes.

## 44. Final Rule

When multiple approaches are valid, choose the one that is:

-   Simplest
-   Safest
-   Cheapest
-   Portable
-   Maintainable
-   Testable
-   Observable
-   Recoverable
-   Replaceable

The goal is not the most complicated AI system. The goal is the most
reliable business system that uses AI where AI provides real value.
