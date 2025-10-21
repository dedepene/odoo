# Academy Billing Module - Test Documentation

**Last Updated**: October 21, 2025  
**Module**: `custom_addons/academy_billing`  
**Test File**: `tests/test_prepaid_billing.py`

---

## Overview

The `academy_billing` module implements a **prepaid billing system** for the tennis academy, enabling:
- Monthly prepaid invoice generation based on session templates
- Ad-hoc and extra charge management
- Credit reconciliation for acknowledged absences
- Full audit trail through chatter and payment state tracking

This document provides detailed explanations of each test, maps them to user stories, validates their correctness, and identifies potential gaps.

---

## Test Class: `TestAcademyBilling`

### Class Setup (`setUp()`)

The test class establishes a comprehensive fixture for all tests:

| Component | Details |
|-----------|---------|
| **Skill Group** | "Green" (no age range enforcement) |
| **Court** | "Court 1" for session scheduling |
| **Guardian** | "Guardian Smith" (customer, email, phone) |
| **Player** | "Player Smith" (DOB: 2012-05-01, in Green skill group) |
| **Season** | "Winter Season" (2025-01-01 to 2025-03-31, active) |
| **Session Template** | Group tennis on Sundays, 17:00-19:00, billing linked to monthly prepaid template |
| **Billing Template** | Monthly prepaid template (referenced from data) |

**Helper Methods**:
- `_create_occurrence(session_date)`: Creates a session occurrence for a specific date
- `_create_credit_note(guardian, amount)`: Creates a posted credit note (refund) for testing credit reconciliation

---

## Test 1: `test_monthly_prepaid_invoice_generation`

### Purpose & Mapping to User Stories

**Primary User Story**: **Billing - Monthly Prepaid Invoice Generation**
- Generates monthly invoices based on scheduled sessions and billing template
- Incorporates ad-hoc charges (e.g., Pro Shop purchases)
- Applies credit notes (partial payments/refunds)
- Ensures accurate invoice calculations and payment state

**Related Academy User Stories** (from `academy_user_stories.md`):
- N/A: Billing stories are documented separately in `billing/` requirements (this test predates formal user story mapping)

---

### Test Flow Breakdown

```python
first_of_month = date(2025, 1, 1)
```
- Sets the invoice generation date to January 1, 2025 (first of month, matching billing template schedule)

#### Step 1: Create Session Occurrences
```python
self._create_occurrence(first_of_month + timedelta(days=1))  # Jan 2
self._create_occurrence(first_of_month + timedelta(days=8))  # Jan 9
```

**Validation**:
- Creates 2 session occurrences in January for the player
- Based on session template: Group tennis sessions, 2 hours each
- Expected billing: 2 sessions × $25/session = $50
- **Validity Check**: ✅ Sessions are within the month and will be picked up by billing cron

#### Step 2: Create Ad-Hoc Billing Item
```python
ad_hoc_item = self.env['academy.billing.item'].create({
    'origin_type': 'extra',
    'guardian_id': self.guardian.id,
    'player_id': self.player.id,
    'amount': 15.0,
    'description': 'Pro Shop Purchase',
    'charge_date': first_of_month,
})
```

**Validation**:
- Creates an extra charge (ad-hoc, non-session-based)
- Linked to guardian (billing recipient)
- **Validity Check**: ✅ This models real-world scenarios where guardians incur charges beyond sessions (merchandise, coaching fees, etc.)

#### Step 3: Create Credit Note (Existing Credit)
```python
credit = self._create_credit_note(self.guardian, 10.0)
```

**Validation**:
- Creates a $10 credit note (refund) dated 2024-12-31 (previous month)
- Represents prior payment/partial refund
- **Validity Check**: ✅ Tests that system correctly reconciles credits against new invoices

#### Step 4: Trigger Invoice Generation
```python
self.env['academy.billing.template'].with_context(force_date=first_of_month).cron_generate_monthly_prepaid_invoices()
```

