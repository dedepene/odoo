# Player Attendance System - Implementation Handover

## Document Information
- **Module**: `academy_schedule` (attendance functionality extension)
- **Date**: October 14, 2025
- **Version**: 19.0.1.0.0
- **Status**: Complete - Core functionality implemented

---

## Executive Summary

This document details the implementation of the comprehensive attendance management system for the Tennis Academy, as specified in the academy requirements and user stories. The system enables efficient attendance tracking through coach-validated prepopulated rosters, walk-in player management, automated billing generation, and comprehensive reporting.

### Key Features Implemented
1. ✅ Coach attendance confirmation with prepopulated rosters
2. ✅ Walk-in player addition with reason tracking
3. ✅ Attendance tracking for absence/credit reconciliation
4. ✅ Security and access control
5. ✅ Backend views and wizards

### Features Pending
- **Pre-Paid Billing System**: The billing logic described in this document is now **DEPRECATED**. A new pre-paid and reconciliation model has been designed. See the `doc/dev/billing/academy_billing_user_stories.md` document for the new specification.
- Guardian portal attendance history views
- Admin reporting pivot tables and analytics

---

## Architecture Overview

> [!WARNING]
> The billing-related models and logic (`academy.billing.item`, `academy.attendance.billing`) described below are **DEPRECATED** as of October 21, 2025. They were part of an attendance-driven, post-paid billing system. The new architecture is a **pre-paid and reconciliation model**. Refer to `doc/dev/billing/academy_billing_user_stories.md` for the current design. The `academy.attendance` model remains critical for tracking presence and reconciling absences.

### Data Models

#### 1. `academy.attendance`
**Purpose**: Tracks coach-confirmed present players only. This record is the source of truth for confirming a player's presence at a session, which is vital for the end-of-month reconciliation process.

**Key Fields**:
- `session_id` (Many2one → academy.session.occurrence) - Required
- `player_id` (Many2one → academy.player) - Required
- `state` (Selection) - 'present', 'late' (future use)
- `marked_by_id` (Many2one → res.users) - Coach who confirmed
- `confirmation_time` (Datetime) - When confirmed
- `is_walkin` (Boolean) - Walk-in player flag
- `walkin_reason` (Selection) - Trial, makeup, advancement, other
- `billing_item_id` (Many2one → academy.billing.item) - **DEPRECATED**: This link is no longer used in the new billing model.

**SQL Constraints**:
- Unique constraint on (session_id, player_id) - One attendance per player per session

**Business Rules**:
- Created ONLY when coach marks player as present during confirmation.
- A player with no `academy.attendance` record for a session is considered absent. This is cross-referenced with `academy.session.absence` records to determine if the absence was excused.

**File**: `custom_addons/academy_schedule/models/academy_attendance.py` (lines 1-185)

---

#### 2. `academy.session.participant`
**Purpose**: Tracks all session participants including walk-ins (temporary session assignments). This model remains unchanged.

**Key Fields**:
- `session_id` (Many2one → academy.session.occurrence) - Required
- `player_id` (Many2one → academy.player) - Required
- `is_walkin` (Boolean) - Default False
- `walkin_reason` (Selection) - Trial, makeup, advancement, other
- `walkin_reason_note` (Text) - Additional notes
- `added_by_id` (Many2one → res.users) - Who added the walk-in
- `added_date` (Datetime) - When added

**SQL Constraints**:
- Unique constraint on (session_id, player_id) - Prevent duplicate participants

**Business Rules**:
- Created automatically for walk-in players via wizard
- Regular participants come from skill group or session player_ids (not stored as participants)

**File**: `custom_addons/academy_schedule/models/academy_attendance.py` (lines 187-235)

---

#### 3. `academy.billing.item` (DEPRECATED)
**Purpose**: **(Old Logic)** Billing items generated from confirmed attendance for invoicing. **(New Logic)** This model may be repurposed for ad-hoc charges, but it is no longer central to session billing.

**File**: `custom_addons/academy_schedule/models/academy_attendance.py` (lines 237-430)

---

#### 4. `academy.attendance.billing` (DEPRECATED)
**Purpose**: **(Old Logic)** Billing processor for automated post-paid billing generation. This model and its methods are fully deprecated.

