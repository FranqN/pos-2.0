# Multi-tenant POS — Tenant Account Features Checklist

This checklist enumerates what each **tenant (store)** should have access to in a multi-tenant POS system.

## 1) Store / Tenant Setup
- Tenant profile: name, phone, email, address
- Tenant settings:
  - Currency
  - VAT enabled + VAT rate
  - Invoice sequence (`next_sale_sequence`)
- Store assets:
  - Tenant logo upload (used in UI header)
- Store lifecycle:
  - Activate/deactivate tenant (optional)
  - Prevent cross-tenant data access

## 2) Users, Roles, and Access Control (per tenant)
- Role-based permissions (at minimum):
  - Owner
  - Manager
  - Cashier
- Authentication & session separation by tenant users
- Tenant scoping enforced for:
  - Products
  - Customers
  - Sales / invoices
  - Stock movements
  - Reports
  - Audit logs
- Audit logging for key actions (recommended)

## 3) Product Catalog (tenant-scoped)
- Product CRUD (create/read/update/deactivate)
- Product attributes:
  - Name, SKU, barcode
  - Category
  - Price, cost
  - Stock on hand
  - Reorder level
  - Active flag
- Low-stock indicators based on `stock_on_hand` vs `reorder_level`
- Product history (recommended):
  - Stock movements tracked for purchase/sale/return/refund/void

## 4) Customer Management (tenant-scoped)
- Customer CRUD: name, phone, notes
- Optional credit/balance:
  - Credit purchases support
  - Customer balance tracking
  - Optional credit limits / credit terms

## 5) POS Checkout & Sales Workflow (tenant-scoped)
- Checkout UI:
  - Add products to cart
  - Select customer (optional)
  - Apply discount
  - Multiple payment methods (cash/mpesa/card)
- Sale creation:
  - Invoice numbering using tenant sequence
  - Payment status calculation: paid / partial / unpaid
  - Transaction-safe behavior:
    - stock decrement with concurrency locking
- Post-sale effects:
  - Update customer credit balance (if customer selected)
  - Create audit log entry

## 6) Refund / Void / Returns (tenant-scoped)
- Void sale:
  - Revert stock movements
  - Revert customer balance (if applicable)
  - Mark sale status as voided
  - Audit log entry
- Refund sale:
  - Revert stock movements
  - Revert customer balance (if applicable)
  - Mark sale status as refunded
  - Audit log entry

## 7) Reports & Analytics (tenant-scoped)
- Daily report:
  - Total sales amount
  - Invoice count
  - Payment breakdown (cash/mpesa/card)
- Sales history browsing (if implemented)
- Low-stock / reorder insights (optional)
- Date-range filtering (optional)

## 8) Operational Features (recommended per tenant)
- Data maintenance:
  - Export (optional): CSV/PDF
  - Data consistency checks (optional)
- Backup/restore strategy (optional)
- Tenant seed/reset endpoints (dev/admin only)

---

## Best-practice Validation (must verify)
- Every query is filtered by `tenant_id` (directly or via scoped joins)
- UI navigation routes only expose tenant-safe functionality
- Void/refund correctly revert:
  - product stock
  - customer balance
  - audit logs
