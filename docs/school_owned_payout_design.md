# School-Owned Payout Architecture — Design Document

> **Status**: Design only — no code yet.
> **Prerequisite**: `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY` remains `False` until this is implemented and validated.

---

## 1. School Funds Ledger

Each school's Paystack subaccount receives fee payments via split settlement. The ledger tracks funds through five states:

| State | Meaning |
|---|---|
| `collected` | Paystack charge.success received; money is with Paystack, not yet settled |
| `cleared` | Paystack settlement paid to school subaccount (T+1 to T+3 depending on channel) |
| `available` | Cleared funds minus any platform holds — eligible for payout requests |
| `reserved` | Locked against a pending/approved payout request (cannot be double-spent) |
| `paid_out` | Transfer executed and confirmed successful |

**Storage**: A single `SchoolFundsLedgerEntry` per state transition, append-only. Running balances derived via `SUM(amount) GROUP BY school, state` or a denormalized `SchoolFundsBalance` row refreshed on each transition.

**Key fields on `SchoolFundsBalance`** (denormalized, one row per school):
- `school` FK, unique
- `total_collected`, `total_cleared`, `available_balance`, `total_reserved`, `total_paid_out`
- `last_reconciled_at`, `last_settlement_synced_at`

---

## 2. Reconciliation Rules

### Fund state transitions

```
collected  →  cleared     Triggered by Paystack settlement webhook or daily settlement sync job
cleared    →  available   Automatic: cleared funds become available after settlement confirmation
available  →  reserved    When a payout request is approved (maker-checker)
reserved   →  paid_out    When Paystack transfer.success webhook confirms the payout
reserved   →  available   When payout fails (transfer.failed) or is cancelled before execution
```

### When a school becomes eligible to pay staff

All of these must be true:
1. `school.is_payout_setup_active == True` (subaccount exists and is active)
2. `school.funds_balance.available_balance >= requested_payout_amount`
3. School has at least one leadership user who can approve (maker-checker)
4. `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY == True`
5. School feature `staff_paystack_transfers` is enabled

### Settlement lag handling

- Paystack settles to subaccounts T+1 (MoMo) to T+3 (cards). During this window, funds are `collected` but not `cleared`.
- A daily cron job calls `GET /settlement` on the Paystack API to reconcile actual settlements against `collected` entries, moving confirmed ones to `cleared → available`.
- UI shows the distinction: "GHS X collected (settling)" vs "GHS Y available for payout".
- No payout can be requested against uncollected/uncleared funds.

---

## 3. Payout Workflow

```
request → approve → execute → settle → [done]
                  → execute → fail → [retry or cancel]
request → cancel  (before approval)
approve → cancel  (before execution, returns reserved → available)
```

| Step | Actor | Action |
|---|---|---|
| **request** | Accountant or school_admin | Creates `StaffPayoutRequest` with amount, staff list, period. Funds move `available → reserved`. |
| **approve** | Different leadership user (maker ≠ checker) | Sets status `approved`. No fund movement — already reserved. |
| **execute** | System (on approval) or manual trigger | Calls `paystack_service.initiate_transfer` per recipient. Sets status `executing`. |
| **settle** | Webhook `transfer.success` | Moves funds `reserved → paid_out`. Links to `StaffPayrollPayment` rows. |
| **fail** | Webhook `transfer.failed` | Marks payout failed. Funds `reserved → available`. Records failure reason. |
| **cancel** | Requester or approver | Only before `executing`. Funds `reserved → available`. |

---

## 4. Controls

### School-scoped permissions

| Action | Required role(s) |
|---|---|
| Request payout | `can_manage_finance` (accountant, school_admin, deputy_head, hod) |
| Approve payout | `is_school_leadership` AND `user != requester` |
| Cancel payout | Requester (if pending) or approver (if approved, not yet executing) |
| View payout history | `can_manage_finance` |
| View funds ledger | `can_manage_finance` |

### Maker-checker approval

- The user who creates the payout request **cannot** approve it.
- Enforced at the model level: `StaffPayoutRequest.requested_by != approved_by` (DB constraint).
- Schools with only one leadership user cannot use automated payouts — they must have at least two.

### Audit trail

- Every `SchoolFundsLedgerEntry` is append-only (no updates/deletes).
- `StaffPayoutRequest` has full lifecycle timestamps: `requested_at`, `approved_at`, `executed_at`, `settled_at`, `failed_at`, `cancelled_at`.
- All actor fields: `requested_by`, `approved_by`, `cancelled_by`.
- Existing `audit.AuditLog` captures model-level changes automatically.

### Duplicate payout prevention

- Unique constraint on `(school, user, period_label)` per `StaffPayoutRequest` at status not in (`cancelled`, `failed`).
- Paystack transfer reference is generated deterministically: `SPR_{payout_request.pk}_{staff_user.pk}_{uuid8}` — idempotent retries reuse the same reference.
- Before creating a request, check for existing active requests covering the same staff + period.

### Cross-school funding prevention

