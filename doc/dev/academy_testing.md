# Academy Testing Guide

## Overview

Testing in Odoo uses the `unittest` framework with Odoo-specific extensions. The academy modules follow Odoo testing best practices with comprehensive test coverage for models, constraints, workflows, and integrations.

## Test Framework

### Base Test Classes

**`odoo.tests.TransactionCase`** - Most common base class:
- Each test method runs in a transaction that is rolled back after the test
- Database state is preserved between tests in the same class
- Fast execution (no database commits)
- Use for model tests, constraint validation, business logic

**`odoo.tests.HttpCase`** - For testing HTTP endpoints:
- Full HTTP client simulation
- Use for portal controller tests
- Browser automation support
- Slower than TransactionCase (requires full server)

**`odoo.tests.SingleTransactionCase`** - For module-wide setup:
- Single transaction for entire test class
- Faster when many tests share expensive setup
- Use when test data creation is slow

### Test Decorators

**`@tagged('academy_core')`** - Module tags for selective test execution:
```python
from odoo.tests import TransactionCase, tagged

@tagged('academy_core')
class TestAcademyPlayer(TransactionCase):
    """Tests for academy.player model."""
```

**Other useful tags**:
- `@tagged('post_install', '-at_install')` - Run only after module installation
- `@tagged('-standard')` - Exclude from standard test suite
- `@tagged('slow')` - Mark slow-running tests

## Running Tests

### Run All Tests for a Module

```bash
# Run all academy_core tests
python odoo-bin -c odoo.conf --test-enable --test-tags /academy_core -d odoo --stop-after-init

# Run all academy_schedule tests
python odoo-bin -c odoo.conf --test-enable --test-tags /academy_schedule -d odoo --stop-after-init

# Run all academy_billing tests
python odoo-bin -c odoo.conf --test-enable --test-tags /academy_billing -d odoo --stop-after-init
```

### Run Specific Test Classes

```bash
# Run specific test class
python odoo-bin -c odoo.conf --test-enable --test-tags /academy_core:TestAcademyPlayerConstraints -d odoo --stop-after-init
```

### Run All Academy Tests

```bash
# Run all tests for all academy modules
python odoo-bin -c odoo.conf --test-enable --test-tags /academy_core,/academy_schedule,/academy_billing -d odoo --stop-after-init
```

### Run Tests Without `--stop-after-init`

```bash
# Useful for development - keeps server running after tests
python odoo-bin -c odoo.conf --test-enable --test-tags /academy_core -d odoo
```

## Test Structure

### Test Organization

Each module has a `tests/` directory:

```
academy_core/tests/
├── __init__.py                    # Import all test modules
├── test_player_constraints.py    # Player model constraint tests
├── test_coach_roles.py           # Coach role and permission tests
└── test_navigation_actions.py    # UI navigation tests

academy_schedule/tests/
├── __init__.py
├── test_session_occurrence.py    # Session occurrence model tests
├── test_court_conflicts.py       # Court conflict detection tests
├── test_absence_workflow.py      # Absence reporting workflow tests
└── test_attendance_wizard.py     # Attendance wizard tests

academy_billing/tests/
├── __init__.py
├── test_billing_generation.py    # Automated billing tests
└── test_invoice_integration.py   # Accounting integration tests
```

### Test Module `__init__.py`

```python
# academy_core/tests/__init__.py
from . import test_player_constraints
from . import test_coach_roles
from . import test_navigation_actions
```

## Academy Test Patterns

### 1. Model Constraint Tests

**Example**: `academy_core/tests/test_player_constraints.py`