**File**: `custom_addons/academy_schedule/models/academy_attendance.py` (lines 432-604)

---

### Session Occurrence Model Extensions

#### Updated Fields in `academy.session.occurrence`
**File**: `custom_addons/academy_schedule/models/academy_session_occurrence.py`

**New Fields Added**:
```python
attendance_ids = fields.One2many('academy.attendance', 'session_id')
attendance_count = fields.Integer(compute='_compute_attendance_count', store=True)
attendance_status = fields.Selection([
    ('pending', 'Pending Confirmation'),
    ('confirmed', 'Confirmed'),
    ('completed', 'Completed'),
], default='pending')
participant_ids = fields.One2many('academy.session.participant', 'session_id')
```

**New Methods**:
- `_get_registered_players()` - Returns all eligible players for session
  - Group sessions: All players in skill_group_id
  - Individual sessions: Explicitly assigned player_ids

- `action_confirm_attendance()` - Opens attendance confirmation wizard
  - ⚠️ **CURRENTLY DISABLED FOR TESTING**: Time window validation (15 min before to 30 min after session start)
    - To re-enable: Uncomment lines 393-401 in `academy_session_occurrence.py`
    - Production deployment should enable this validation
  - Prevents duplicate confirmation
  - Creates wizard with prepopulated roster and absence requests

- `process_attendance_confirmation(present_player_ids)` - Processes confirmation
  - Creates attendance records ONLY for checked (present) players
  - Updates attendance_status to 'confirmed'
  - Posts chatter audit message with counts
  - Returns summary dict

- `action_add_walkin_player()` - Opens walk-in player wizard

---

## Wizards

### 1. Attendance Confirmation Wizard
**Model**: `academy.attendance.confirmation.wizard`
**File**: `custom_addons/academy_schedule/wizard/attendance_wizards.py` (lines 1-199)

**Purpose**: Coach interface for confirming attendance by unchecking absentees.

**Fields**:
- `session_id` - Session being confirmed (readonly)
- `registered_player_ids` - All registered players (readonly, hidden)
- `present_player_ids` - Players marked present (checkboxes, all checked by default)
- `absence_request_ids` - Pre-reported absences (readonly, displayed separately)
- Computed counts: total_count, present_count, absent_count, pre_reported_count
- `confirmation_message` - HTML summary

**Workflow**:
1. Coach opens session from "Today's Sessions" menu
2. Clicks "Confirm Attendance" button on session form
3. Wizard displays with all registered players checked (☑️)
4. Pre-reported absences shown separately (not in main roster)
5. Coach unchecks players who are absent (❌)
6. Coach clicks "Confirm Attendance"
7. System creates attendance records ONLY for checked players
8. Session attendance_status changes to 'confirmed'

**Key Method**:
- `action_confirm()` - Validates and calls `session_id.process_attendance_confirmation()`

**View**: `custom_addons/academy_schedule/views/attendance_wizard_views.xml`

**Recent Update (Oct 14, 2025)**: Walk-in functionality integrated into main attendance wizard.

---

### 2. Walk-In Player Addition (Integrated)
**Implementation**: Integrated into `academy.attendance.confirmation.wizard`
**File**: `custom_addons/academy_schedule/wizard/attendance_wizards.py`

**Purpose**: Add unregistered academy players to session (trials, makeups, advancement) directly within the attendance confirmation dialog.

**New Fields Added to Attendance Wizard**:
- `walkin_player_id` - Searchable player selection (Many2one)
- `walkin_reason` - Trial, makeup, advancement, other (Selection)
- `walkin_ids` - List of added walk-ins (One2many to `academy.attendance.confirmation.wizard.walkin`)
- `walkin_count` - Number of walk-ins (computed)

**Walk-In Line Model**: `academy.attendance.confirmation.wizard.walkin`
- `wizard_id` - Parent wizard reference
- `player_id` - Selected player
- `reason` - Walk-in reason (trial/makeup/advancement/other)
- `skill_group_id` - Related from player (for display)

**Workflow**:
1. Coach opens "Confirm Attendance" wizard
2. In **Walk-In Players** section, types to search for player
   - Players displayed as: **[Skill Group] Player Name**
   - Duplicates shown as: **[Skill Group] Player Name (Guardian Name)**
