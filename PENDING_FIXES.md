# Pending Fixes

## Status: ALL ISSUES FIXED ✅

### Issue 1: ID Cards Issue
- **Status**: FIXED
- **Description**: The ID card views now properly handle both students and staff
- **Files Modified**: `schoolms/operations/views.py`

### Issue 2: Parents and Students Payment Portal (Canteen, Textbooks, Transport)
- **Status**: FIXED
- **Description**: Fixed the payment portal views to properly get school from student's record for parents (since parents don't have school assigned directly)
- **Root Cause**: Parents don't have a direct `school` attribute on their user account - the school is inferred from their children (students)
- **Views Fixed**:
  - `canteen_my` - Now gets school from children for parents
  - `bus_my` - Now gets school from children for parents  
  - `textbook_my` - Now gets school from children for parents
- **Files Modified**: `schoolms/operations/views.py`

### Issue 3: "Currency not supported by merchant" Error (Bus, Textbook, Hostel Payments)
- **Status**: FIXED
- **Description**: Fixed the "Currency not supported by merchant" error for bus, textbook, and hostel payments
- **Root Cause**: School fees and canteen payments had the `currency` parameter passed to Paystack's `initialize_payment()` function, but bus, textbook, and hostel payments were missing this parameter
- **Fix Applied**: Added `currency=currency` parameter to all Paystack payment initialize calls in `schoolms/operations/payment_views.py`:
  - Canteen payment - Already had it ✓
  - Bus payment - Added `currency=currency`
  - Textbook payment - Added `currency=currency`  
  - Hostel payment - Added `currency=currency`
- **Currency Source**: Retrieved from Django settings (`PAYSTACK_CURRENCY`, defaulting to 'GHS')
- **Files Modified**: `schoolms/operations/payment_views.py`

### Changes Made

1. **canteen_my** function:
   - Added check at beginning to get school from children for parents
   - Now properly queries `Student.objects.filter(parent=request.user)` for parents
   
2. **bus_my** function:
   - Added same fix as canteen_my
   - Gets school from child for parents
   
3. **textbook_my** function:
   - Added same fix as canteen_my
   - Gets school from child for parents

### How to Test

1. Login as a parent
2. Navigate to:
   - Canteen (My Canteen)
   - Transport (My Bus)
   - Textbooks (My Textbooks)
   - Hostel (My Hostel)
3. Verify that items and payment history are now visible
4. Test making a payment for bus, textbook, or hostel - should no longer show "Currency not supported" error

### Date Fixed
- 2026-04-02 (Issues 1 & 2)
- 2026-04-04 (Issue 3 - Currency Fix)
