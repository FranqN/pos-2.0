# BEST ENTERPRISE POS — Execution Checklist (Phase 0 → Phase 6)

This checklist tracks work to make the current multi-tenant Flask POS **enterprise-grade**:
- correctness (inventory + transactions)
- multi-tenant safety
- roles/permissions
- auditability
- reporting/export
- UX + white-label
- AI differentiation (safe suggestions)
- ops hardening

## Phase 0 — Baseline audit
- [ ] Add tests / sanity checks for tenant isolation on all routes
  - [ ] /pos/checkout (GET)
  - [ ] /pos/sale (POST)
  - [ ] /products/ (GET, POST)
  - [ ] /customers/ (GET, POST)
  - [ ] /reports/daily (GET)
  - [ ] /tenant/create (POST)
- [ ] Run app locally and verify login → checkout → reports
- [ ] Ensure consistent error handling is registered in app factory
- [ ] Add smoke checks for tenant_id scoping (no unscoped queries)

## Phase 1 — Checkout + inventory safety (business correctness)
- [ ] Add DB transaction wrapper for sale creation + stock updates
- [ ] Prevent double-selling with atomic decrement / locking strategy
- [ ] Ensure Sale and StockMovement writes are consistent (all-or-nothing)
- [ ] Add refund flow (`sale_type="refund"`)
  - [ ] stock return
  - [ ] payment/status updates
- [ ] Add stock adjustment type + stock_movements for adjustments/returns
- [ ] Fix sale number uniqueness (per-tenant sequence; collision-proof)

## Phase 2 — Roles + Audit Logs (enterprise control)
- [ ] Implement RBAC decorator / permission checks by role
- [ ] Ensure every route filters by `tenant_id` for all DB reads/writes
- [ ] Add AuditLog writes for:
  - [ ] stock changes (sale, refund, adjustment)
  - [ ] sale created/refunded
  - [ ] price changes and discounts (when implemented)
- [ ] Add audit details schema consistency (action/entity/detail/created_by)
- [ ] (Optional) per-tenant user management for owner role

## Phase 3 — Reporting + exports
- [ ] Daily report enhancements
  - [ ] breakdown by cashier (created_by)
  - [ ] payment method totals (cash/mpesa/card)
  - [ ] VAT breakdown (when enabled)
- [ ] Sales history page with filters
  - [ ] date range
  - [ ] customer
  - [ ] payment method
  - [ ] sale_type
- [ ] CSV export for sales history
- [ ] Inventory valuation report
- [ ] Low stock report

## Phase 4 — White-label + UX polish
- [ ] Brand theme per tenant (logo/name/currency/vat)
- [ ] Better checkout UI (keyboard navigation, faster cart entry)
- [ ] Print-friendly receipt/invoice (at minimum print CSS; PDF if feasible)

## Phase 5 — AI differentiation (safe suggestions)
- [ ] Upgrade reorder suggestions using:
  - [ ] recent sales velocity with correct time window
  - [ ] lead-time inputs (if/when added)
- [ ] Add anomaly flags:
  - [ ] unusual discounts
  - [ ] frequent refunds
  - [ ] abnormal stock deltas
- [ ] Add explanation strings (“why this suggestion”) in UI

## Phase 6 — Ops / Setup / Seed
- [ ] Add DB init + seed command/CLI
- [ ] Add quickstart in README with exact steps
- [ ] Ensure all error handlers + consistent flash messaging
- [ ] Add structured logging (request id, tenant id, user id, route)
- [ ] Add basic monitoring hooks (optional)

## Notes / Known current gaps (from code review)
- [ ] Inventory decrement is not concurrency-safe (risk of double-selling)
- [ ] Sale number generation is time-based and can collide under load; not per-tenant sequence
- [ ] AuditLog exists but isn’t written from core flows
- [ ] RBAC not enforced in routes (only login_required)
- [ ] Error handlers exist but may not be registered in create_app
