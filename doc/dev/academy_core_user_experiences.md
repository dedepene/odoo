# Academy Core – User Experiences & Manual Verification

## New/Updated Experiences
1. **Academy Player Management (Site Admins & Head Coaches)**
   - Dedicated “Academy ▸ Players” workspace with tailored list/form views.
   - Automatic player code assignment (`PLR####`) and age calculation once DOB is entered.
   - Guardian linkage UI with validation prompts for missing contact data.
   - Single-click elevation to portal user when a player is ready for self-service access.

2. **Skill Group Configuration (Site Admins & Head Coaches)**
   - “Academy ▸ Configuration ▸ Skill Groups” enables defining age-banded cohorts.
   - Enforced uniqueness of group code/name prevents conflicting set-ups.
   - Age range enforcement toggles allow exceptions (e.g., advanced players promoted early).

3. **Player Elevation Workflow (Site Admins)**
   - Modal wizard collects login/email details and optionally reuses guardian portal rights.
   - Immediate portal user creation with optional welcome email dispatch.
   - Player form shows linked portal user badge to confirm status.

## Manual Verification Checklist
Follow the steps per persona to confirm the implementation.

### A. Pre-requisites
- Ensure the `academy_core` module is installed and the database has outgoing email configured (needed only to test welcome messages).

### B. Skill Group Setup
1. Navigate to **Academy ▸ Configuration ▸ Skill Groups**.
2. Create a “Green Ball” group with min age 8, max age 10, enforcement enabled.
3. Attempt to create a second group with the same code – expect a uniqueness error.
4. Edit the group to set min age greater than max age – saving should raise a validation error.

### C. Guardian Data Integrity
1. Open **Contacts** and create a new partner “Taylor Parent” with email + phone.
2. Remove the phone value and try to save – should succeed (contact form doesn’t enforce it), but note the player constraint will catch it later.

### D. Player Creation & Constraints
1. Go to **Academy ▸ Players** and create a new player:
   - Name: “Jordan Player”.
   - DOB: nine years ago.
   - Skill Group: Green Ball.
   - Guardians: add “Taylor Parent”.
   - Primary Guardian: “Taylor Parent”.
   - Provide basic contact info if desired.
2. Save – record should create with a `PLR####` reference and computed age.
3. Edit the same player, remove all guardians, and click save – expect a blocking error about missing guardians.
4. Re-add guardian, but set primary guardian to a *different* contact – expect validation error.
5. Edit the guardian partner and clear both phone & mobile. Try saving the player again – expect error requiring contact details.

### E. Age Alignment Enforcement
1. Duplicate the “Jordan Player” form and change DOB to twelve years ago.
2. Try to save – expect an error indicating the player is older than the group allows.
3. Uncheck “Enforce Age Range” on the skill group and retry – save should now succeed (for exception handling).

### F. Elevation Wizard Flow
1. Ensure the guardian partner has a valid email.
2. Open the player record and click **Elevate to Portal**.
3. In the wizard, accept the default login/email, keep the welcome email enabled, and confirm.
4. After success:
   - The player form should display the portal user badge.
   - Inspect **Settings ▸ Users & Companies ▸ Users** to confirm the new user has the academy player portal group (and guardian group if selected).
5. Attempt to elevate again – the button should be hidden/inactive because a user already exists.

## Success Criteria
- Skill groups enforce data integrity (steps B3–B4).
- Player form blocks missing guardians, mismatched primary guardian, and incomplete guardian contact details (steps D3–D5).
- Age enforcement aligns with group configuration (steps E1–E3).
- Elevation wizard creates portal users with correct group memberships and prevents duplicates (steps F1–F5).