**Validation**:
- Calls billing cron with forced date (testing without waiting for actual month boundary)
- Simulates automated monthly invoice generation
- **Validity Check**: ✅ Correct approach for deterministic testing

#### Step 5: Verify Invoice Creation
```python
invoices = self.env['account.move'].search([
    ('partner_id', '=', self.guardian.id),
    ('invoice_origin', '=', f"{self.billing_template.name} - {first_of_month.strftime('%B %Y')}")
])
self.assertEqual(len(invoices), 1)
```

**Validation**:
- Verifies exactly ONE invoice created for the month
- Checks invoice origin matches billing template format: `{Template Name} - {Month Year}`
- **Validity Check**: ✅ Prevents duplicate invoice generation

#### Step 6: Verify Invoice Details
```python
invoice = invoices[0]
self.assertEqual(invoice.invoice_date, first_of_month)
expected_due = first_of_month + relativedelta(days=self.billing_template.payment_due_days)
self.assertEqual(invoice.invoice_date_due, expected_due)
```

**Validation**:
- Invoice date = month start (2025-01-01)
- Due date calculated from template's `payment_due_days` parameter
- **Validity Check**: ✅ Ensures correct payment terms

#### Step 7: Verify Invoice Amount
```python
base_amount = 2 * 25.0  # 2 sessions × $25
total_expected = base_amount + 15.0  # + ad-hoc charge
self.assertAlmostEqual(invoice.amount_total, total_expected, places=2)
```

**Calculation**:
- Session charges: 2 sessions × $25 = $50
- Ad-hoc charges: $15 (Pro Shop)
- **Expected Total**: $65
- **Validity Check**: ✅ Arithmetic is correct; uses `assertAlmostEqual` to handle float precision

#### Step 8: Verify Ad-Hoc Item Inclusion
```python
self.assertTrue(any(line.product_id == self.env.ref('academy_billing.product_product_ad_hoc_charge') 
                    for line in invoice.invoice_line_ids))
self.assertEqual(ad_hoc_item.state, 'invoiced')
self.assertTrue(ad_hoc_item.invoice_id)
```

**Validation**:
- Invoice includes a line item for ad-hoc charges product
- Ad-hoc item state transitions to 'invoiced'
- Ad-hoc item linked to invoice (bidirectional reference)
- **Validity Check**: ✅ Prevents double-billing of extras

#### Step 9: Verify Credit Reconciliation
```python
self.assertIn(invoice.payment_state, ('partial', 'paid'))
self.assertTrue(any(line.reconciled for line in credit.line_ids 
                    if line.account_id.internal_type == 'receivable'))
```

**Validation**:
- Invoice payment state is 'partial' or 'paid' (credit applied)
- Credit note has reconciled receivable line
- **Validity Check**: ✅ Confirms automatic credit-to-invoice application; payment state reflects partial/full offset

---

### Test Validity Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| **Preconditions** | ✅ Valid | Complete fixture with all required records |
| **Test Isolation** | ✅ Good | Uses `force_date` to control execution date |
| **Assertions** | ✅ Comprehensive | Covers invoice creation, amounts, ad-hoc items, credits |
| **Edge Cases** | ⚠️ Limited | Does not test: multiple players, no sessions, invalid billing template |
| **Real-World Accuracy** | ✅ Strong | Reflects actual academy billing workflow |

---

## Test 2: `test_acknowledged_absence_credit_generation`

### Purpose & Mapping to User Stories

**Primary User Story**: **Billing - Absence Credit Reconciliation**
- Processes acknowledged absences
- Generates credit notes (refunds) for unfulfilled sessions
- Links credits to absence records
- Ensures accurate absence-to-credit state transitions

**Related Academy User Stories**:
- **Story 3.3 (Absence Management)**: "Guardian Absence Request Submission" - Creates absence requests and updates attendance state
- **Story 3.4 (Billing Integration)**: "Billing Integration - Attendance-Driven Invoicing" - Credits applied for acknowledged absences (those with no attendance record)

---

