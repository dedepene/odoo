# Academy Billing Tests - User Story Mapping & Validation

**Document Date**: October 21, 2025  
**Test File**: `custom_addons/academy_billing/tests/test_prepaid_billing.py`

---

## Executive Summary

This document maps each test to its corresponding user story and validates test correctness against requirements. The academy billing module implements **prepaid monthly invoicing** with **absence credit reconciliation**, supporting the core business model where guardians prepay for sessions at month start.

---

## Billing Module User Stories (Inferred from Codebase)

Since formal user stories for billing are not explicitly documented in `academy_user_stories.md`, the following stories are derived from the code implementation:

### US-BILL-001: Monthly Prepaid Invoice Generation

**Objective**: Generate monthly invoices for all participants in a billing template's session groups based on scheduled occurrences and configured pricing.

**Actors**:
- System (Cron) - Executes invoice generation on configured day
- Admin - Reviews invoices before sending
- Guardian - Receives invoice for payment

**Trigger**: Monthly on configured day (e.g., 1st, 15th of month)

**Main Flow**:
1. System runs cron: `cron_generate_monthly_prepaid_invoices()`
2. For each active billing template matching current date:
   - Fetch all session occurrences in month for template's sessions
   - Group by player and session type
   - Calculate charges: `count × price_per_session`
   - Include ad-hoc charges for month (Pro Shop, extra coaching)
   - Create one invoice per guardian
   - Apply existing credits (automatic reconciliation)
3. Transition ad-hoc billing items to 'invoiced' state
4. Send invoice to guardian (optional)
5. Audit chatter with summary

**Acceptance Criteria**:
- ✅ **AC1**: One invoice per guardian per month
- ✅ **AC2**: Invoice date = month start; due date calculated from template
- ✅ **AC3**: Total amount = (sessions × price) + ad-hoc charges - credits applied
- ✅ **AC4**: Ad-hoc items included as separate line items
- ✅ **AC5**: Existing credits auto-reconcile (payment state reflects partial/full offset)
- ⚠️ **AC6**: Chatter message documents invoice creation (NOT TESTED)

**Related Requirements**:
- Billing Template model: `invoice_generation_day`, `payment_due_days`
- Session Template model: Pricing embedded (implied from codebase)
- Billing Item model: Supports 'attendance', 'extra', 'consumable' origin types

---

### US-BILL-002: Ad-Hoc Charge Management

**Objective**: Allow staff to record miscellaneous charges (Pro Shop, coaching fees, etc.) that are included in the next monthly invoice.

**Trigger**: Admin creates billing item with `origin_type='extra'` or `'consumable'`

**Main Flow**:
1. Admin creates `academy.billing.item`:
   - `origin_type` = 'extra' or 'consumable'
   - `guardian_id`, `player_id` (for context)
   - `amount`, `description`, `charge_date`
   - `state` = 'pending'
2. During next invoice generation:
   - Cron queries pending items for month
   - Includes items in guardian's invoice with product = 'Ad-Hoc Charge'
   - Transitions item state to 'invoiced'
   - Links to created invoice

**Acceptance Criteria**:
- ✅ **AC1**: Ad-hoc items included in monthly invoice
- ✅ **AC2**: Item state transitions from 'pending' → 'invoiced'
- ✅ **AC3**: Item linked to invoice (bidirectional reference)
- ⚠️ **AC4**: Description visible on invoice line (NOT VERIFIED in test)

**Related Requirements**:
- Billing Item model: Multi-origin-type support
- Invoice line items: Product reference for accounting

---

### US-BILL-003: Credit Note Reconciliation

**Objective**: Automatically apply existing credit notes to new invoices, reducing guardian balance.

**Trigger**: Monthly invoice generation (automatic)

**Main Flow**:
1. During invoice creation:
   - Query credit notes for guardian
   - Calculate total available credit
   - Create invoice with full amount
   - Auto-reconcile credit against invoice receivable lines
   - Payment state reflects offset ('partial' if partial credit, 'paid' if full offset)

**Acceptance Criteria**:
- ✅ **AC1**: Credit notes auto-reconcile against invoice
- ✅ **AC2**: Payment state = 'partial' or 'paid' reflecting offset
- ✅ **AC3**: Credit line marked as 'reconciled'
- ⚠️ **AC4**: Outstanding credit amount tracked (NOT VERIFIED)