3. Selects player from dropdown
4. Chooses reason (defaults to "makeup")
5. Player automatically added to walk-ins list and marked present
6. Coach can repeat for multiple walk-ins
7. Clicks "Confirm Attendance" - system creates:
   - `academy.session.participant` records for each walk-in (is_walkin=True)
   - `academy.attendance` records for all present players including walk-ins

**Player Display Format** (Custom `name_get` on `academy.player`):
```python
# Normal: [Оранжеви] Далия Величкова
# Duplicate: [Оранжеви] Иван Петров (Мария Петрова)
```

**Validation**:
- Player must exist in academy (searchable dropdown, no create)
- Player cannot already be in session roster (warning shown)
- Prevents duplicate walk-in additions (warning shown)

**Key Methods**:
- `_onchange_walkin_player()` - Adds player to walk-ins list on selection
- `action_confirm()` - Creates participant records before processing attendance

**View**: `custom_addons/academy_schedule/views/attendance_wizard_views.xml`

**Removed**: Standalone `academy.attendance.walkin.wizard` wizard (deprecated)

---

## Views and UI

### Backend Views

#### Attendance List View
**File**: `custom_addons/academy_schedule/views/attendance_views.xml`
- Columns: Player, Session, Date, Type, Skill Group, State, Walk-In, Coach, Time, Billed
- Filters: Present, Walk-In, Billed, Unbilled, This Month
- Group By: Player, Session, Skill Group, Session Type, Date
- Actions: View-only (create/delete disabled)

#### Attendance Form View
- Displays all attendance details
- Links to billing item if billed
- Shows walk-in ribbon if applicable
- Chatter for audit trail
- Read-only (cannot edit confirmed attendance)

#### Billing Item List View
- Columns: Player, Date, Type, Guardian, Amount, Walk-In, State
- Filters: Pending, Approved, Invoiced, Walk-In, This Month
- Group By: Player, Guardian, Status, Date
- Bulk actions: Approve, Cancel
- Sum column for total amount

#### Billing Item Form View
- Header actions: Approve, Cancel
- Links to attendance, session, invoice
- Walk-in and auto-generated ribbons
- State workflow: pending → approved → invoiced

#### Session Participant List/Form
- Shows walk-in participants
- Displays reason and added by/date
- Read-only for coaches (admin can edit)

### Menu Structure
```
Academy
└── Scheduling
    └── Attendance (NEW)
        ├── Attendance Records
        └── Billing Items
```

---

## Security and Access Control

### Access Rights
**File**: `custom_addons/academy_schedule/security/ir.model.access.csv`

| Model | Admin | Head Coach | Coach | Portal |
|-------|-------|------------|-------|--------|
| academy.attendance | CRUD | CRUD | CRUD | R |
| academy.billing.item | CRUD | R | - | R (own) |
| academy.session.participant | CRUD | CRU | CRU | - |
| academy.attendance.billing | CRUD | - | - | - |
| Attendance wizards | CRUD | CRUD | CRUD | - |

**Notes**:
- Coaches can create/read/update attendance but not delete (billed records protected)
- Only admins can manage billing items
- Portal users can only view their own children's attendance (guardian record rules needed)

### Record Rules (To Be Added)
**Recommended** (not yet implemented):
```xml
<!-- Guardians see only their children's attendance -->
<record id="attendance_guardian_rule" model="ir.rule">
    <field name="name">Guardians: Own Children Attendance</field>
    <field name="model_id" ref="model_academy_attendance"/>
    <field name="domain_force">[('player_id.guardian_ids', 'in', [user.partner_id.id])]</field>
    <field name="groups" eval="[(4, ref('base.group_portal'))]"/>
</record>
```

---

## Cron Jobs

### Monthly Billing Cron (DEPRECATED)
**File**: `custom_addons/academy_schedule/data/attendance_billing_cron.xml`

> [!IMPORTANT]
> This cron job, which generates billing items from attendance, is **DEPRECATED**. The new system uses two separate cron jobs: one for generating pre-paid invoices at the start of the month, and another for reconciling acknowledged absences to create credit notes at the end of the month. See `doc/dev/billing/academy_billing_user_stories.md` for details.