```python
from datetime import date
from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools.sql import column_exists


@tagged('academy_core')
class TestAcademyPlayerConstraints(TransactionCase):
    """Test constraint validation on academy.player model."""
    
    def setUp(self):
        """Set up test data - runs before each test method."""
        super().setUp()
        self._ensure_autopost_bills_default()
        
        # Create test skill group
        self.skill_group = self.env['academy.skill.group'].create({
            'name': 'Green Ball',
            'code': 'GREEN',
            'min_age': 8,
            'max_age': 10,
        })
        
        # Create test guardian
        self.guardian = self.env['res.partner'].create(self._guardian_vals(
            name='Pat Guardian',
            email='pat.guardian@example.com',
            phone='+15550001',
        ))

    def _player_vals(self):
        """Helper method to create player values."""
        dob = date.today() - relativedelta(years=9)
        return {
            'name': 'Ada Player',
            'dob': fields.Date.to_string(dob),
            'skill_group_id': self.skill_group.id,
            'guardian_ids': [(6, 0, [self.guardian.id])],
            'primary_guardian_id': self.guardian.id,
        }

    def _guardian_vals(self, **overrides):
        """Helper method to create guardian values."""
        base_vals = {
            'name': overrides.get('name', 'Guardian'),
            'email': overrides.get('email', 'guardian@example.com'),
        }
        if phone := overrides.get('phone'):
            base_vals['phone'] = phone
        if 'autopost_bills' in self.env['res.partner']._fields:
            base_vals.setdefault('autopost_bills', 'never')
        return base_vals

    def _ensure_autopost_bills_default(self):
        """Ensure autopost_bills column has default value."""
        if column_exists(self.env.cr, 'res_partner', 'autopost_bills'):
            self.env.cr.execute(
                "ALTER TABLE res_partner ALTER COLUMN autopost_bills SET DEFAULT %s",
                ('never',),
            )
            self.env.cr.execute(
                "UPDATE res_partner SET autopost_bills = %s WHERE autopost_bills IS NULL",
                ('never',),
            )

    def test_player_requires_guardian(self):
        """Test that player must have at least one guardian."""
        vals = self._player_vals()
        vals['guardian_ids'] = [(5, 0, 0)]  # Clear all guardians
        vals['primary_guardian_id'] = False
        
        with self.assertRaises(ValidationError, msg='Player should require guardian'):
            self.env['academy.player'].create(vals)

    def test_player_age_must_fit_skill_group(self):
        """Test that player age must be within skill group range."""
        vals = self._player_vals()
        vals['dob'] = date.today() - relativedelta(years=15)  # Too old for Green Ball
        
        with self.assertRaises(ValidationError, msg='Age should be validated against skill group'):
            self.env['academy.player'].create(vals)

    def test_dob_cannot_be_future(self):
        """Test that date of birth cannot be in the future."""
        vals = self._player_vals()
        vals['dob'] = date.today() + relativedelta(days=1)
        
        with self.assertRaises(ValidationError):
            self.env['academy.player'].create(vals)

    def test_primary_guardian_must_be_in_guardians(self):
        """Test that primary guardian must be in guardian list."""
        other_guardian = self.env['res.partner'].create(self._guardian_vals(
            name='Other Guardian',
            email='other@example.com',
        ))
        
        vals = self._player_vals()
        vals['primary_guardian_id'] = other_guardian.id  # Not in guardian_ids
        
        with self.assertRaises(ValidationError):
            self.env['academy.player'].create(vals)
```

### 2. Workflow Tests

**Example**: Testing absence reporting workflow

```python
@tagged('academy_schedule')
class TestAbsenceWorkflow(TransactionCase):
    """Test absence reporting and acknowledgment workflow."""
    
    def setUp(self):
        super().setUp()
        self.player = self._create_test_player()
        self.occurrence = self._create_test_occurrence()
    
    def test_absence_workflow_guardian_to_coach(self):
        """Test full absence workflow from guardian report to coach acknowledgment."""
        # Guardian reports absence
        absence = self.env['academy.session.absence'].create({
            'occurrence_id': self.occurrence.id,
            'player_id': self.player.id,
            'reason': 'Family emergency',
            'state': 'reported',
        })
        
        self.assertEqual(absence.state, 'reported')
        
        # Coach acknowledges
        absence.write({'state': 'acknowledged'})
        self.assertEqual(absence.state, 'acknowledged')
        
        # Coach marks as excused
        absence.write({'state': 'excused'})
        self.assertEqual(absence.state, 'excused')
    
    def test_absence_prevents_attendance(self):
        """Test that absence prevents attendance marking."""
        # Report absence
        absence = self.env['academy.session.absence'].create({
            'occurrence_id': self.occurrence.id,
            'player_id': self.player.id,
            'reason': 'Sick',
            'state': 'reported',
        })
        
        # Attempt to mark attendance
        with self.assertRaises(ValidationError):
            self.env['academy.attendance'].create({
                'session_id': self.occurrence.id,
                'player_id': self.player.id,
            })
```

### 3. Wizard Tests

**Example**: Testing individual session wizard