- `SchoolFundsBalance` is FK'd to `School` with unique constraint.
- `StaffPayoutRequest.school` must match `staff_user.school`.
- All queries use `SchoolScopedManager.for_school(school)`.
- The `reserved` amount is deducted from the requesting school's balance only — never from platform or another school.
- Transfer is initiated from the school's Paystack subaccount balance, not the platform merchant balance.

---

## 5. Data Model Plan

### New models (in `finance/models.py`)

**`SchoolFundsLedgerEntry`**
```
school              FK(School)
entry_type          CharField choices: collected, cleared, available, reserved, paid_out, released
amount              DecimalField(12,2)    # positive = credit, negative = debit
currency            CharField(8) default "GHS"
reference           CharField(255)        # Paystack reference or payout request ID
description         CharField(500)
related_payment     FK(FeePayment, null)  # links to the originating fee payment
related_payout      FK(StaffPayoutRequest, null)
created_at          DateTimeField
```
Indexes: `(school, entry_type, created_at)`, `(reference)`

**`SchoolFundsBalance`** (denormalized)
```
school              OneToOneField(School)
total_collected     Decimal(14,2) default 0
total_cleared       Decimal(14,2) default 0
available_balance   Decimal(14,2) default 0
total_reserved      Decimal(14,2) default 0
total_paid_out      Decimal(14,2) default 0
last_reconciled_at  DateTimeField(null)
updated_at          DateTimeField(auto_now)
```
Constraint: `available_balance >= 0`

### New models (in `accounts/hr_models.py`)

**`StaffPayoutRequest`**
```
school              FK(School)
period_label        CharField(64)         # e.g. "January 2026"
total_amount        Decimal(12,2)
currency            CharField(8) default "GHS"
status              CharField choices: pending, approved, executing, settled, failed, cancelled
requested_by        FK(User)
approved_by         FK(User, null)
cancelled_by        FK(User, null)
requested_at        DateTimeField(auto_now_add)
approved_at         DateTimeField(null)
executed_at         DateTimeField(null)
settled_at          DateTimeField(null)
failed_at           DateTimeField(null)
cancelled_at        DateTimeField(null)
failure_reason      TextField(blank)
notes               TextField(blank)
```
Constraints: `approved_by != requested_by` (DB check), unique `(school, period_label)` where status not in (`cancelled`, `failed`)
Indexes: `(school, status)`, `(school, period_label)`

**`StaffPayoutRequestLine`**
```
payout_request      FK(StaffPayoutRequest)
staff_user          FK(User)
amount              Decimal(12,2)
payroll_payment     FK(StaffPayrollPayment, null)  # linked after execution
paystack_transfer_code  CharField(64, blank)
paystack_status     CharField(16, blank)            # pending/success/failed
failure_reason      TextField(blank)
```
Index: `(payout_request, staff_user)` unique

### Existing models affected

| Model | Change |
|---|---|
| `StaffPayrollPayment` | Add nullable FK `payout_request_line` back-link |
| `School` | No changes (already has `is_payout_setup_active`) |

### Modules/files affected

| File | Change |
|---|---|
| `finance/models.py` | Add `SchoolFundsLedgerEntry`, `SchoolFundsBalance` |
| `accounts/hr_models.py` | Add `StaffPayoutRequest`, `StaffPayoutRequestLine` |
| `accounts/hr_views.py` | New views: `payout_request_create`, `payout_request_approve`, `payout_request_cancel`, `payout_request_list` |
| `finance/views.py` | New view: `school_funds_dashboard` (read-only ledger + balance) |
| `finance/staff_payroll_paystack.py` | Refactor `initiate_staff_payroll_paystack_transfer` to work from `StaffPayoutRequestLine` instead of direct `StaffPayrollPayment` |
| `finance/paystack_service.py` | Add `get_settlements()` method for reconciliation |
| `finance/reconciliation.py` | **New file**: settlement sync cron, ledger entry creation |
| `accounts/urls.py` | Add payout request URLs |
| `finance/urls.py` | Add funds dashboard URL |
| `templates/accounts/` | New templates for payout request CRUD |
| `templates/finance/` | New template for funds dashboard |
| `schools/features.py` | No change (already has `staff_paystack_transfers`) |
| `settings.py` | No change (`PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY` already exists) |

### Migration risks

- **`SchoolFundsLedgerEntry`**: New table, no risk. Backfill completed `FeePayment` rows as `collected+cleared+available` for existing schools (data migration).
- **`SchoolFundsBalance`**: New table. Backfill one row per school with aggregated values from existing payments.
- **`StaffPayoutRequest` + lines**: New tables, no risk to existing data.
- **`StaffPayrollPayment` FK addition**: Nullable, no data loss. Existing rows get `NULL`.
- **No destructive changes to existing tables.**

---

## 6. Rollout Plan

### Phase 1 — Ship immediately (safe, read-only)
1. `SchoolFundsLedgerEntry` + `SchoolFundsBalance` models + migration
2. Backfill migration for existing completed fee payments
3. Read-only funds dashboard (view-only, no payout actions)
4. Settlement sync cron job (populates ledger from Paystack settlements API)
5. `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY` stays `False`

**Why safe**: All additive. No changes to payment flow. Dashboard is read-only.