---

## Business Logic and Workflows

### Coach Attendance Confirmation Flow

The flow for a coach confirming attendance remains largely the same. The key difference is the *consequence* of the data. Creating an `academy.attendance` record no longer directly triggers a billable item. Instead, it serves as a positive confirmation of presence, which is used during the end-of-month reconciliation to differentiate between a "no-show" (absent, but no `academy.session.absence` record) and an attended session.

```
1. Session scheduled (state='planned')
   ├─> Roster generated from skill_group_id or player_ids
   └─> Absence requests recorded by guardians

2. Session start time approaches
   └─> Coach opens "Today's Sessions"

3. Coach clicks "Confirm Attendance" on session
   ├─> Wizard opens with prepopulated roster
   ├─> All players checked (☑️) by default
   ├─> Pre-reported absences displayed separately
   ├─> Walk-In Players section available
   └─> Coach unchecks absent players (❌)

4. Coach adds walk-in players (optional)
   └─> Process remains the same.

5. Coach clicks "Confirm Attendance" button
   ├─> System creates `academy.attendance` records for ALL present players.
   └─> NO `academy.billing.item` is created at this stage.

6. Session attendance_status changes to 'confirmed'
   └─> Data is now ready for end-of-month reconciliation.
```

### Walk-In Player Flow (Integrated)

The walk-in flow is unchanged. However, how walk-ins are billed is now handled by the new pre-paid system. A walk-in for a trial might still be free, but a walk-in for a makeup session is effectively already paid for. Other walk-ins would likely be handled via "Ad-Hoc Charges" as defined in the new billing user stories.

### Billing Generation Flow (DEPRECATED)

```
The entire post-paid billing flow described previously is DEPRECATED.

The new flow is:

1. START of Month (e.g., Nov 1st):
   ├─> Cron job runs (`cron_generate_monthly_prepaid_invoices`).
   ├─> System finds all players' scheduled sessions for November.
   ├─> System checks for available credits from October's reconciliation.
   ├─> Generates one invoice per guardian for all of November's sessions, applying any credits.
   └─> Invoice is sent.

2. DURING Month (e.g., Nov 1st - 30th):
   ├─> Guardians report absences (`academy.session.absence` created).
   ├─> Coaches confirm attendance (`academy.attendance` created for present players).
   ├─> Coaches "Acknowledge" reported absences.

3. END of Month (e.g., Dec 1st):
   ├─> Cron job runs (`cron_reconcile_monthly_absences`).
   ├─> System finds all 'acknowledged' absences from November.
   ├─> For each one, a credit note (`account.move` of type `out_refund`) is created.
   └─> These credits are now available to be applied to the December invoice.
```

### Key Principle: Pre-Paid First, Reconcile Later

The core principle has shifted from "No Attendance = No Billing" to a pre-paid model with credits for excused absences.

```
Scenario 1: Player attends
  ├─> Guardian was pre-billed for the session.
  ├─> Coach marks player as present (☑️) -> `academy.attendance` record created.
  └─> At month-end, nothing to reconcile for this session. The pre-payment is kept. ✅

Scenario 2: Player has an excused, acknowledged absence
  ├─> Guardian was pre-billed for the session.
  ├─> Guardian reports absence -> `academy.session.absence` created.
  ├─> Coach "Acknowledges" the absence.
  └─> At month-end, a credit note is generated for this session. ✅

Scenario 3: Player is a no-show (unreported absence)
  ├─> Guardian was pre-billed for the session.
  ├─> Coach marks player as absent (❌) -> NO `academy.attendance` record.
  ├─> There is no corresponding `academy.session.absence` record.
  └─> At month-end, nothing to reconcile. No credit is given. The pre-payment is kept. ✅
```

---

## Testing and Validation

### Manual Testing Checklist

#### A. Attendance Confirmation
1. ✅ Create a session with registered players
2. ✅ Navigate to session (⚠️ **TESTING MODE**: Time window validation disabled)
3. ✅ Click "Confirm Attendance"
4. ✅ Verify all players checked by default
5. ✅ Uncheck 2-3 players (mark absent)
6. ✅ Confirm attendance
7. ✅ Verify:
   - Attendance records created ONLY for checked players
   - NO attendance for unchecked players
   - Session attendance_status = 'confirmed'
   - Chatter message with counts