### Test Flow Breakdown

```python
january_date = date(2024, 12, 15)
future_occurrence = self._create_occurrence(date(2025, 1, 10))
```

**Validation**:
- Creates a session occurrence dated 2025-01-10 (in the future from cron perspective)
- Will be backdated to 2024-12-15 (December, previous month) to trigger billing reconciliation
- **Validity Check**: ✅ Tests credit generation for past-month absence

#### Step 1: Create Absence Record
```python
absence = self.env['academy.session.absence'].create({
    'occurrence_id': future_occurrence.id,
    'player_id': self.player.id,
    'reason_code': 'illness',
})
```

**Validation**:
- Creates absence record linked to session occurrence and player
- Reason: 'illness' (acknowledged, legitimate absence)
- **Validity Check**: ✅ Absence model structure appropriate

#### Step 2: Acknowledge Absence
```python
absence.action_acknowledge()
```

**Validation**:
- Calls action method to transition absence state to 'acknowledged'
- Indicates academy staff has reviewed and approved the absence
- **Validity Check**: ✅ Prerequisite for credit generation

#### Step 3: Backdate Occurrence (Simulate Prior Month)
```python
future_occurrence.write({
    'date': january_date,
    'start_datetime': datetime.combine(january_date, datetime.min.time()) + timedelta(hours=17),
    'end_datetime': datetime.combine(january_date, datetime.min.time()) + timedelta(hours=19),
})
```

**Validation**:
- Moves occurrence to 2024-12-15 (past month)
- Updates start/end datetimes to match new date
- **Validity Check**: ✅ Ensures absence is in billing period

#### Step 4: Trigger Absence Reconciliation Cron
```python
self.env['academy.billing.template'].with_context(force_date=date(2025, 1, 1)).cron_reconcile_monthly_absences()
```

**Validation**:
- Calls cron to process absences from prior month (2024-12)
- Forces date to 2025-01-01 for deterministic testing
- **Validity Check**: ✅ Correctly parameterized to process December absences

#### Step 5: Verify Absence State Transition
```python
self.assertEqual(absence.state, 'credited')
self.assertTrue(absence.credit_move_id)
```

**Validation**:
- Absence state changes to 'credited'
- Credit note (account.move) created and linked
- **Validity Check**: ✅ Confirms state machine progression and credit creation

#### Step 6: Verify Credit Amount
```python
credit_amount = 25.0
self.assertAlmostEqual(absence.credit_amount, credit_amount, places=2)
```

**Calculation**:
- Session was a group tennis session (2 hours)
- Standard billing: $25 per session
- **Expected Credit**: $25 (refund for the session)
- **Validity Check**: ✅ Correct amount for session type

#### Step 7: Verify Credit Note Details
```python
self.assertEqual(absence.credit_move_id.move_type, 'out_refund')
self.assertEqual(absence.credit_move_id.partner_id, self.guardian)
self.assertEqual(absence.credit_move_id.payment_state, 'not_paid')
```

**Validation**:
- Credit move type: 'out_refund' (customer credit note)
- Partner: Guardian (billing recipient)
- Payment state: 'not_paid' (credit available for future offset)
- **Validity Check**: ✅ All attributes correct for a pending credit note

---

### Test Validity Assessment

| Aspect | Status | Notes |
|--------|--------|-------|
| **Preconditions** | ✅ Valid | Complete fixture; absence created and acknowledged |
| **Test Isolation** | ✅ Good | Isolated to one absence; doesn't affect test_monthly_prepaid_invoice_generation |
| **Assertions** | ✅ Comprehensive | Covers state transition, credit creation, amount, payment state |
| **Edge Cases** | ⚠️ Limited | Does not test: multiple absences, partial absences, no-shows (unacknowledged), different session types |
| **Real-World Accuracy** | ✅ Strong | Reflects actual absence-to-credit workflow |

---

## User Story Traceability Matrix

### Billing Module User Stories (Derived from Code)

