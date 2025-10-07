# Fix: False Court Conflict Detection in Session Templates

## Problem
Users were getting a "Court conflict detected!" error when trying to schedule sessions via the Weekly Schedule wizard, even though no actual scheduling conflicts existed.

**Error message:**
```
Validation Error
Court conflict detected! Courts Първи, Трети are already allocated to: Оранжеви - Tuesday 10:00
```

## Root Cause
The issue occurred when users **accidentally created a NEW template line** in the wizard instead of editing the existing pre-loaded template line. This happened when:

1. User opens "Define Weekly Schedule" wizard
2. Wizard pre-loads existing templates (both Зелени and Оранжеви)
3. User deletes all lines from the wizard
4. User manually adds a new line for Оранжеви with same schedule
5. When clicking "Apply", the wizard tries to CREATE a new template
6. The new template conflicts with the existing Оранжеви template → ERROR

The constraint was working correctly - it was preventing actual duplicates. The problem was that the wizard allowed users to inadvertently create duplicate templates.

## Solution
Implemented a two-layer fix:

### 1. Improved Conflict Detection (`academy_session_template.py`)
**Simplified the time overlap check:**
- Removed redundant OR condition in search domain
- Used standard interval overlap formula: `start < other.end AND end > other.start`
- Added defensive checks for incomplete records
- Added double-verification of court overlap before raising error

### 2. Wizard-Level Duplicate Prevention (`weekly_schedule_wizard.py`)
**Added proactive duplicate detection:**
```python
# If this line doesn't have a template_id, check for existing templates with same schedule
if not self.template_id:
    existing = self.env['academy.session.template'].search([
        ('season_id', '=', self.wizard_id.season_id.id),
        ('skill_group_id', '=', self.skill_group_id.id),
        ('day_of_week', '=', self.day_of_week),
        ('start_time', '=', self.start_time),
        ('end_time', '=', self.end_time),
        ('active', '=', True),
    ], limit=1)
    
    if existing:
        raise ValidationError(
            f'A template for {self.skill_group_id.name} already exists!\n\n'
            f'Please edit the existing line instead of adding a new one.'
        )
```

This provides a clear, user-friendly error message BEFORE attempting to create the duplicate.

## User Workflow
**Correct way to modify schedules:**
1. Open "Define Weekly Schedule"
2. Wizard loads existing templates automatically
3. **Edit the pre-loaded lines** (don't delete and re-add)
4. Remove unwanted lines by deleting them
5. Click "Apply & Generate Sessions"

**What NOT to do:**
- Don't delete all lines and manually add new ones
- Use the pre-loaded lines that appear automatically

## Testing
✅ Module upgraded successfully  
✅ Updating existing templates works without false conflicts  
✅ Attempting to create duplicate templates shows clear error message  
✅ Actual conflicts are still properly detected

## Files Modified
- `custom_addons/academy_schedule/models/academy_session_template.py` - Improved `_check_court_conflicts` method
- `custom_addons/academy_schedule/wizard/weekly_schedule_wizard.py` - Added duplicate prevention in `_validate_line` method

## Date
October 7, 2025
