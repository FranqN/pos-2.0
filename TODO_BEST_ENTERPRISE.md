# BEST INDUSTRY FEATURES TODO (multi-tenant Flask POS)

This file tracks implementation steps to “make it the best”.

## Phase 0 — Baseline audit
- [ ] Add tests / sanity checks for tenant isolation on all routes
- [ ] Run app locally and verify login -> checkout -> reports

## Phase 1 — Checkout + inventory safety (real business correctness)
- [ ] Add DB transaction wrapper for sale creation + stock updates
- [ ] Prevent double-selling: lock/atomic decrement strategy (within DB transaction)
- [ ] Add refund flow (sale_type=refund) + stock return + payment updates
- [ ] Add stock adjustment UI + stock_movements with adjustment/return types
- [ ] Fix sale number uniqueness (sequence per tenant) and avoid collisions

## Phase 2 — Roles + Audit Logs (enterprise control)
- [ ] Implement RBAC decorator/permission checks by role
- [ ] Ensure every route filters by tenant_id for all DB reads/writes
- [ ] Add AuditLog writes for: stock changes, price changes, discounts, refunds
- [ ] Add per-tenant user management (optional for owner)

## Phase 3 — Reporting + exports
- [ ] Daily report: breakdown by cashier + payment method + VAT (if enabled)
- [ ] Sales history page (with filters) + CSV export
- [ ] Inventory valuation report + low stock report

## Phase 4 — White-label + UX polish
- [ ] Brand theme per tenant (logo, name, colors)
- [ ] Better checkout UI: keyboard navigation, fast add items
- [ ] Improve invoice/receipt page (print-friendly PDF if feasible)

## Phase 5 — AI differentiation (safe suggestions)
- [ ] Upgrade reorder suggestions to include recent velocity + lead-time inputs
- [ ] Add anomaly flags: unusual discounts, frequent refunds, abnormal stock deltas
- [ ] Add explanation strings + “why this suggestion” in UI

## Phase 6 — Ops / Setup / Seed
- [ ] Add DB init + seed command/CLI
- [ ] Add quickstart in README with exact steps
- [ ] Add error handlers + consistent flash messaging