```python
@tagged('academy_schedule')
class TestIndividualSessionWizard(TransactionCase):
    """Test individual session booking wizard."""
    
    def setUp(self):
        super().setUp()
        self.coach = self._create_test_coach()
        self.player = self._create_test_player()
        self.court = self._create_test_court()
        self.season = self._create_test_season()
    
    def test_wizard_creates_session(self):
        """Test that wizard creates session occurrence."""
        wizard = self.env['academy.individual.session.wizard'].create({
            'player_ids': [(6, 0, [self.player.id])],
            'date': fields.Date.today(),
            'start_time': 17.0,
            'end_time': 18.0,
            'session_type': 'tennis_individual',
            'court_ids': [(6, 0, [self.court.id])],
            'coach_id': self.coach.id,
        })
        
        action = wizard.action_book()
        
        # Verify session created
        occurrence = self.env['academy.session.occurrence'].browse(action['res_id'])
        self.assertEqual(occurrence.session_type, 'tennis_individual')
        self.assertIn(self.player, occurrence.player_ids)
        self.assertEqual(occurrence.coach_id, self.coach)
    
    def test_wizard_detects_court_conflicts(self):
        """Test that wizard detects court booking conflicts."""
        # Create existing session
        existing = self._create_session_occurrence(
            court=self.court,
            start_time=17.0,
            end_time=18.0,
        )
        
        # Try to book same court at same time
        wizard = self.env['academy.individual.session.wizard'].create({
            'player_ids': [(6, 0, [self.player.id])],
            'date': existing.date,
            'start_time': 17.5,  # Overlaps with existing
            'end_time': 18.5,
            'session_type': 'tennis_individual',
            'court_ids': [(6, 0, [self.court.id])],
            'check_conflicts': True,
        })
        
        with self.assertRaises(ValidationError, msg='Should detect court conflict'):
            wizard.action_book()
```

### 4. Integration Tests

**Example**: Testing billing generation from attendance

```python
@tagged('academy_billing')
class TestBillingGeneration(TransactionCase):
    """Test automated billing generation from attendance."""
    
    def setUp(self):
        super().setUp()
        self.guardian = self._create_test_guardian()
        self.player = self._create_test_player(guardian=self.guardian)
        self.occurrence = self._create_test_occurrence()
        
        # Create billing template for guardian
        self.billing_template = self.env['academy.billing.template'].create({
            'guardian_id': self.guardian.id,
            'auto_generate': True,
        })
    
    def test_attendance_creates_billing_item(self):
        """Test that marking attendance creates billing item."""
        # Mark attendance
        attendance = self.env['academy.attendance'].create({
            'session_id': self.occurrence.id,
            'player_id': self.player.id,
        })
        
        # Verify billing item created
        billing_items = self.env['academy.billing.item'].search([
            ('attendance_id', '=', attendance.id),
        ])
        
        self.assertEqual(len(billing_items), 1)
        self.assertEqual(billing_items.guardian_id, self.guardian)
        self.assertEqual(billing_items.player_id, self.player)
    
    def test_monthly_billing_aggregation(self):
        """Test monthly billing cron job aggregates items."""
        # Create multiple attendance records
        for _ in range(5):
            occurrence = self._create_test_occurrence()
            self.env['academy.attendance'].create({
                'session_id': occurrence.id,
                'player_id': self.player.id,
            })
        
        # Run monthly billing cron
        self.env['academy.attendance.billing'].cron_generate_monthly_billing()
        
        # Verify billing aggregation created
        billing = self.env['academy.attendance.billing'].search([
            ('guardian_id', '=', self.guardian.id),
        ])
        
        self.assertTrue(billing)
        self.assertEqual(len(billing.item_ids), 5)
```

### 5. Security/Permission Tests

**Example**: Testing coach access restrictions

```python
@tagged('academy_core')
class TestCoachRoles(TransactionCase):
    """Test coach role permissions and access control."""
    
    def setUp(self):
        super().setUp()
        self.coach = self._create_coach_user()
        self.head_coach = self._create_head_coach_user()
        self.skill_group = self._create_test_skill_group()
    
    def test_coach_can_only_see_assigned_sessions(self):
        """Test coaches only see sessions for assigned skill groups."""
        # Assign skill group to coach
        self.coach.write({
            'academy_coach_skill_groups': [(6, 0, [self.skill_group.id])],
        })
        
        # Create session for assigned group
        assigned_session = self._create_session(skill_group=self.skill_group)
        
        # Create session for different group
        other_group = self._create_test_skill_group(name='Other Group')
        other_session = self._create_session(skill_group=other_group)
        
        # Search as coach
        sessions = self.env['academy.session.occurrence'].with_user(self.coach).search([])
        
        self.assertIn(assigned_session, sessions)
        self.assertNotIn(other_session, sessions)
    
    def test_head_coach_can_create_templates(self):
        """Test that head coaches can create session templates."""
        template = self.env['academy.session.template'].with_user(self.head_coach).create({
            'name': 'Weekly Tennis',
            'skill_group_id': self.skill_group.id,
            'session_type': 'tennis_group',
        })
        
        self.assertTrue(template)
    
    def test_regular_coach_cannot_create_templates(self):
        """Test that regular coaches cannot create templates."""
        with self.assertRaises(AccessError):
            self.env['academy.session.template'].with_user(self.coach).create({
                'name': 'Weekly Tennis',
                'skill_group_id': self.skill_group.id,
                'session_type': 'tennis_group',
            })
```