4. **Invite Guardian Workflow (Site Admins & Coaches)**
    - Purpose: Allow staff to invite a guardian (existing `res.partner`) to the portal with a single action, creating a `res.users` linked to the partner and sending an invite/reset token.
    - Behaviour:
       - Action available on `academy.player` and guardian partner form: "Invite Guardian to Portal".
       - Validates partner has an email; performs case-insensitive uniqueness check on login/email.
       - Creates `res.users` with `partner_id` = guardian partner, assigns `group_portal` and `group_academy_guardian_portal` (custom group), and calls `action_reset_password()` to send an invite.
       - Posts a chatter message on the guardian partner and the related player (if invoked from player form).
    - Manual Verification:
       1. Create a guardian partner with a valid email.
       2. Open the player form, click **Invite Guardian to Portal** next to the primary guardian.
       3. Confirm the user appears in **Settings ▸ Users & Companies ▸ Users** with portal + guardian groups.
       4. Confirm an invite email is received and that the partner form shows a portal badge.
       5. Attempt to invite the same guardian again — expect a clear error about existing login/email.

5. **Attendance Management (Coaches, Guardians, Site Admins)**
    - Purpose: Enable efficient attendance tracking through coach-validated prepopulated rosters at session start, with guardian absence notifications and comprehensive billing integration.
    
    **A. Guardian Absence Notification (Portal Users)**
    - Behaviour:
       - Guardians log into portal and navigate to **My Kids ▸ Sessions**.
       - Each upcoming session displays a **"Report Absence"** button.
       - Clicking opens a modal with:
         - Pre-filled player, session, date/time (read-only)
         - Reason dropdown (Illness, Travel, Family Emergency, Other)
         - Optional notes field (max 500 chars)
       - Submission validates cutoff window (default: 2 hours before session start).
       - Creates `academy.absence.request` record; does NOT create attendance record.
       - Posts chatter message on session; sends notification to lead coach.
       - Button changes to "Absence Reported" (disabled) after submission.
    - Manual Verification:
       1. Log in as guardian, navigate to **My Kids ▸ Sessions**.
       2. Click **"Report Absence"** for an upcoming session (>2 hours away).
       3. Select reason "Illness", add note "Has a fever", submit.
       4. Verify button changes to "Absence Reported" (disabled, with check icon).
       5. Verify coach receives notification (check lead coach's email or portal notifications).
       6. Attempt to submit absence within 2-hour cutoff – expect blocking error.
       7. Verify absence request appears in backend (**Academy ▸ Attendance ▸ Absence Requests**).
       8. Verify NO attendance record created for the absence.
    
    **B. Coach Attendance Validation (Mobile/Tablet Interface)**
    - Behaviour:
       - Coach opens Academy app on mobile/tablet at session start.
       - Navigates to **Today's Sessions** → selects current session.
       - System displays prepopulated attendance roster:
         - All registered players checked (☑️) by default (presumed present).
         - Pre-reported absences displayed separately (not in main roster).
       - Coach reviews physical attendance and taps players who are ABSENT to uncheck (❌).
       - Coach can add walk-in players (academy members not in roster) via **"Add Walk-In Player"**.
       - Walk-in search allows finding by name/code; adding creates participation + attendance.
       - Tapping **"Confirm Attendance"** creates attendance records ONLY for checked (☑️) players.
       - Confirmation updates session status to 'confirmed'; posts chatter with counts.
    - Manual Verification:
       1. Log in as coach, navigate to **Academy ▸ Today's Sessions**.
       2. Select an active session (within 15 min of start time).
       3. Verify all registered players display with ☑️ (checked) by default.
       4. Verify pre-reported absences display separately (not in checklist).
       5. Tap 2-3 players to mark absent (checkbox changes to ❌).
       6. Tap **"Add Walk-In Player"**, search for unregistered academy player.
       7. Select player, choose reason (e.g., "Skill level advancement"), confirm.
       8. Verify walk-in appears in roster with ☑️ and walk-in indicator (🚶).
       9. Tap **"Confirm Attendance"**.
       10. Verify confirmation dialog shows counts (Present: X, Absent: Y, Pre-reported: Z).
       11. Confirm and verify:
           - Session status changes to 'confirmed' in backend.
           - Attendance records created ONLY for checked players (query `academy.attendance`).
           - NO attendance records for unchecked (absent) or pre-reported absence players.
           - Chatter message documents confirmation with counts.
       12. Attempt to confirm before session start window (>15 min early) – expect warning.
       13. Attempt to re-confirm already confirmed session – expect error.
    
    **C. Attendance-Driven Billing (System/Site Admins)**
    - Behaviour:
       - Monthly billing cron queries confirmed sessions for unbilled attendances.
       - Creates `academy.billing.item` ONLY for players with attendance records (coach-confirmed present).
       - Pricing determined by session type:
         - Group session (regular): $25
         - Individual session: $60
         - Physical training: $20
         - Walk-in trial: $0 (free)
       - Walk-in billing items flagged for admin review (special pricing).
       - Billing items grouped by primary guardian → draft invoices created.
       - Invoice lines trace back to attendance records (full audit trail).
       - Players with absence requests NOT billed (no attendance record exists).
       - Coach-marked absences NOT billed (no attendance record created).
       - No-shows NOT billed (no attendance, no absence request).
    - Manual Verification:
       1. Confirm 2-3 sessions with mixed attendance (some present, some absent, some pre-reported).
       2. Run billing cron manually: **Academy ▸ Billing ▸ Run Monthly Billing**.
       3. Navigate to **Academy ▸ Billing ▸ Billing Items**.
       4. Verify billing items exist ONLY for coach-confirmed present players.
       5. Verify NO billing items for:
          - Pre-reported absences
          - Coach-marked absences (unchecked players)
          - No-shows (players not marked either way)
       6. Verify walk-in billing items display walk-in indicator and correct pricing (trial=$0).
       7. Verify each billing item links to source attendance record (Many2one field).
       8. Navigate to **Invoicing ▸ Customer Invoices** (drafts).
       9. Verify invoices grouped by guardian with correct line items.
       10. Verify invoice lines indicate walk-in sessions ("🚶 Walk-In" suffix).
       11. Attempt to re-bill same attendances – verify prevention (billing_item_id already set).
    
    **D. Guardian Portal Attendance View (Portal Users)**
    - Behaviour:
       - Guardians view attendance history in portal: **My Kids ▸ Attendance History**.
       - Table displays past sessions with attendance status per child.
       - Filters: Date range, player, session type.
       - Status indicators: Present (✅), Absent-Reported (📢), Absent-Unreported (❌), No session (blank).
       - Monthly summary: Total sessions scheduled, attended, absent (reported vs unreported), attendance %.
    - Manual Verification:
       1. Log in as guardian with multiple children.
       2. Navigate to **My Kids ▸ Attendance History**.
       3. Verify table displays all past sessions for guardian's children.
       4. Verify status icons match backend attendance records.
       5. Verify pre-reported absences show as "Absent-Reported" (📢).
       6. Verify coach-marked absences (unchecked during confirmation) show as "Absent-Unreported" (❌) or blank (no record).
       7. Apply date filter (e.g., current month) – verify results update.
       8. Verify monthly summary calculates correctly (attendance %).
       9. Verify guardian can ONLY see their own children's attendance (not other players).
    
    **E. Admin Attendance Reporting (Site Admins)**
    - Behaviour:
       - Admins access comprehensive attendance reports: **Academy ▸ Reports ▸ Attendance**.
       - Reports available:
         - Player attendance summary (monthly, per player)
         - Session attendance rates (by skill group, session type)
         - Absence analysis (reported vs unreported, reasons)
         - Walk-in frequency (by player, reason distribution)
       - Export to CSV/Excel for external analysis.
       - Pivot views for ad-hoc slicing (by coach, court, time slot).
    - Manual Verification:
       1. Navigate to **Academy ▸ Reports ▸ Attendance ▸ Player Summary**.
       2. Select current month, verify report shows all players with attendance metrics.
       3. Verify metrics: Total sessions, present count, absence (reported vs unreported), attendance %.
       4. Export to CSV, verify data integrity (matches backend query).
       5. Navigate to **Academy ▸ Reports ▸ Attendance ▸ Absence Analysis**.
       6. Verify report groups absences by reason (Illness, Travel, etc.).
       7. Verify reported absences (via portal) vs unreported (coach-marked) distinguished.
       8. Navigate to **Academy ▸ Reports ▸ Attendance ▸ Walk-In Frequency**.
       9. Verify walk-ins listed with player, session, reason, billing status.
       10. Verify pivot view allows grouping by skill group, coach, session type.
       11. Test record rules: Create a non-admin user (coach) and verify they see only their assigned players' reports.


Document and share any deviations—these mark regressions against the core deliverables.