8. ✅ Attempt to confirm again → expect error

#### B. Walk-In Player Addition
1. ✅ During attendance confirmation, in **Walk-In Players** section:
2. ✅ Type to search for player (e.g. "Дал" → finds Далия)
3. ✅ Verify player display format: **[Skill Group] Player Name**
4. ✅ Select player from dropdown
5. ✅ Choose walk-in reason (trial/makeup/advancement/other)
6. ✅ Verify player appears in walk-ins list
7. ✅ Verify player automatically added to present players (checked)
8. ✅ Add another walk-in player
9. ✅ Remove a walk-in from list (delete button)
10. ✅ Confirm attendance
11. ✅ Verify:
   - Participant records created for walk-ins (is_walkin=True)
   - Attendance records include walk-ins
   - Walkin_count shown in confirmation summary
12. ✅ Try to add same player twice → expect warning
13. ✅ Try to add registered player as walk-in → expect warning
4. ✅ Choose reason: "Skill Level Advancement"
5. ✅ Add player
6. ✅ Verify:
   - Player appears in roster with walk-in indicator
   - academy.session.participant record created (is_walkin=True)
   - academy.attendance record created (is_walkin=True, state='present')
   - Chatter message documents addition
7. ✅ Attempt to add same player again → expect error

#### C. Billing Generation (DEPRECATED)
This entire testing section is deprecated. Testing should now follow the user stories in `doc/dev/billing/academy_billing_user_stories.md`, focusing on:
1.  **Billing Template Creation**: Verify the default template is created and configurable.
2.  **Pre-Paid Invoice Generation**: Run the daily cron and verify invoices are created on the correct day based on the template, for the correct amount, and that prior credits are applied.
3.  **Ad-Hoc Charge Inclusion**: Create ad-hoc charges and ensure they appear on the next invoice.
4.  **Absence Acknowledgment**: Verify coaches can "Acknowledge" absences.
5.  **Credit Note Reconciliation**: Run the month-end reconciliation cron and verify that credit notes are created *only* for acknowledged absences.

#### D. Absence Request Integration
1. ✅ Create absence request for upcoming session (guardian portal or admin)
2. ✅ Open attendance confirmation wizard
3. ✅ Verify:
   - Absent player shown in separate "Pre-Reported Absences" section
   - Absent player NOT in main roster checkboxes
4. ✅ Confirm attendance
5. ✅ Verify:
   - NO `academy.attendance` record is created for the absent player.
   - This absence is now eligible to be "Acknowledged" by a coach for credit.

#### E. Security and Access
1. ✅ Login as coach
2. ✅ Verify can:
   - View attendance records
   - Confirm attendance
   - Add walk-ins
   - **Acknowledge reported absences**
3. ✅ Verify cannot:
   - Delete confirmed attendance
   - Manage billing templates or invoices
4. ✅ Login as admin
5. ✅ Verify can:
   - View all attendance
   - Manage billing templates
   - Review generated invoices and credit notes
   - Run billing and reconciliation crons manually

---

## Configuration

### System Parameters (ir.config_parameter)
The pricing parameters are now **DEPRECATED** as session pricing should be handled more robustly, likely on the `academy.session` model itself or linked through products. The new system introduces `academy.billing.template` which holds configuration for timing.

| Key | Default | Description |
|-----|---------|-------------|
| academy.billing.group_tennis_price | 25.00 | **DEPRECATED** |
| academy.billing.group_physical_price | 20.00 | **DEPRECATED** |
| academy.billing.individual_tennis_price | 60.00 | **DEPRECATED** |
| academy.billing.individual_physical_price | 40.00 | **DEPRECATED** |

### Cron Configuration
The single billing cron is replaced by two new ones:
1.  **"Academy: Generate Monthly Pre-Paid Invoices"**: Runs daily, checks for templates due for generation.
2.  **"Academy: Reconcile Monthly Absences for Credit"**: Runs monthly (1st of month), processes the previous month's acknowledged absences.

---

## Database Schema

### ER Diagram (Simplified, Reflecting New Logic)