### Phase 2 — Payout request + approval workflow (behind gate)
1. `StaffPayoutRequest` + `StaffPayoutRequestLine` models + migration
2. Request creation view (deducts from `available_balance` → `reserved`)
3. Approval view (maker-checker enforcement)
4. Cancel view
5. `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY` stays `False` — workflow is testable but execution is blocked.

**Why safe**: Gate prevents actual transfers. Schools can create/approve/cancel requests as dry-run.

### Phase 3 — Execute + settle (enable for pilot schools first)
1. Execution logic: approved request → Paystack transfers from school subaccount balance
2. Webhook handlers for `transfer.success` / `transfer.failed` linked to payout request lines
3. `StaffPayrollPayment` back-link population
4. Enable `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY=True` for one pilot school via school feature flag override
5. Monitor for one billing cycle

### Phase 4 — General availability
1. Set `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY=True` globally
2. Each school still needs `staff_paystack_transfers` feature enabled + `is_payout_setup_active == True`
3. Document the rollout in school onboarding guide

### What must remain disabled until Phase 3+
- Actual Paystack transfer execution
- `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY` must stay `False`
- The existing `initiate_staff_payroll_paystack_transfer` path (platform-balance debits) is permanently retired once school-owned payouts go live

---

# PR Changelog — Staff Payout Hardening

## Changes

### `finance/staff_payroll_paystack.py`
- **Added** `staff_paystack_school_owned_controls_ready()` — safety gate that reads `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY` (default `False`).
- **Updated** `school_staff_paystack_allowed()` — now requires both `staff_paystack_transfers_enabled()` AND `staff_paystack_school_owned_controls_ready()`.

### `settings.py`
- **Added** `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY = env_bool("PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY", False)` — keeps automated staff payouts disabled until school-owned funding controls are implemented.

### `accounts/hr_views.py`
- **Hardened** `staff_payroll_disburse`: Paystack modes now require `_require_leadership()` (school_admin, deputy_head, hod).
- **Added** granular error messages: distinguishes "transfers globally disabled" vs "school-owned controls not ready" vs "school feature off".
- **Added** `paystack_school_owned_ready` to template context for conditional UI.

### `templates/accounts/staff_payroll_disburse.html`
- **Updated** heading text: "Record or disburse" (clarifies record-only is always available).
- **Added** conditional warning when `paystack_school_owned_ready` is `False`.

### `accounts/tests.py`
- **Added** `school_admin` user to `StaffPayrollDisburseTests.setUpTestData`.
- **Updated** `override_settings` to include `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY=True`.
- **Fixed** test logins to use correct roles (accountant for record-only, school_admin for automated).
- **Added** `test_paystack_blocked_for_non_leadership_user` — verifies accountant cannot use Paystack modes.
- **Added** `test_paystack_blocked_when_school_owned_controls_not_ready` — verifies gate blocks when flag is `False`.

## Impact
- **Zero behavioral change for existing deployments** — `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY` defaults `False`, so automated payouts remain disabled.
- Record-only payroll (cash, bank, cheque, MoMo record) is unaffected.
- All 6 existing tests pass.

---

# Rollout Checklist

## Before deploying to production

- [ ] Run `python manage.py migrate schools 0012` (payout setup fields)
- [ ] Verify backfill: any school with existing `paystack_subaccount_code` should now have `paystack_subaccount_status = "active"`
- [ ] Confirm `PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY` is **not set** or set to `False` in production `.env`
- [ ] Confirm `PAYSTACK_STAFF_TRANSFERS_ENABLED` is `False` in production (unchanged)
- [ ] Run `python manage.py test accounts.tests.StaffPayrollDisburseTests` — all 6 pass

## After deploying

- [ ] Log in as school_admin → School Settings → verify "Payout Setup" card shows correct status
- [ ] For a school with existing subaccount code, verify status shows "active" and fee payment still works
- [ ] For a school without subaccount, verify "Pay Online" buttons are hidden on fee lists
- [ ] Attempt staff payroll → Paystack MoMo mode → verify it's blocked with clear message
- [ ] Attempt staff payroll → offline cash mode → verify it still works
- [ ] Check logs for `school_payout_setup:` entries on any new payout setup attempt

## Production environment variables (no changes required)

```bash
# Already in .env — no action needed:
PAYSTACK_SECRET_KEY=sk_live_...
PAYSTACK_STAFF_TRANSFERS_ENABLED=False     # or absent (defaults False)
# PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY  # absent = False (safe default)
```

---

# .env.example Update

Add the following to the `# --- Payments (Paystack) ---` section:

```env
# Outgoing staff salary transfers via Paystack (debits Paystack merchant balance).
# PAYSTACK_STAFF_TRANSFERS_ENABLED=False

# Safety gate: keep False until school-owned funding controls (ledger, reconciliation,
# maker-checker approval) are fully implemented and validated. When False, automated
# staff payouts are blocked even if PAYSTACK_STAFF_TRANSFERS_ENABLED=True.
# PAYSTACK_STAFF_SCHOOL_OWNED_PAYOUTS_READY=False
```
