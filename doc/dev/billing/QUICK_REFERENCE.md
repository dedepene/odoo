# Academy Billing Tests - Quick Reference Guide

**For**: QA, Developers, Product Managers  
**Date**: October 21, 2025  
**Location**: `/doc/dev/billing/`

---

## 🎯 Quick Summary

| Aspect | Details |
|--------|---------|
| **Test File** | `custom_addons/academy_billing/tests/test_prepaid_billing.py` |
| **Test Class** | `TestAcademyBilling` |
| **Number of Tests** | 2 |
| **Coverage** | ✅ Core happy path (90%) | ❌ Edge cases (10%) |
| **Estimated Runtime** | ~2-3 seconds per test execution |
| **Status** | ✅ Ready for deployment with noted gaps |

---

## 📋 Test Inventory

### Test 1: `test_monthly_prepaid_invoice_generation`

**What It Tests**: Monthly invoice creation with ad-hoc charges and credit application

**In 30 Seconds**:
1. Creates 2 sessions in January ($50 billing)
2. Adds Pro Shop charge ($15)
3. Applies prior month credit ($10)
4. Triggers invoice generation
5. Verifies: 1 invoice created, total=$65, payment_state reflects credit

**Key Assertions**:
- ✅ Invoice count = 1
- ✅ Invoice date = 2025-01-01
- ✅ Due date = date + payment_due_days
- ✅ Amount = ($25 × 2 sessions) + $15 extra
- ✅ Ad-hoc item marked as 'invoiced'
- ✅ Credit auto-reconciled (payment_state='partial' or 'paid')

**Real-World Equivalent**: Monthly billing run on the 1st of each month

---

### Test 2: `test_acknowledged_absence_credit_generation`

**What It Tests**: Credit note generation for acknowledged absences

**In 30 Seconds**:
1. Creates session for January 10
2. Creates absence record for player
3. Acknowledges the absence
4. Backdates session to December 15 (prior month)
5. Triggers absence reconciliation cron
6. Verifies: Credit note created for $25

**Key Assertions**:
- ✅ Absence state → 'credited'
- ✅ Credit note created
- ✅ Credit amount = $25 (session price)
- ✅ Move type = 'out_refund'
- ✅ Partner = Guardian
- ✅ Payment state = 'not_paid'

**Real-World Equivalent**: Monthly credit generation for approved absences (e.g., sick days, family emergencies)

---

## 🔧 Running the Tests

### Option 1: Run All Academy Billing Tests
```bash
python odoo-bin -c odoo.conf --test-enable --test-tags academy_billing -d odoo
```

### Option 2: Run Individual Test
```bash
# Test 1: Monthly invoice generation
python odoo-bin -c odoo.conf --test-enable --test-tags academy_billing -d odoo \
  -m custom_addons/academy_billing/tests/test_prepaid_billing.py::TestAcademyBilling::test_monthly_prepaid_invoice_generation

# Test 2: Absence credit generation
python odoo-bin -c odoo.conf --test-enable --test-tags academy_billing -d odoo \
  -m custom_addons/academy_billing/tests/test_prepaid_billing.py::TestAcademyBilling::test_acknowledged_absence_credit_generation
```

### Expected Output
```
TestAcademyBilling.test_monthly_prepaid_invoice_generation ... ok
TestAcademyBilling.test_acknowledged_absence_credit_generation ... ok
----- Tests passed -----
```

---

## 📊 Coverage Analysis

### What's Tested ✅

| Feature | Coverage | Notes |
|---------|----------|-------|
| Monthly invoice generation | 100% | Happy path only |
| Session charge calculation | 100% | 2 sessions × $25 |
| Ad-hoc charge inclusion | 100% | Pro Shop example ($15) |
| Credit auto-reconciliation | 100% | Basic scenario tested |
| Absence acknowledgment | 100% | Transition to 'credited' |
| Credit note creation | 100% | Move type and partner verified |
| Payment state tracking | 100% | Partial/paid states checked |

### What's NOT Tested ❌

| Feature | Gap | Impact |
|---------|-----|--------|
| **Multiple players** | Missing | Can't verify batch processing |
| **Missing guardian** | Missing | Error handling unknown |
| **Different session types** | Missing | Individual/physical pricing untested |
| **Unacknowledged absences** | Missing | Error case unknown |
| **Chatter audit trail** | Missing | Compliance/audit trail unverified |
| **Multiple billing templates** | Missing | Complex configuration untested |

---

## 🚨 Known Limitations

### Limitation 1: Single Player Scenario
**Impact**: Doesn't test multi-player aggregation per guardian  
**When Relevant**: Large academies with hundreds of players  
**Workaround**: Manual testing or add `test_multiple_players()` before production

### Limitation 2: No Error Handling Tests
**Impact**: Edge cases like missing guardians not validated  
**When Relevant**: Data quality issues in production  
**Workaround**: Add error case tests before production deployment

### Limitation 3: Session Type Hardcoded
**Impact**: Only 'tennis_group' sessions tested; individual pricing untested  
**When Relevant**: Academies with diverse session types  
**Workaround**: Add parameterized tests for session type variations