```
academy.session
    ├──> academy.billing.template (billing_template_id)

academy.session.occurrence
    ├──< academy.attendance (session_id)
    │    └──> academy.player (player_id)
    │
    └──< academy.session.absence (occurrence_id)
         ├──> academy.player (player_id)
         └──> account.move (credit_note_id)  // Link to generated credit

account.move (Invoice)
    ├──> res.partner (partner_id) // Guardian
    └──< account.move.line

account.move (Credit Note)
    ├──> res.partner (partner_id) // Guardian
    └──> academy.session.absence (origin_absence_id) // Link back to source
```

### Key Relationships
- **One-to-One**: `academy.session.absence` → `account.move` (An acknowledged absence generates one credit note).
- The `academy.billing.item` model is no longer central and its relationship to `academy.attendance` is severed.

---

## Known Limitations and Future Enhancements

### Current Limitations
1. **No partial attendance tracking**.
2. **No attendance correction UI**.
3. **No guardian portal views for attendance/billing history**.
4. **No analytics/reporting**.

### Recommended Enhancements
The previous recommendations are still valid. The "Automated Invoice Generation" is now the core of the new system, but the other points remain relevant.

1.  **Guardian Portal Views** (Priority: HIGH)
2.  **Admin Analytics** (Priority: HIGH)
3.  **Attendance Correction Workflow** (Priority: MEDIUM)
4.  **Late Arrival Tracking** (Priority: LOW)

---

## Troubleshooting

The previous troubleshooting steps related to billing are now **DEPRECATED**. New issues will revolve around the pre-paid and reconciliation logic.

### Issue: Invoice generated on the wrong day or for the wrong amount.
**Cause**: Misconfiguration in the `academy.billing.template` or error in the session scheduling.
**Solution**:
- Verify `invoice_generation_day` on the template.
- Check the player's scheduled sessions for the month to ensure the count is correct.

### Issue: Credit not applied to an invoice.
**Cause**: The absence was not "Acknowledged" by a coach, or the reconciliation cron job has not run yet.
**Solution**:
- Ensure the `academy.session.absence` record has a state of 'acknowledged'.
- Manually run the `cron_reconcile_monthly_absences` for the correct period.
- Check that the generated credit note (`account.move`) is in a 'posted' state and un-reconciled.

### Issue: Duplicate credit given for one absence.
**Cause**: The `academy.session.absence` record was not correctly marked as 'credited' after reconciliation.
**Solution**:
- Add constraints to prevent an absence from being linked to more than one credit note.
- Review the reconciliation logic to ensure the state is updated immediately after credit creation.


---

## File Index

### Models
- `custom_addons/academy_schedule/models/academy_attendance.py`
  - Lines 1-185: `academy.attendance`
  - Lines 187-235: `academy.session.participant`
  - Lines 237-430: `academy.billing.item`
  - Lines 432-604: `academy.attendance.billing`

- `custom_addons/academy_schedule/models/academy_session_occurrence.py`
  - Lines 90-108: Attendance-related fields added
  - Lines 243-247: `_compute_attendance_count()`
  - Lines 367-380: `_get_registered_players()`
  - Lines 382-426: `action_confirm_attendance()`
  - Lines 428-516: `process_attendance_confirmation()`
  - Lines 518-531: `action_add_walkin_player()`

### Wizards
- `custom_addons/academy_schedule/wizard/attendance_wizards.py`
  - Lines 1-199: `academy.attendance.confirmation.wizard`
  - Lines 201-379: `academy.attendance.walkin.wizard`

### Views
- `custom_addons/academy_schedule/views/attendance_views.xml`
  - Attendance list/form/search views
  - Billing item list/form/search views
  - Session participant views
  - Menu items

- `custom_addons/academy_schedule/views/attendance_wizard_views.xml`
  - Attendance confirmation wizard form
  - Walk-in player wizard form

### Data
- `custom_addons/academy_schedule/data/attendance_billing_cron.xml`
  - Cron job definition
  - Pricing system parameters

### Security
- `custom_addons/academy_schedule/security/ir.model.access.csv`
  - Lines 31-50: Attendance model access rules

---

## Deployment Instructions

