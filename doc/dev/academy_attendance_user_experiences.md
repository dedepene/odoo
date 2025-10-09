# Academy Attendance – User Experiences & Manual Verification

## Domain Context & Design Philosophy

**Key Operational Realities:**
1. **Sessions are scheduled during season setup** - Head coach plans all group sessions when creating the season
2. **Suspensions for planned events** - Tournaments, dome setup, etc. use season suspension mechanism (already implemented)
3. **Absence = pre-emptive guardian notification** - Guardian clicks "Report Absence" button in portal before session
4. **Check-in creates attendance** - Players check themselves in on tablet/kiosk at court entrance, creating the attendance record
5. **Coach supplements check-ins** - Coach can check in players who forgot or arrived late
6. **Session has one-to-many attendees** - Each session links to actual attendees for audit trail
7. **Interrupted sessions count as complete** - If a session starts (any check-ins), it's billable even if cut short

**Design Implications:**
- **NO automatic attendance generation** - attendance records created only by check-in actions
- **Absence requests are notifications** - "My child won't attend" (no attendance record created for absent players)
- **Tablet/kiosk is primary check-in** - Self-service at court entrance
- **Coach UI for supplemental check-in** - Mobile-friendly list for quick additions
- **Billing based on actual attendance** - Only checked-in players generate billing items
- **Session-attendee relationship** - One-to-many for auditing who actually attended

---

## New/Updated Experiences

### 1. **Guardian Absence Request (Portal Form)**
   - **Purpose**: Allow guardians to notify the academy when their child will not attend a scheduled session, preventing no-show follow-up and enabling operational planning.
   - **Behavior**:
     - Guardian logs into portal and navigates to **My Kids ▸ Sessions**
     - Sees table of upcoming sessions per child with columns: Date, Time, Session, Actions
     - Each row has a **"Report Absence"** button (styled with red outline, secondary action)
     - Clicking button opens absence request form modal with fields matching the screenshot:
       - **Player name** (read-only, pre-filled from context)
       - **Session details** (date, time, session name - read-only)
       - **Reason dropdown**: Illness, Travel, Family Emergency, Other
       - **Additional Notes** (optional text area, max 500 chars)
     - **Submission deadline**: Must be submitted at least 2 hours before session start
     - On successful submission:
       - System creates `academy.absence.request` record with player, session, reason, notes, timestamp
       - **NO attendance record created** (absence is just a notification)
       - Confirmation message: "Absence reported successfully."
       - Lead coach receives notification (email/portal badge)
       - Session shows absence badge for that player in coach views
     - After submission:
       - "Report Absence" button changes to "Absence Reported" (disabled, check icon)
       - Clicking shows details: reason, submission time, notes
   - **Manual Verification**:
     1. Log in as guardian with children (e.g., "Стела Величкова")
     2. Navigate to portal **My Kids ▸ Sessions**
     3. Verify table matches screenshot format with "Report Absence" buttons
     4. Click "Report Absence" for session "Зелени - Monday 15:00" on 10/13/2025
     5. Verify form modal opens with correct pre-filled data
     6. Select reason "Illness", add note "Has a fever", submit
     7. Verify:
        - Confirmation message displayed
        - Button changes to "Absence Reported" (disabled)
        - No attendance record exists in database
        - Absence request record created
        - Lead coach receives notification
     8. Test deadline: Try to report absence for session starting in <2 hours
     9. Verify error: "Cannot report absence within 2 hours of session start."

### 2. **Tablet/Kiosk Check-In at Court Entrance (Players)**
   - **Purpose**: Provide frictionless self-service check-in for players arriving at the court, creating attendance records in real-time.
   - **Behavior**:
     - **Kiosk Setup**: Tablet mounted at court entrance, running full-screen web app
     - **Display**: Shows current and upcoming sessions on nearby courts
     - **Check-in Flow**:
       1. Player sees list of registered players for current session
       2. Player taps their name
       3. Confirmation animation (2 seconds): "✓ Checked In! Enjoy your session!"
       4. System creates `academy.attendance` record:
          - session_id, player_id, checkin_time=now, state='present', checkin_method='kiosk'
       5. Screen returns to player list
     - **Already checked in**: Shows "Already checked in at [time]" (idempotent)
     - **Absence override**: If absence request exists, check-in overrides it (player showed up)
   - **Manual Verification**:
     1. Set up tablet in kiosk mode at court entrance
     2. Navigate to kiosk URL
     3. Verify display shows current session with player roster
     4. Tap a player name
     5. Verify:
        - Confirmation animation
        - Attendance record created with state='present', method='kiosk'
        - Check in time = now
     6. Tap same player again → verify "Already checked in" message