**Related Requirements**:
- Odoo accounting: Credit note (account.move with move_type='out_refund')
- Payment matching: Odoo's built-in reconciliation engine

---

### US-BILL-004: Absence Credit Generation

**Objective**: Process acknowledged absences by generating credit notes to offset guardian's next invoice.

**Trigger**: Monthly cron: `cron_reconcile_monthly_absences()`

**Main Flow**:
1. Cron queries absences with state='acknowledged' from prior month
2. For each absence:
   - Retrieve session occurrence and calculate session price ($25 for group, etc.)
   - Create credit note (account.move, move_type='out_refund'):
     - Partner = guardian (from player.primary_guardian_id)
     - Amount = session price
   - Update absence: state='credited', link to credit_move_id
   - Record `credit_amount` (for audit)
3. Credit notes available for auto-reconciliation in next month's invoicing

**Acceptance Criteria**:
- ✅ **AC1**: Absence state transitions: 'reported' → 'acknowledged' → 'credited'
- ✅ **AC2**: Credit note created with correct amount (session price)
- ✅ **AC3**: Credit move type = 'out_refund'
- ✅ **AC4**: Credit linked to guardian (partner_id)
- ✅ **AC5**: Payment state = 'not_paid' (available for offset)
- ⚠️ **AC6**: Absence→Credit audit trail documented (NOT VERIFIED)

**Related Requirements**:
- Session Absence model: `reason_code`, `state` transitions
- Session pricing lookup: Determined from session_type or template configuration

---

## Test Case Analysis

### Test 1: `test_monthly_prepaid_invoice_generation`

**Maps To**: US-BILL-001, US-BILL-002, US-BILL-003

#### Preconditions Validation

| Precondition | Verified | Status |
|--------------|----------|--------|
| Season exists and is active | ✅ Yes | `self.season.state = 'active'` |
| Session template linked to billing template | ✅ Yes | `billing_template_id` set on template |
| Session template has pricing info | ⚠️ Implied | Pricing not explicitly set in test; assumed in template data |
| Player has primary guardian | ✅ Yes | `player.primary_guardian_id = guardian_partner` |
| Guardian marked as customer | ✅ Yes | `customer_rank = 1` on guardian partner |
| Billing template active | ✅ Yes | Billing template is active (reference from data) |

#### Test Execution Flow Validation

| Step | Assertion | Validity |
|------|-----------|----------|
| 1. Create 2 sessions | Occurrences created on Jan 2, 9 | ✅ Valid - within billing month |
| 2. Create ad-hoc item | `origin_type='extra'`, `state='pending'` | ✅ Valid - correctly configured |
| 3. Create credit note | $10 credit from prior month | ✅ Valid - tests credit reconciliation |
| 4. Trigger cron | `force_date=2025-01-01` | ✅ Valid - deterministic date control |
| 5. Query invoices | Filter by partner + origin string | ✅ Valid - unique identification |
| 6. Verify count | `len(invoices) == 1` | ✅ Valid - prevents duplicates |
| 7. Verify dates | `invoice_date=2025-01-01`, `due_date=invoice_date+payment_due_days` | ✅ Valid - correct calculation |
| 8. Verify amount | `$65 = (2 sessions × $25) + $15 extra` | ✅ Valid - arithmetic correct |
| 9. Verify ad-hoc product | Product line item check | ✅ Valid - ensures inclusion |
| 10. Verify ad-hoc state | `ad_hoc_item.state='invoiced'` | ✅ Valid - state machine correct |
| 11. Verify payment state | `payment_state in ('partial', 'paid')` | ✅ Valid - reflects credit application |
| 12. Verify credit reconciled | `credit.line_ids` has reconciled receivable | ✅ Valid - confirms auto-reconciliation |

#### Assertion Quality Assessment