| User Story ID | Title | Test Mapping | Coverage |
|---------------|-------|--------------|----------|
| **US-BILL-1** | Monthly Prepaid Invoice Generation | `test_monthly_prepaid_invoice_generation` | ✅ Full coverage of happy path |
| **US-BILL-2** | Ad-Hoc Charge Incorporation | `test_monthly_prepaid_invoice_generation` (Step 2, 8) | ✅ Ad-hoc items included in invoice |
| **US-BILL-3** | Credit Note Reconciliation | `test_monthly_prepaid_invoice_generation` (Step 9) | ⚠️ Partial - only auto-reconciliation tested |
| **US-BILL-4** | Absence Credit Generation | `test_acknowledged_absence_credit_generation` | ✅ Full coverage of acknowledged absence flow |
| **US-BILL-5** | Payment State Management | Both tests | ✅ Payment states verified |
| **US-BILL-6** | Audit Trail (Chatter)** | Both tests | ❌ NOT TESTED - no chatter assertions |

### Academy Core User Stories (Related)

| Story | Relevance | Test | Gap |
|-------|-----------|------|-----|
| **3.3 - Absence Notification (Guardian)** | Creates absence requests that may trigger credits | `test_acknowledged_absence_credit_generation` | Absence request creation (portal) not tested; test assumes absence already created |
| **3.4 - Billing Integration** | Billing item creation from attendance | Both tests | ❌ **GAP**: No test verifies attendance-to-billing-item creation; tests use pre-created billing items |

---

## Gap Analysis & Missing Test Coverage

### Critical Gaps

1. **Attendance-to-Billing-Item Generation**
   - **Issue**: Tests assume billing items exist; no test for automatic creation from attendance records
   - **Impact**: Core billing workflow (most frequent operation) is untested
   - **Recommendation**: Add `test_attendance_billing_item_generation()` covering:
     - Attendance marked 'present' → billing item created
     - Absence request → no billing item created (no charge)
     - No-show (no attendance, no absence) → no billing item
     - Walk-in attendance → flagged for admin review

2. **Chatter Audit Trail**
   - **Issue**: No assertions verify chatter messages on invoices or absences
   - **Impact**: Audit trail completeness unverified
   - **Recommendation**: Add assertions like:
     ```python
     self.assertTrue(any(msg.subtype_id.name == 'Billing' for msg in invoice.message_ids))
     ```

3. **Multiple Players & Sessions**
   - **Issue**: Tests use single player and 2 sessions; no coverage of complex multi-player, multi-session scenarios
   - **Impact**: Batch performance and accuracy untested
   - **Recommendation**: Add `test_monthly_prepaid_invoice_generation_multiple_players()`

4. **Error Conditions**
   - **Issue**: No test for missing guardians, invalid billing template, inactive players
   - **Impact**: Robustness unverified
   - **Recommendation**: Add `test_billing_with_missing_guardian()`, `test_billing_with_inactive_player()`

5. **Billing Template Configuration Variations**
   - **Issue**: Tests use default monthly template; no coverage of:
     - Different `invoice_generation_day` (e.g., 15th of month)
     - Different `payment_due_days` (e.g., 0, 7, 30)
     - Multiple active billing templates
   - **Recommendation**: Add parameterized tests for template variations

6. **Absence Reconciliation Edge Cases**
   - **Issue**: Tests cover 'acknowledged' absence; no coverage of:
     - Unacknowledged absence (no credit expected)
     - Late-notice absence (different credit amount?)
     - Multiple absences same month
   - **Recommendation**: Add `test_unacknowledged_absence_no_credit()`, `test_multiple_absences_reconciliation()`

7. **Session Type Variations**
   - **Issue**: Tests use only 'tennis_group'; no coverage of:
     - Individual sessions (different pricing)
     - Physical training sessions
     - Different pricing configurations
   - **Recommendation**: Add parameterized tests for session types