### 3. **Coach Supplemental Check-In (Mobile/Tablet)**
   - **Purpose**: Enable coach to check in players who forgot kiosk or arrived late.
   - **Behavior**:
     - Coach opens session on mobile/tablet
     - Sees two sections: "Checked In" (with times) and "Not Yet Checked In"
     - Taps "Check In Now" button next to player
     - System creates attendance with checkin_method='coach_manual'
     - **Reported absences** shown separately for awareness
     - No ability to mark "absent" - only add check-ins
   - **Manual Verification**:
     1. Log in as coach on mobile
     2. Open current session
     3. Verify display shows checked-in players and those not yet checked in
     4. Tap "Check In Now" for a player
     5. Verify attendance record created with method='coach_manual'

### 4. **Session Attendee Audit View (Admin/Head Coach)**
   - **Purpose**: Provide audit trail of who actually attended each session.
   - **Behavior**:
     - Session form has **Attendees** tab showing one-to-many relationship
     - Lists all checked-in players with times, methods, billing amounts
     - Shows absence requests separately
     - Identifies "no-shows" (registered but no check-in, no absence)
     - Export to CSV for record-keeping
   - **Manual Verification**:
     1. Open completed session
     2. View **Attendees** tab
     3. Verify shows all check-ins with details
     4. Verify absence requests listed separately
     5. Verify no-shows identified
     6. Export and verify CSV data

### 5. **Billing Integration - Attendance-Driven Invoicing**
   - **Purpose**: Bill only players who actually attended (checked in).
   - **Behavior**:
     - Monthly billing cron queries attendance records (state='present')
     - Creates billing items only for check-ins
     - **Absence requests** → No attendance → No billing
     - **No-shows** → No attendance → No billing (but flagged for follow-up)
     - Each billing item links to attendance record for traceability
   - **Manual Verification**:
     1. Complete session with 8 check-ins, 1 absence, 3 no-shows
     2. Run billing cron
     3. Verify 8 billing items created (only for check-ins)
     4. Verify no billing for absences or no-shows
     5. Verify traceability: billing item → attendance → session

### 6. **Interrupted Session Handling**
   - **Purpose**: Treat started sessions as complete for billing even if cut short.
   - **Behavior**:
     - Session interrupted (rain) after some check-ins
     - Coach clicks "Mark Session Complete"
     - All checked-in players billed (full amount)
     - No refunds or makeup sessions
   - **Manual Verification**:
     1. Check in 8 players
     2. Mark session complete early (before scheduled end)
     3. Verify billing items created for all 8 at full price

### 7. **Emergency Session Cancellation**
   - **Purpose**: Cancel sessions before they start (rare: severe weather).
   - **Behavior**:
     - Hidden in emergency actions (requires admin/head coach)
     - Confirmation dialog with mandatory reason
     - **Blocked if any check-ins exist** (can't cancel started session)
     - Sends guardian notifications
   - **Manual Verification**:
     1. Try to cancel session with no check-ins → Success with notification
     2. Try to cancel session with check-ins → Error: "Cannot cancel - mark as completed"

## Success Criteria
- ✅ Guardian portal matches screenshot with "Report Absence" buttons per session
- ✅ Tablet/kiosk check-in creates attendance records via player self-service
- ✅ Coach can supplement check-ins for forgotten/late players
- ✅ Session shows one-to-many attendee relationship for audit
- ✅ Billing only for checked-in players (no-shows and absences not charged)
- ✅ Interrupted sessions billed normally when marked complete
- ✅ Cancellation secured and blocked if session started

## Design Principles
1. **Check-in driven**: Records created by actual check-ins only
2. **Absence is notification**: Pre-emptive notice, no attendance record
3. **No-show = no billing**: Not charged, but flagged for follow-up
4. **Coach supplements, doesn't lead**: Kiosk is primary
5. **Audit via relationship**: One-to-many session→attendees
6. **Interruption = completion**: Started = billable

Document and share any deviations from these experiences.