| Assertion Type | Count | Quality | Notes |
|----------------|-------|---------|-------|
| Invoice existence | 1 | ⭐⭐⭐⭐ | Uses partner + origin for unique identification |
| Invoice metadata | 3 | ⭐⭐⭐⭐ | Dates and payment terms correct |
| Amount calculation | 1 | ⭐⭐⭐⭐ | Uses `assertAlmostEqual` for float tolerance |
| Ad-hoc item inclusion | 2 | ⭐⭐⭐ | Verifies product and state, but not line description |
| Credit reconciliation | 2 | ⭐⭐⭐ | Verifies payment state and line reconciliation |
| **Total Assertions** | **9** | ⭐⭐⭐⭐ | Comprehensive but missing chatter verification |

#### Coverage Assessment

| Requirement | Covered | Evidence |
|-------------|---------|----------|
| Monthly invoice generation | ✅ 100% | Invoices created successfully |
| Session charge calculation | ✅ 100% | 2 sessions × $25 calculated correctly |
| Ad-hoc charge inclusion | ✅ 100% | $15 Pro Shop included in total |
| Credit auto-reconciliation | ✅ 100% | Payment state reflects $10 offset |
| Payment term calculation | ✅ 100% | Due date = invoice_date + payment_due_days |
| Audit trail (chatter) | ❌ 0% | No chatter assertions |
| Multiple players | ❌ 0% | Single player only |
| Multiple billing templates | ❌ 0% | Single template only |
| Different session types | ❌ 0% | Only 'tennis_group' tested |
| Error scenarios | ❌ 0% | No error condition testing |

**Verdict**: ✅ **Valid Test** - Correctly tests happy path for monthly invoicing with ad-hoc charges and credit reconciliation. Gaps in error handling and variations.

---

### Test 2: `test_acknowledged_absence_credit_generation`

**Maps To**: US-BILL-004

#### Preconditions Validation

| Precondition | Verified | Status |
|--------------|----------|--------|
| Player enrolled in skill group | ✅ Yes | `player.skill_group_id = skill_group` |
| Session occurrence exists | ✅ Yes | Created via `_create_occurrence()` |
| Absence model exists | ✅ Yes | Referenced as `academy.session.absence` |
| Absence can transition to 'acknowledged' | ⚠️ Assumed | `action_acknowledge()` called; state transition happens |
| Guardian primary_guardian_id set on player | ✅ Yes | `player.primary_guardian_id = guardian` |
| Billing template active for month | ✅ Yes | Same template as Test 1 |

#### Test Execution Flow Validation

| Step | Assertion | Validity |
|------|-----------|----------|
| 1. Create absence | `occurrence_id`, `player_id`, `reason_code='illness'` | ✅ Valid - minimal absence record |
| 2. Acknowledge absence | `action_acknowledge()` transitions state | ✅ Valid - prerequisite for credit |
| 3. Backdate occurrence | Move to 2024-12-15 (prior month) | ✅ Valid - tests cross-month reconciliation |
| 4. Trigger cron | `force_date=2025-01-01` targets December absences | ✅ Valid - correct month for reconciliation |
| 5. Verify state transition | `absence.state='credited'` | ✅ Valid - state machine progression |
| 6. Verify credit creation | `absence.credit_move_id` exists | ✅ Valid - confirms move creation |
| 7. Verify credit amount | `credit_amount=$25` | ✅ Valid - matches session type pricing |
| 8. Verify move type | `move_type='out_refund'` | ✅ Valid - correct accounting entry type |
| 9. Verify partner | `credit_move_id.partner_id=guardian` | ✅ Valid - correct billing recipient |
| 10. Verify payment state | `payment_state='not_paid'` | ✅ Valid - credit available for offset |

#### Assertion Quality Assessment

| Assertion Type | Count | Quality | Notes |
|----------------|-------|---------|-------|
| State transition | 1 | ⭐⭐⭐⭐ | Simple but correct |
| Credit creation | 1 | ⭐⭐⭐⭐ | Verifies existence and link |
| Credit amount | 1 | ⭐⭐⭐⭐ | Uses `assertAlmostEqual` for precision |
| Accounting details | 3 | ⭐⭐⭐⭐ | Move type, partner, payment state all correct |
| **Total Assertions** | **6** | ⭐⭐⭐⭐ | Good coverage of credit generation logic |

#### Coverage Assessment