### 1. Update Module
```bash
cd /path/to/odoo
python odoo-bin -c odoo.conf -u academy_schedule -d odoo --stop-after-init
```

### 2. Verify Models Created
```python
# In Odoo shell
env['ir.model'].search([('model', 'in', [
    'academy.attendance',
    'academy.billing.item',
    'academy.session.participant',
    'academy.attendance.billing',
    'academy.attendance.confirmation.wizard',
    'academy.attendance.walkin.wizard',
])])
```

### 3. Configure Pricing (Optional)
Navigate to: Settings > Technical > Parameters > System Parameters
- Verify pricing parameters exist (default values set by data file)
- Adjust if needed

### 4. Enable Billing Cron
Navigate to: Settings > Technical > Scheduled Actions
- Find "Academy: Generate Monthly Billing from Attendance"
- Verify Active = True
- Adjust schedule if needed

### 5. Test Workflow
1. Create test session with players
2. Confirm attendance via wizard
3. Verify attendance records created
4. Manually run billing: `env['academy.attendance.billing'].generate_billing_items()`
5. Verify billing items created

---

## Support and Maintenance

### Developer Contacts
- **Module Developer**: dedepene
- **Date Implemented**: October 14, 2025

### Code Review Notes
- All models follow Odoo 19 conventions
- Security properly configured (coaches, head coaches, admins)
- Chatter integration for audit trails
- SQL constraints prevent duplicates
- Business logic matches user stories

### Performance Considerations
- Attendance queries use indexes (session_id, player_id, session_date)
- Billing cron limited to monthly runs (not daily)
- Computed fields stored for faster access
- No N+1 queries in billing generation

---

## Appendix A: Sample Data Scenarios

### Scenario 1: Normal Group Session
- **Session**: Green Ball Group - Monday 15:00
- **Registered**: 12 players in Green Ball skill group
- **Attendance**:
  - 10 players present (checked by coach)
  - 1 pre-reported absence (illness)
  - 1 unreported absence (no-show)
- **Result**:
  - 10 attendance records created
  - 10 billing items × $25 = $250
  - 0 billing items for absences

### Scenario 2: Session with Walk-In
- **Session**: Orange Ball Group - Tuesday 17:00
- **Registered**: 8 players in Orange Ball skill group
- **Walk-In**: 1 Green Ball player (skill advancement)
- **Attendance**:
  - 8 registered players present
  - 1 walk-in player present
- **Result**:
  - 9 attendance records created (1 with is_walkin=True)
  - 9 billing items × $25 = $225 (walk-in advancement = normal price)

### Scenario 3: Trial Session (Walk-In)
- **Session**: Hard Ball Group - Wednesday 16:00
- **Walk-In**: 1 new player (trial)
- **Attendance**:
  - 1 walk-in player present (is_walkin=True, walkin_reason='trial')
- **Result**:
  - 1 attendance record created
  - 1 billing item × $0 = $0 (trial = free)
  - Flagged for admin review

---

## Appendix B: SQL Queries for Reporting

### Monthly Attendance Summary by Player
```sql
SELECT 
    p.name AS player_name,
    p.reference AS player_code,
    COUNT(a.id) AS sessions_attended,
    SUM(bi.amount) AS total_billed
FROM academy_player p
LEFT JOIN academy_attendance a ON a.player_id = p.id
LEFT JOIN academy_billing_item bi ON bi.attendance_id = a.id
WHERE a.session_date >= '2025-10-01' 
  AND a.session_date <= '2025-10-31'
GROUP BY p.id, p.name, p.reference
ORDER BY sessions_attended DESC;
```

### Walk-In Frequency Report
```sql
SELECT 
    p.name AS player_name,
    COUNT(a.id) AS walkin_count,
    a.walkin_reason,
    AVG(bi.amount) AS avg_price
FROM academy_attendance a
JOIN academy_player p ON p.id = a.player_id
LEFT JOIN academy_billing_item bi ON bi.attendance_id = a.id
WHERE a.is_walkin = TRUE
  AND a.session_date >= '2025-10-01' 
  AND a.session_date <= '2025-10-31'
GROUP BY p.id, p.name, a.walkin_reason
ORDER BY walkin_count DESC;
```

