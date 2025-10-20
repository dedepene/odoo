# Fix: Weekly Schedule Wizard Template Persistence Issue

**Date:** October 7, 2025  
**Issue:** Wizard showing "Generated 0 sessions from 0 template(s)" - template_id was not persisting in transient wizard lines  
**Root Cause:** Readonly fields in Odoo are not sent by the web client when saving forms

---

## Problem Summary

The Weekly Schedule Wizard was redesigned to be a selection-only interface (no editing of templates in wizard). However, when clicking "Apply & Generate Sessions", it would always report "0 sessions generated" because the `template_id` field was being lost during form submission.

### Technical Details

1. **Transient Model Behavior**: Transient models (`models.TransientModel`) don't persist data like regular models
2. **Readonly Field Issue**: The web client does NOT send readonly fields back to the server when saving forms
3. **Related Fields Problem**: Using `related='template_id.field_name'` didn't work because the `template_id` itself was lost
4. **Form Save Process**: When the wizard form is saved (on clicking Apply), it calls `default_get` again but WITHOUT `line_ids` in the fields list, so the lines are created empty

---

## Solution Applied

### 1. Changed `template_id` Field from Readonly to Editable

**File:** `custom_addons/academy_schedule/wizard/weekly_schedule_wizard.py`

**Change:**
```python
# OLD (didn't work):
template_id = fields.Many2one('academy.session.template', string='Template', 
                             required=True, readonly=True)

# NEW (works):
template_id = fields.Many2one('academy.session.template', string='Template', 
                             required=True, readonly=False)  # Must be editable for web client to send it
```

**Why:** Even though the field is hidden in the UI (`column_invisible="1"`), it must be **editable** (`readonly=False`) for the web client to include it in the form data when saving.

### 2. Store All Template Data Directly (Not as Related Fields)

**File:** `custom_addons/academy_schedule/wizard/weekly_schedule_wizard.py`

**Change:**
```python
# OLD (didn't work - related fields):
skill_group_id = fields.Many2one('academy.skill.group', string='Skill Group',
                                related='template_id.skill_group_id', readonly=True)
day_of_week = fields.Selection(related='template_id.day_of_week', readonly=True)
# ... etc

# NEW (works - stored fields):
skill_group_id = fields.Many2one('academy.skill.group', string='Skill Group', readonly=True)
day_of_week = fields.Selection([
    ('0', 'Monday'),
    ('1', 'Tuesday'),
    # ... full definition
], readonly=True)
# ... etc
```

**Why:** Related fields depend on `template_id` being present. Since `template_id` was being lost, all related fields became empty. Storing the data directly ensures it persists even in transient records.

### 3. Populate All Fields in `default_get`

**File:** `custom_addons/academy_schedule/wizard/weekly_schedule_wizard.py`

**Change:**
```python
# OLD (minimal data):
lines.append((0, 0, {
    'template_id': template.id,
    'selected': True,
}))

# NEW (complete data):
lines.append((0, 0, {
    'template_id': template.id,
    'selected': True,
    # Copy all template data directly
    'skill_group_id': template.skill_group_id.id,
    'day_of_week': template.day_of_week,
    'start_time': template.start_time,
    'end_time': template.end_time,
    'session_type': template.session_type,
    'court_ids': [(6, 0, template.court_ids.ids)],
    'coach_id': template.coach_id.id if template.coach_id else False,
    'occurrence_count': template.occurrence_count,
}))
```

**Why:** By copying all template data into the wizard line fields during creation, the data is preserved even if `template_id` was lost (though now it's not lost anymore).

### 4. Add `template_id` to View as Hidden Field

**File:** `custom_addons/academy_schedule/wizard/weekly_schedule_wizard_views.xml`

**Change:**
```xml
<field name="line_ids" nolabel="1">
    <list editable="bottom" create="0" delete="0">
        <!-- MUST be first so it's included in form data -->
        <field name="template_id" column_invisible="1"/>
        <field name="selected" widget="boolean_toggle"/>
        <field name="skill_group_id"/>
        <!-- ... other fields ... -->
    </list>
</field>
```

**Why:** The field must be present in the view for the web client to include it in the form data. Using `column_invisible="1"` hides it from the user while still including it in the data.

---

## Key Lessons Learned

### 1. **Odoo Readonly Field Behavior**
- **Readonly fields are NOT sent by the web client** when saving forms
- If you need a field value to persist through a form save, it MUST be editable (`readonly=False`)
- You can still hide it visually using `column_invisible="1"` or `invisible="1"`

### 2. **Transient Models and One2many Relations**
- Transient models (`models.TransientModel`) don't persist data between requests
- One2many lines created in `default_get` are recreated on every form load
- Data must be explicitly passed in the `default_get` return value

### 3. **Related Fields Limitations**
- Related fields (`related='other_field.field_name'`) only work if the source field (`other_field`) has a value
- In transient models, related fields may not persist properly
- For critical data, store it directly instead of using related fields

### 4. **Form Save Process**
When a user clicks a button on a wizard form:
1. Web client calls `web_save` to save the form
2. This triggers `default_get` with a LIMITED fields list (e.g., `['id', 'display_name', ...]`)
3. One2many lines are saved separately
4. Then the button method is called
5. If fields aren't in the view or are readonly, they're lost during this process

---

## Testing

### Verify the Fix:
1. Open **Academy → Seasons → Есен 25**
2. Click **Define Weekly Schedule**
3. See both templates listed (Зелени, Оранжеві) with all data visible
4. Check/uncheck templates as needed
5. Click **Apply & Generate Sessions**
6. **Expected:** Success message showing "Generated X sessions from Y template(s)"
7. **Expected:** Sessions are created for the selected templates

### Debug Logging Added:
```python
_logger.info(f"Line ID {line.id}: selected={line.selected}, template_id={line.template_id.id if line.template_id else 'MISSING'}")
```

This logging helps identify when `template_id` is missing.

---

## Files Modified

1. **`custom_addons/academy_schedule/wizard/weekly_schedule_wizard.py`**
   - Changed `template_id` field to `readonly=False`
   - Removed `related=` from all display fields
   - Added full field definitions for `day_of_week` and `session_type`
   - Updated `default_get` to populate all field values directly

2. **`custom_addons/academy_schedule/wizard/weekly_schedule_wizard_views.xml`**
   - Added `<field name="template_id" column_invisible="1"/>` as first field in list
   - Kept all other fields readonly for display

---

## Related Issues

This fix also resolved the original issue where the wizard was showing false "Court conflict detected!" errors. The root cause was that the wizard was confusing users about when they were editing vs. creating templates, leading to accidental duplicate creation attempts. The solution was to:

1. Redesign wizard as **selection-only** interface (no editing)
2. Make template creation/editing happen in the **Session Templates** menu
3. Fix the `template_id` persistence issue so the wizard actually works

---

## Odoo Version
- **Odoo 19.0**
- Note: In Odoo 19, `view_mode="tree"` was renamed to `view_mode="list"`

---

## References
- [Odoo Documentation: Transient Models](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html#transient-models)
- [Odoo Documentation: Fields](https://www.odoo.com/documentation/19.0/developer/reference/backend/orm.html#fields)
- Original issue: False court conflict detection → Led to UX redesign → Led to template_id persistence issue