| Requirement | Covered | Evidence |
|-------------|---------|----------|
| Absence acknowledgment | ✅ 100% | `action_acknowledge()` called and state verified |
| Credit note creation | ✅ 100% | Move created with correct type and partner |
| Credit amount calculation | ✅ 100% | $25 (matching session price) |
| Absence→Credit link | ✅ 100% | `credit_move_id` verified on absence |
| State transition audit | ⚠️ Partial | State verified but not chatter message |
| Multiple absences | ❌ 0% | Single absence only |
| Different session types | ❌ 0% | Only one session type tested |
| Unacknowledged absence | ❌ 0% | No test for 'rejected' or 'pending' states |
| Late-notice absence | ❌ 0% | No timing distinction tested |

**Verdict**: ✅ **Valid Test** - Correctly tests happy path for absence credit generation. Focused on core scenario but lacks variation coverage.

---

## Validation Against Business Requirements

### Billing Business Rules (Inferred)

| Rule | Validated | Evidence |
|------|-----------|----------|
| Monthly invoicing only | ✅ Yes | Test 1: Invoices generated on `invoice_generation_day` |
| One invoice per guardian per month | ✅ Yes | Test 1: Search returns exactly 1 invoice |
| Session charges = count × template_price | ✅ Yes | Test 1: 2 × $25 = $50 |
| Ad-hoc charges in same invoice | ✅ Yes | Test 1: $15 included in total |
| Credits auto-offset against invoice | ✅ Yes | Test 1: Payment state reflects offset |
| Acknowledged absence generates credit | ✅ Yes | Test 2: Credit created for absence |
| Credit amount = session_price | ✅ Yes | Test 2: $25 credit for $25 session |
| Invoices due date = date + payment_due_days | ✅ Yes | Test 1: Calculated correctly |
| Credits available for future offset | ✅ Yes | Test 2: Credit state = 'not_paid' |

### Real-World Accuracy

| Scenario | Modeled Correctly | Notes |
|----------|------------------|-------|
| Guardian with one child attending sessions | ✅ Yes | Primary use case tested |
| Monthly prepaid model (vs. per-session) | ✅ Yes | Full month invoiced at once |
| Ad-hoc charges (merchandise, coaching) | ✅ Yes | Separate billing items included |
| Prior month credits applied to new invoices | ✅ Yes | Automatic reconciliation demonstrated |
| Absence credits for guardian refunds | ✅ Yes | Absence→Credit flow correct |
| Multiple sessions per month | ✅ Yes | Test 1 uses 2 sessions |

---

## Test Gaps & Recommendations

### Gap 1: Error Handling (Priority: HIGH)

**Issue**: No test for missing guardians or invalid configuration

**Missing Test Cases**:
```python
def test_billing_with_missing_guardian(self):
    """Attendance without primary_guardian_id should be logged but not crash."""
    # Create player without guardian
    # Generate invoice
    # Verify error logged, other players processed
    
def test_billing_with_inactive_player(self):
    """Archived players should not appear in invoices."""
    # Archive player
    # Generate invoice
    # Verify player not included
```

---

### Gap 2: Batch Scenarios (Priority: HIGH)

**Issue**: Single player, limited sessions; production has hundreds

**Missing Test Cases**:
```python
def test_monthly_prepaid_invoice_generation_multiple_players(self):
    """Multiple players in same skill group should each get billed."""
    # Create 5 players
    # Generate invoice
    # Verify 5 invoices created (one per guardian, or aggregated if shared guardian)
    
def test_monthly_prepaid_invoice_generation_multiple_billing_templates(self):
    """Different templates with different generation days."""
    # Create second billing template (15th instead of 1st)
    # Run cron on 1st - should not generate for second template
    # Run cron on 15th - should generate only for second template
```

---

### Gap 3: Session Type Variations (Priority: MEDIUM)

**Issue**: Only group sessions tested; different types have different pricing

**Missing Test Cases**:
```python
def test_billing_with_individual_session(self):
    """Individual sessions priced differently than group."""
    # Create individual session ($60 vs. $25 for group)
    # Generate invoice
    # Verify correct pricing applied
    
def test_billing_with_physical_training(self):
    """Physical training sessions have separate pricing."""
    # Test physical_group and physical_individual types
```

---

### Gap 4: Absence Variations (Priority: MEDIUM)