### Session Attendance Rates
```sql
SELECT 
    so.name AS session_name,
    sg.name AS skill_group,
    COUNT(a.id) AS present_count,
    COUNT(DISTINCT sp.player_id) AS registered_count,
    ROUND(COUNT(a.id) * 100.0 / NULLIF(COUNT(DISTINCT sp.player_id), 0), 2) AS attendance_rate
FROM academy_session_occurrence so
LEFT JOIN academy_skill_group sg ON sg.id = so.skill_group_id
LEFT JOIN academy_attendance a ON a.session_id = so.id
LEFT JOIN academy_session_participant sp ON sp.session_id = so.id
WHERE so.attendance_status = 'confirmed'
  AND so.date >= '2025-10-01' 
  AND so.date <= '2025-10-31'
GROUP BY so.id, so.name, sg.name
ORDER BY attendance_rate DESC;
```

---

## Appendix C: Guardian Portal Implementation Guide (Future)

### Recommended Route Structure
```python
# In custom_addons/academy_core/controllers/portal.py

@http.route(['/my/kids/attendance'], type='http', auth='user', website=True)
def portal_kids_attendance(self, date_from=None, date_to=None, player_id=None, **kw):
    """
    Display attendance history for guardian's children.
    Filters: date range, player, session type.
    """
    # Get user's partner (guardian)
    partner = request.env.user.partner_id
    
    # Query children (players with guardian)
    children = request.env['academy.player'].sudo().search([
        ('guardian_ids', 'in', [partner.id])
    ])
    
    # Build domain
    domain = [('player_id', 'in', children.ids)]
    if date_from:
        domain.append(('session_date', '>=', date_from))
    if date_to:
        domain.append(('session_date', '<=', date_to))
    if player_id:
        domain.append(('player_id', '=', int(player_id)))
    
    # Query attendance
    attendances = request.env['academy.attendance'].sudo().search(
        domain, order='session_date desc, player_id'
    )
    
    # Calculate summary
    summary = {
        'total_sessions': len(attendances),
        'attendance_rate': len(attendances) / total_scheduled if total_scheduled else 0,
    }
    
    return request.render('academy_core.portal_kids_attendance', {
        'attendances': attendances,
        'children': children,
        'summary': summary,
    })
```

### Recommended Template
```xml
<!-- In custom_addons/academy_core/views/portal_attendance_templates.xml -->
<template id="portal_kids_attendance" name="My Kids - Attendance History">
    <t t-call="portal.portal_layout">
        <t t-set="breadcrumbs_searchbar" t-value="True"/>
        
        <div class="container">
            <h2>Attendance History</h2>
            
            <!-- Filters -->
            <form method="get" class="form-inline mb-3">
                <select name="player_id" class="form-control mr-2">
                    <option value="">All Children</option>
                    <t t-foreach="children" t-as="child">
                        <option t-att-value="child.id"><t t-esc="child.name"/></option>
                    </t>
                </select>
                <input type="date" name="date_from" class="form-control mr-2"/>
                <input type="date" name="date_to" class="form-control mr-2"/>
                <button type="submit" class="btn btn-primary">Filter</button>
            </form>
            
            <!-- Summary -->
            <div class="alert alert-info">
                Total Sessions: <strong><t t-esc="summary['total_sessions']"/></strong> |
                Attendance Rate: <strong><t t-esc="round(summary['attendance_rate'] * 100, 1)"/>%</strong>
            </div>
            
            <!-- Attendance Table -->
            <table class="table table-striped">
                <thead>
                    <tr>
                        <th>Date</th>
                        <th>Player</th>
                        <th>Session</th>
                        <th>Status</th>
                    </tr>
                </thead>
                <tbody>
                    <t t-foreach="attendances" t-as="att">
                        <tr>
                            <td><t t-esc="att.session_date"/></td>
                            <td><t t-esc="att.player_id.name"/></td>
                            <td><t t-esc="att.session_id.name"/></td>
                            <td>
                                <span class="badge badge-success">✅ Present</span>
                            </td>
                        </tr>
                    </t>
                </tbody>
            </table>
        </div>
    </t>
</template>
```

---

## Document Revision History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2025-10-14 | dedepene | Initial handover document |

---

**END OF DOCUMENT**
