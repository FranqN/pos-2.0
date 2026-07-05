# TODO - Login & Account Creation Fix

## Plan steps
- [x] Step 1: Update `app/routes/auth.py` to harden `/login` (safe tenant_id parsing, clearer flashes, and more reliable user lookup).

- [x] Step 2: Update `app/routes/tenant.py` to ensure tenant creation commits correctly and failures are surfaced.

- [ ] Step 3: Add/adjust an end-to-end smoke test in `tests/` that:
  - creates a tenant
  - logs in as the created owner
  - asserts we reach `/pos/checkout` (or at least a logged-in protected page).
- [ ] Step 4: Run `pytest -q` and fix any failures.