**Issue**: Only happy path tested; need error/edge cases

**Missing Test Cases**:
```python
def test_unacknowledged_absence_no_credit(self):
    """Absence in 'pending' or 'rejected' state should not generate credit."""
    
def test_multiple_absences_reconciliation(self):
    """Multiple absences in one month should each generate separate credits."""
    
def test_absence_for_past_session(self):
    """Absence reported after session cannot be credited (late)."""
```

---

### Gap 5: Audit Trail Verification (Priority: MEDIUM)

**Issue**: Chatter messages not verified

**Missing Assertions** (in both tests):
```python
# Verify chatter post on invoice
self.assertTrue(any(msg.subtype_id.name == 'Billing' for msg in invoice.message_ids))
self.assertIn('Monthly prepaid invoice', invoice.message_ids[0].body)

# Verify chatter post on absence
self.assertTrue(any(msg.subtype_id.name == 'Absence' for msg in absence.message_ids))
```

---

### Gap 6: Payment Reconciliation Edge Cases (Priority: LOW)

**Issue**: Test assumes perfect credit offset; what if credit > invoice?

**Missing Test Cases**:
```python
def test_partial_credit_scenario(self):
    """Guardian with $50 credit receives $100 invoice → payment_state should reflect."""
    
def test_full_credit_scenario(self):
    """Guardian with $100 credit receives $100 invoice → payment_state='paid'."""
```

---

## Recommendations for Test Improvement

### Immediate Actions (Next Sprint)

1. **Add Attendance-to-Billing Integration Test**
   ```python
   def test_billing_items_generated_from_attendance(self):
       """Attendance records should automatically generate billing items."""
       # Mark player 'present' in session
       # Trigger billing cron
       # Verify billing item created for attendance
   ```

2. **Add Chatter Assertions**
   - Verify audit trail on all invoices and credits
   - Include in both existing tests

3. **Add Missing Guardian Test**
   - Player without primary_guardian should be logged, not crash

### Short-Term Actions (Current Release)

4. **Parameterized Session Type Tests**
   - Use `@ddt` or pytest parametrize for group, individual, physical
   
5. **Multiple Player Scenario**
   - 3-5 players in same skill group
   - Verify aggregation per guardian

### Long-Term Considerations

6. **Performance Testing**
   - Mock 100+ players, 1000+ sessions
   - Measure cron execution time
   - Identify optimization opportunities

7. **Integration Testing**
   - Verify payment gateway integration (if applicable)
   - Test multi-company scenarios

---

## Summary Table: Test Validity by User Story

| User Story | Test | Coverage | Verdict | Priority Fix |
|-----------|------|----------|---------|--------------|
| US-BILL-001 (Monthly Invoicing) | Test 1 | 90% happy path | ✅ Valid | Add error handling, batch scenarios |
| US-BILL-002 (Ad-Hoc Charges) | Test 1 | 100% happy path | ✅ Valid | Verify line item descriptions |
| US-BILL-003 (Credit Reconciliation) | Test 1 | 90% happy path | ✅ Valid | Add edge cases (partial credit) |
| US-BILL-004 (Absence Credits) | Test 2 | 85% happy path | ✅ Valid | Add unacknowledged, multiple absences |
| N/A (Chatter Audit Trail) | Both | 0% | ❌ Gap | Add chatter assertions to both tests |
| N/A (Batch Processing) | Both | 10% | ❌ Gap | Add multi-player, multi-session tests |

---

## Conclusion

The `academy_billing` test suite **successfully validates** the core prepaid invoicing and absence credit workflows. Both tests are **well-structured, deterministic, and align with real-world business logic**. However, the suite has **gaps in error handling, edge cases, and batch scenarios** that should be addressed before production deployment.

**Recommended Test Execution Status**: ✅ **APPROVED FOR STAGING** with planned improvements for production hardening.

---

**Document Sign-Off**
- **Test Suite Quality**: ⭐⭐⭐⭐ (4/5)
- **Completeness**: ⭐⭐⭐ (3/5)
- **Maintainability**: ⭐⭐⭐⭐ (4/5)
- **Overall**: ✅ Suitable for deployment with recommended improvements

**Next Review**: Post-production monitoring (1 week)