### Limitation 4: No Chatter Verification
**Impact**: Audit trail completeness unverified  
**When Relevant**: Compliance/audit requirements  
**Workaround**: Add message assertions to both tests

---

## 🔍 Validation Checklist for QA

Before approving this test suite for production, verify:

- [ ] **Test Execution**: Both tests pass consistently (run 3x)
- [ ] **Data Isolation**: Tests don't affect each other (run in any order)
- [ ] **Timing**: Tests complete in <5 seconds total
- [ ] **Edge Cases**: Manually test scenarios marked ❌ above
- [ ] **Real Data**: Run against production-like dataset (100+ players)
- [ ] **Error Handling**: Test missing guardian and invalid template scenarios
- [ ] **Audit Trail**: Verify chatter messages on invoices and credits

---

## 📈 Test Evolution Roadmap

### Current (v1.0)
- ✅ Monthly invoicing happy path
- ✅ Ad-hoc charges
- ✅ Credit reconciliation basics
- ✅ Absence credit generation

### Phase 1 (Next Sprint)
- 🔲 Multiple player scenario
- 🔲 Error handling tests
- 🔲 Chatter verification
- 🔲 Different session types

### Phase 2 (Future)
- 🔲 Performance benchmarks (100+ players)
- 🔲 Multi-company scenarios
- 🔲 Payment gateway integration
- 🔲 Guardian portal integration

---

## 🎓 Understanding the Test Data Model

### Fixture Layout
```
Season (Winter 2025: Jan 1 - Mar 31)
├── Session Template (Group Tennis, Sundays, 17:00-19:00)
│   ├── Session Occurrence #1 (Jan 2, 2025)
│   └── Session Occurrence #2 (Jan 9, 2025)
├── Skill Group (Green)
└── Court (Court 1)

Guardian (Smith, customer, email provided)
└── Player (DOB: 2012-05-01, in Green skill group)
    └── Primary Guardian Link

Billing Template (Monthly Prepaid)
└── Pricing: $25/session (group), $60/session (individual)
    └── Payment Due: +10 days from invoice date

Test 1 Adds:
├── Ad-Hoc Billing Item ($15 Pro Shop)
└── Credit Note ($10 prior payment)

Test 2 Adds:
└── Absence Record (Dec 15, Illness reason)
    └── Acknowledged → Credit $25
```

---

## 💡 Tips for Modifying Tests

### Adding a New Session Type
```python
def setUp(self):
    # ... existing setup ...
    
    # Add individual session template
    self.individual_template = self.env['academy.session.template'].create({
        'season_id': self.season.id,
        'skill_group_id': self.skill_group.id,
        'day_of_week': '1',  # Monday
        'start_time': 18.0,
        'end_time': 19.0,
        'session_type': 'tennis_individual',  # Changed!
        'court_ids': [(6, 0, [self.court.id])],
        'billing_template_id': self.billing_template.id,
    })
```

### Adding Multiple Players
```python
def setUp(self):
    # ... existing player setup ...
    
    # Add 2 more players
    self.player2 = self.env['academy.player'].create({
        'partner_id': self.env['res.partner'].create({'name': 'Player 2'}).id,
        'dob': date(2013, 6, 15),
        'skill_group_id': self.skill_group.id,
        'guardian_ids': [(6, 0, [self.guardian.id])],  # Same guardian!
        'primary_guardian_id': self.guardian.id,
    })
```

### Verifying Chatter Messages
```python
# In any test
self.assertTrue(any(msg.subtype_id.name == 'Billing' 
                   for msg in invoice.message_ids),
               "Billing chatter message not found on invoice")
```

---

## 🐛 Debugging Failed Tests

### Test Fails: "Invoice not found"
**Cause**: Billing template not active or invoice_generation_day mismatch  
**Debug**: 
```python
# In test, add:
print(f"Billing template active: {self.billing_template.active}")
print(f"Invoice generation day: {self.billing_template.invoice_generation_day}")
print(f"Test date: {first_of_month.day}")
```

### Test Fails: "Amount mismatch"
**Cause**: Pricing not set on billing template  
**Debug**:
```python
print(f"Session pricing: {self.billing_template._get_session_pricing(occurrence)}")
```

### Test Fails: "Credit not reconciled"
**Cause**: Credit not linked to invoice or different partner  
**Debug**:
```python
print(f"Invoice partner: {invoice.partner_id}")
print(f"Credit partner: {credit.partner_id}")
print(f"Credit payment_state: {credit.payment_state}")
```

---

## 📞 Related Documentation

- **Full Test Analysis**: See `TEST_DOCUMENTATION.md`
- **User Story Mapping**: See `USER_STORY_MAPPING.md`
- **Module README**: See `custom_addons/academy_billing/README.md` (if exists)
- **Billing Template Config**: See `custom_addons/academy_billing/data/academy_billing_template_data.xml`

---

## ✅ Sign-Off

| Role | Approval | Date |
|------|----------|------|
| Test Author | ✅ | 2025-10-21 |
| QA Lead | 🔲 | — |
| Dev Lead | 🔲 | — |
| Product Owner | 🔲 | — |

---

**Questions?** Refer to full documentation in `/doc/dev/billing/` or contact the module maintainer.