## Test Data Helpers

### Common Helper Pattern

Create reusable helper methods in `setUp()` or as class methods:

```python
class TestAcademyBase(TransactionCase):
    """Base class with common test data helpers."""
    
    def _create_test_player(self, name='Test Player', **kwargs):
        """Create a test player with default values."""
        guardian = kwargs.pop('guardian', None) or self._create_test_guardian()
        skill_group = kwargs.pop('skill_group', None) or self._create_test_skill_group()
        
        dob = date.today() - relativedelta(years=kwargs.pop('age', 9))
        
        return self.env['academy.player'].create({
            'name': name,
            'dob': dob,
            'skill_group_id': skill_group.id,
            'guardian_ids': [(6, 0, [guardian.id])],
            'primary_guardian_id': guardian.id,
            **kwargs,
        })
    
    def _create_test_guardian(self, **kwargs):
        """Create a test guardian."""
        return self.env['res.partner'].create({
            'name': kwargs.pop('name', 'Test Guardian'),
            'email': kwargs.pop('email', 'guardian@test.com'),
            'phone': kwargs.pop('phone', '+15550000'),
            'academy_is_guardian': True,
            **kwargs,
        })
    
    def _create_test_skill_group(self, **kwargs):
        """Create a test skill group."""
        return self.env['academy.skill.group'].create({
            'name': kwargs.pop('name', 'Test Group'),
            'code': kwargs.pop('code', 'TEST'),
            'min_age': kwargs.pop('min_age', 8),
            'max_age': kwargs.pop('max_age', 10),
            **kwargs,
        })
```

## Test Coverage Goals

### Minimum Coverage by Module

**academy_core**:
- ✅ Player constraint validation
- ✅ Guardian relationship validation
- ✅ Age-based skill group assignment
- ✅ Portal elevation workflow
- ✅ Coach role permissions
- ✅ Name display logic (duplicate handling)

**academy_schedule**:
- ✅ Session occurrence creation from templates
- ✅ Court conflict detection
- ✅ Player double-booking prevention
- ✅ Absence reporting workflow
- ✅ Attendance marking with walk-ins
- ✅ Season suspension logic
- ✅ Wizard validations

**academy_billing**:
- ✅ Billing item generation from attendance
- ✅ Template-based pricing
- ✅ Monthly aggregation cron job
- ✅ Invoice integration
- ✅ Custom line item handling

## Debugging Tests

### Run Single Test Method

```bash
# Run specific test method
python odoo-bin -c odoo.conf --test-enable \
  --test-tags /academy_core:TestAcademyPlayerConstraints.test_player_requires_guardian \
  -d odoo --stop-after-init
```

### Add Debug Breakpoints

```python
def test_something(self):
    """Test with debugging."""
    import pdb; pdb.set_trace()  # Breakpoint
    # ... test code
```

### Print Debug Output

```python
def test_something(self):
    """Test with print debugging."""
    import logging
    _logger = logging.getLogger(__name__)
    
    _logger.info('Debug: player = %s', self.player)
    # ... test code
```

### View SQL Queries

```python
self.env.cr.execute("SELECT * FROM academy_player WHERE id = %s", [player_id])
result = self.env.cr.fetchall()
_logger.info('SQL result: %s', result)
```

## Continuous Integration

For CI/CD pipelines, run all tests:

```bash
# Run all academy tests with coverage
python odoo-bin -c odoo.conf \
  --test-enable \
  --test-tags /academy_core,/academy_schedule,/academy_billing \
  -d test_database \
  --stop-after-init \
  --log-level=test
```

## Best Practices

1. **Isolate Tests**: Each test should be independent and not rely on other tests
2. **Use Helpers**: Create reusable helper methods for common test data
3. **Clear Names**: Test method names should describe what they test
4. **Test Edge Cases**: Test boundary conditions, not just happy paths
5. **Fast Tests**: Keep tests fast by avoiding unnecessary database commits
6. **Clean Up**: Use `setUp()` and `tearDown()` properly to manage test state
7. **Assert Messages**: Provide clear assertion messages for debugging failures
8. **Tag Tests**: Use `@tagged()` for selective test execution
9. **Mock External Calls**: Mock external APIs/services to avoid dependencies
10. **Document Assumptions**: Comment complex test setups to explain assumptions
