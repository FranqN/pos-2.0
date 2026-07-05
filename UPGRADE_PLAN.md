# POS Upgrade Plan (Best-in-industry direction)

## Current state (baseline)
- Multi-tenant (tenant name + logo)
- Auth (login/logout)
- Products CRUD
- Customers CRUD (credit balance field only)
- POS checkout (multi-item cart, discount, split payments, stock decrement)
- Daily report (today totals + low stock demo)
- AI module: safe deterministic reorder suggestions

## Upgrade goals
1) **UI/UX**: modern, faster, touch-friendly POS screen; better workflow (scan/search, cart summary, totals, quick actions).
2) **Inventory correctness**: validation for negative stock, returns, adjustments, purchase receiving.
3) **Operations**: refunds/voids with audit trail; stock units (packs/bundles) optional.
4) **Accounting**: proper line/item totals; VAT support; payment receipts.
5) **Reports**: sales by hour/day/category, product movement, payment breakdown, inventory valuation (simple).
6) **AI upgrades (safe)**: anomaly flags (discount/refund spikes), smart categorization suggestions, smarter reorder qty based on sales velocity per product, draft customer reminders.

## Concrete implementation steps (code changes)

### Phase A — UI overhaul (templates + minor backend)
- Replace `templates/checkout.html` with a better layout:
  - Left: product search + category filters
  - Center: cart table with running totals
  - Right: payment panel with paid/partial/unpaid indicator
  - Buttons: Hold sale, Void sale, Clear cart
- Add lightweight JS for cart building without page reload (keep backend endpoints same for now).
- Improve `base.html` styling (consistent buttons, spacing, responsive).

Files:
- `app/templates/checkout.html`
- `app/templates/base.html`

### Phase B — POS backend improvements (routes)
- Add validation:
  - if requested qty > stock_on_hand → prevent sale and show flash error (or allow setting override in tenant settings)
- Compute totals correctly with discount and line totals.
- Add `/pos/void/<sale_id>` and `/pos/refund/<sale_id>` routes:
  - revert stock movements
  - write an `AuditLog` entry

Files:
- `app/routes/pos.py`
- `app/models.py` (if needed: store refund/void links)
- `app/routes/reports.py` (include refunds/voids in totals)
- `app/models.py` (extend AuditLog usage)

### Phase C — Inventory & purchasing (new features)
- Add suppliers + receiving/purchases:
  - `Supplier` model + `Purchase` model + receiving endpoint
  - stock increases from purchase lines

Files:
- `app/models.py`
- `app/routes/*` (new routes or extend products)

### Phase D — Better reports
- Daily report improvements:
  - payment breakdown (Cash/M-Pesa/Card)
  - top sellers by revenue and quantity
  - low-stock list by reorder_level

Files:
- `app/routes/reports.py`
- `app/templates/daily_report.html`

### Phase E — AI safe additions
- Anomaly flags:
  - flag if discount > tenant threshold (e.g. 20%)
  - flag unusual refund count in last 24h
- Smart reorder qty:
  - use per-product sales velocity (fix current velocity approximation)

Files:
- `app/services/ai_service.py`
- (optional) extend templates to show anomaly cards

## Acceptance checklist
- Create tenant with logo works
- POS sale updates stock and shows correct totals
- Refunding/voiding reverts stock + logs audit
- Daily report shows cash/M-Pesa/card split
- UI is usable on touch screens
- AI suggestions are deterministic and safe (no auto postings)