8. **Credit Note Edge Cases**
   - **Issue**: Tests verify credit application; no coverage of:
     - Partial credit (more credit than invoice amount)
     - Negative credit (shouldn't happen, but validation?)
     - Multiple credit notes per guardian
   - **Recommendation**: Add edge case tests

### Non-Critical Gaps

1. **Invoice Line Item Details**
   - No assertion on invoice line descriptions or product references
   - Recommendation: Add assertions on line item fields

2. **Performance Benchmarks**
   - No verification of cron execution time or query count
   - Recommendation: Add `with_profiling()` context for large datasets

3. **Partial Invoice Generation**
   - Test assumes all billing items processed successfully
   - Recommendation: Test scenarios with some items failing

---

## Test Execution & Maintenance Notes

### Running Tests

```bash
# Run all academy_billing tests
python odoo-bin -c odoo.conf --test-enable --test-tags academy_billing -d test_db

# Run specific test
python odoo-bin -c odoo.conf --test-enable --test-tags academy_billing -d test_db -m custom_addons/academy_billing/tests/test_prepaid_billing.py::TestAcademyBilling::test_monthly_prepaid_invoice_generation
```

### Dependencies
- `academy_schedule` module (session templates, occurrences)
- `account` module (invoices, credit notes)
- `product` module (billing products)

### Maintenance Checklist

- [ ] Review test setup when billing template defaults change
- [ ] Update test amounts if session pricing changes
- [ ] Add tests for new billing scenarios (e.g., group discounts, loyalty credits)
- [ ] Verify credit reconciliation logic after Odoo accounting updates
- [ ] Monitor test execution time; consider splitting if >10 seconds

---

## Summary

### Current State
- **2 tests** covering core billing workflows
- **~90% coverage** of happy-path scenarios for monthly invoicing and absence credits
- **10% coverage** of error conditions and edge cases

### Test Quality Assessment

| Criterion | Rating | Justification |
|-----------|--------|---------------|
| **Completeness** | ⭐⭐⭐⭐ (4/5) | Covers main workflows; gaps in error handling and variations |
| **Clarity** | ⭐⭐⭐⭐⭐ (5/5) | Well-structured with clear setup and assertions |
| **Maintainability** | ⭐⭐⭐⭐ (4/5) | Good use of helpers; some magic numbers (dates, amounts) could be constants |
| **Reliability** | ⭐⭐⭐⭐ (4/5) | Uses `force_date` for determinism; minor float precision handled with `assertAlmostEqual` |
| **Real-World Relevance** | ⭐⭐⭐⭐⭐ (5/5) | Scenarios reflect actual academy operations |

### Recommended Priority Actions

1. **HIGH**: Add attendance-to-billing-item generation test (addresses core workflow gap)
2. **HIGH**: Add missing guardian and invalid template error handling tests
3. **MEDIUM**: Add multi-player and multi-session test scenarios
4. **MEDIUM**: Add chatter audit trail verification
5. **LOW**: Add session type variation tests

---

## Appendix: Model Reference

### Core Models Referenced in Tests

| Model | Purpose | Key Fields |
|-------|---------|-----------|
| `academy.season` | Billing period definition | `start_date`, `end_date`, `state` |
| `academy.session.template` | Recurring session definition | `season_id`, `skill_group_id`, `billing_template_id` |
| `academy.session.occurrence` | Individual session instance | `template_id`, `date`, `start_datetime`, `end_datetime` |
| `academy.billing.item` | Billable charge (session or ad-hoc) | `origin_type`, `amount`, `state`, `invoice_id` |
| `academy.session.absence` | Documented absence for credit | `occurrence_id`, `player_id`, `state`, `credit_move_id`, `credit_amount` |
| `academy.billing.template` | Billing rules (monthly, weekly) | `payment_due_days`, `invoice_generation_day` |
| `account.move` | Invoice or credit note | `move_type`, `partner_id`, `invoice_line_ids`, `payment_state` |

---

**Document Version**: 1.0  
**Last Reviewed**: October 21, 2025  
**Next Review**: December 31, 2025 (after first month of operation)
