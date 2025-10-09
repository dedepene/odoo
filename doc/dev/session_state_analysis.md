# Session State Model Analysis: Domain Reality vs. State Design

## Executive Summary

**Current Implementation:** Sessions have 3 states: `planned`, `suspended`, `completed` (with `cancelled` as a 4th rarely-used state).

**Initial Proposal (REJECTED):** Add `draft` and `confirmed` states to create a 5-state model with explicit confirmation workflow.

**Domain Reality (from Academy Operations):**
- Sessions are **scheduled to happen** - once created by cron, they are committed
- Cancellations are **RARE** (poor weather only, and only when dome is down)
- Season suspensions handle planned interruptions (dome setup, tournaments)
- A session that starts but is interrupted (rain) is **treated as complete** for billing purposes

**Revised Approach:** The current model is actually **correct** but needs operational interpretation adjustment:
- `planned` = scheduled and committed (attendance records created immediately)
- `suspended` = season-level suspension (dome, tournaments) - already implemented
- `cancelled` = emergency-only operation (rare weather cancellations, requires special permissions)
- `completed` = session time has passed (regardless of whether it ran full duration)

**Verdict:** The current 3-state model is **sufficient**. The initial proposal was based on incorrect assumptions about cancellation frequency. This document explains why the simpler model is better for this domain.

---

## Domain Reality: How the Academy Actually Operates

### Key Fact 1: Sessions Are Committed When Scheduled
**Reality:** Once the cron generates a session, it **will happen** unless extraordinary circumstances intervene.

**Why:**
- Coaches are scheduled and committed
- Courts are reserved
- Guardians expect consistency (same day/time weekly)
- Season suspensions handle all planned interruptions (dome setup, tournaments, facility maintenance)

**Implication:** Sessions don't need a "tentative" phase. They're born committed.

---

### Key Fact 2: Cancellations Are Rare Emergencies
**Reality:** Cancellations happen only for:
- Severe weather (outdoor courts, no dome)
- Emergency situations (coach illness at last minute, facility emergency)

**Frequency:**
- Winter (dome up): ~0 cancellations per week
- Summer (outdoor): ~0-2 cancellations per month (severe weather)

**Implication:** Cancellation should be designed as an **emergency operation**, not a routine workflow step.

---

### Key Fact 3: Interrupted Sessions Count as Complete
**Reality:** If a session starts and is interrupted (e.g., rain after 20 minutes), it's **treated as complete** for:
- Billing purposes (guardians are charged full amount)
- Attendance records (players marked "present" stay present)
- Coach compensation (coach is paid for the session)

**Rationale:**
- Coach showed up and started teaching
- Kids got value (even if shortened)
- Rescheduling makeup sessions creates more complexity than value

**Implication:** The system doesn't need to track "partial completion" - a session is either cancelled (didn't start) or completed (started, regardless of duration).

---

## Why Draft/Confirmed States Are NOT Needed

### Problem with the Initial Proposal
The draft/confirmed model was designed for a scenario where:
- ❌ Sessions are frequently cancelled during planning
- ❌ Sessions need administrative review before commitment
- ❌ Guardians can't rely on the schedule until confirmed

**But the academy reality is:**
- ✅ Sessions are rarely cancelled
- ✅ Cron-generated sessions are already validated (template defines recurring pattern)
- ✅ Guardians rely on the schedule being stable (same sessions every week)

### Unnecessary Complexity
Adding draft/confirmed would require:
- Admin to manually confirm 100+ sessions every week (busywork)
- Guardians to check if sessions are "confirmed" vs "tentative" (confusion)
- Attendance records delayed until confirmation (breaks absence request flow)
- Extra state transitions with no business value

---

## Revised State Model (Current Model is Correct)

### State Definitions

#### **planned** (Default State)
**Meaning:** "This session is scheduled and will happen."

**Characteristics:**
- Created by cron with this state
- Visible to guardians immediately
- Attendance records created immediately (on next cron or trigger)
- QR codes can be generated
- Guardians can submit absence requests
- Billing pipeline includes these sessions

**Duration:** From creation until session end time passes

**Transition to completed:** Automatic (cron runs daily, marks sessions where date_end < now as 'completed')

---

#### **suspended** (Season-Level Interruption)
**Meaning:** "This session is part of a season suspension window."

**Characteristics:**
- Applied by season suspension mechanism (already implemented)
- Used for: dome setup period, tournaments, facility renovations
- Planned in advance (not emergency)
- May revert to 'planned' if suspension removed
- Attendance records preserved (may be deleted or kept depending on suspension policy)

**Duration:** Duration of suspension window

**Transition to planned:** When suspension window removed or expires

---

#### **cancelled** (Emergency Only)
**Meaning:** "This session did not happen due to emergency circumstances."

**Characteristics:**
- **Requires special permission** (site admin, head coach only)
- **Confirmation dialog required:** "Are you sure? This will notify all guardians and adjust billing."
- **Audit trail:** Who cancelled, when, reason (required field)
- **Attendance handling:**
  - All 'expected' attendance → 'abs_notified' (no charge)
  - If any 'present' attendance exists → error: "Session already started, cannot cancel. Mark as completed instead."
- **Guardian notification:** Automatic email/portal notification sent
- **Irreversible:** Cannot un-cancel (data integrity)

**Use cases:**
- Severe weather before session start
- Emergency facility closure (power outage, equipment failure)
- Coach unable to attend (illness) and no substitute available

**Frequency:** < 5 per year

---

#### **completed** (Final State)
**Meaning:** "This session occurred (or started and was interrupted)."

**Characteristics:**
- Applied automatically (cron) when date_end passes
- Applied manually if session started but interrupted (coach marks complete)
- **Billing:** All 'present' attendance records generate billing items
- **Immutable:** Once completed, cannot edit time/date/participants (data integrity)
- **Attendance locked:** No further attendance changes (except admin override for corrections)

**Rule:** If any player has state='present', session CANNOT be cancelled - it must be marked completed.

---

## Operational Workflows

### Normal Weekly Flow (99% of sessions)

```
Sunday 00:00: Cron generates week's sessions
            ↓
     State = 'planned'
            ↓
Attendance records created immediately
            ↓
Guardians see sessions in portal
            ↓
Guardians can submit absence requests
            ↓
QR codes available for check-in
            ↓
Session occurs (Mon-Fri)
            ↓
Coach marks attendance during/after session
            ↓
Next day cron: date_end passed
            ↓
State = 'completed'
            ↓
Billing cron processes 'present' attendance
```

**No manual intervention required** - fully automated.

---

### Emergency Cancellation Flow (rare)

```
Monday 13:00: Severe weather forecast
            ↓
Admin evaluates: Cancel Tuesday 14:00 session?
            ↓
Admin opens session form
            ↓
Clicks "Cancel Session" (red button, confirmation required)
            ↓
System shows confirmation dialog:
  "Cancel session: Group Tennis - Green Ball?
   • 12 players will be notified
   • All attendance records will be marked absent (notified)
   • Billing will exclude this session
   • This action cannot be undone
   
   Reason: [Required text field]
   
   [Cancel Action] [Confirm Cancellation]"
            ↓
Admin enters reason: "Severe weather - tornado warning"
            ↓
System processes:
  • Set state = 'cancelled'
  • Update all attendance: state = 'abs_notified'
  • Send guardian notifications (email + portal)
  • Post chatter message with audit trail
            ↓
Guardians receive notification immediately
```

**Requires:** Admin/head coach permission, reason, confirmation

**Frequency:** Monthly at most (summer), zero (winter with dome)

---

### Interrupted Session Flow (session starts but doesn't complete)

```
Tuesday 14:00: Session starts, coach checks in players
            ↓
14:05: 8 of 12 players marked 'present'
            ↓
14:20: Sudden heavy rain, coach ends session early
            ↓
Coach options:
  Option A: Mark remaining players 'abs_unnotified' and let cron mark completed
  Option B: Click "Mark Session Complete" button immediately
            ↓
State = 'completed' (either way)
            ↓
Billing: 8 players charged (marked present)
            ↓
No refunds, no makeup session needed
```

**Rule:** Once ANY attendance is marked 'present', the session cannot be cancelled - it's treated as having occurred.

---

## GUI Design Implications

### Session Form - Action Buttons

**Prominent (Normal Operations):**
```
[Generate QR Code]  [Mark Complete]  [View Attendance]
```

**Hidden/Restricted (Emergency Only):**
```
⚠ Administrative Actions
[Cancel Session]  ← Red button, requires confirmation + reason
```

**Visual Design:**
- Normal actions: Blue/green buttons, top of form
- Cancel action: Red button, collapsed section "Emergency Actions" or hamburger menu
- Cancel requires: Confirmation dialog with scary warning, mandatory reason field, audit trail display

---

### Session List View - Bulk Actions

**Available:**
- Generate QR Codes (bulk)
- Export to CSV
- Mark as Complete (bulk, for past sessions)

**NOT Available:**
- Bulk cancel (too dangerous, cancellation should be one-at-a-time with deliberation)

---

### Guardian Portal - Session Display

**Show immediately:**
- All 'planned' sessions (no "tentative" label needed)
- Session details: time, court, coach, skill group

**No "confirmation pending" indicators** - sessions are reliable

**If cancelled:**
- Session marked with strikethrough and red badge: "CANCELLED - Severe weather"
- Notification at top of portal: "1 session was cancelled. You will not be charged."

---

## Attendance Record Generation Trigger

### Original Proposal (REJECTED)
Create attendance records only when session confirmed (manual admin action).

**Problem:** Requires admin to confirm 100+ sessions weekly (busywork).

---

### Revised Approach (CORRECT)
Create attendance records **immediately when session is scheduled**.

**Trigger Options:**

**Option A: Same cron that creates sessions**
```python
def _generate_sessions(self):
    sessions = self._create_session_occurrences()
    for session in sessions:
        session._generate_attendance()  # Immediate
    return sessions
```

**Option B: Separate cron (runs 5 minutes after generation cron)**
```python
@api.model
def cron_generate_attendance_for_new_sessions(self):
    new_sessions = self.search([
        ('state', '=', 'planned'),
        ('attendance_count', '=', 0),  # No attendance yet
        ('date_start', '>', fields.Datetime.now())  # Future session
    ])
    for session in new_sessions:
        session._generate_attendance()
```

**Recommendation:** Option A (immediate) - simpler, one cron does everything.

---

### Handling Cancellations After Attendance Created

**Not a problem** because:
1. Cancellations are rare (< 5 per year)
2. Cancellation process explicitly handles attendance cleanup:
   ```python
   def action_cancel_session(self):
       if self.attendance_ids.filtered(lambda a: a.state == 'present'):
           raise UserError("Cannot cancel - session has already started. Mark as completed instead.")
       
       # Update all expected/absent attendance to abs_notified (no charge)
       self.attendance_ids.write({'state': 'abs_notified'})
       self.state = 'cancelled'
       self._notify_guardians_cancellation()
   ```

3. Billing query simply excludes cancelled sessions:
   ```python
   billing_attendance = self.env['academy.attendance'].search([
       ('state', '=', 'present'),
       ('session_id.state', '!=', 'cancelled')  # Simple filter
   ])
   ```

**Data integrity maintained** - no orphaned records, clean cancellation handling.

---

## Billing Rules (Simplified)

### Rule 1: Present = Billable
If attendance.state = 'present', create billing item (regardless of session duration).

### Rule 2: Session Cancellation = No Charges
If session.state = 'cancelled', all attendance set to 'abs_notified' → no billing items created.

### Rule 3: Interrupted Session = Full Billing
If session started (has 'present' attendance) then got rained out, those present players are billed normally.

**Example:**
```
Session: Tuesday 14:00, 12 players registered
14:05 - Coach checks in 8 players (state='present')
14:20 - Heavy rain, session ends
14:25 - Coach marks session complete

Result:
- 8 players billed (marked present before rain)
- 4 players not billed (never showed up or marked)
- No refunds, no partial charges - clean outcome
```

---

## Comparison: Initial Proposal vs. Revised Approach

| Aspect | Initial Proposal (draft/confirmed) | Revised Approach (planned only) |
|--------|-----------------------------------|--------------------------------|
| **State Count** | 5 states (draft, confirmed, suspended, cancelled, completed) | 4 states (planned, suspended, cancelled, completed) |
| **Admin Work** | Confirm 100+ sessions weekly | Zero manual work |
| **Attendance Trigger** | Manual confirmation | Automatic (cron) |
| **Guardian Experience** | Wait for confirmation, see "tentative" labels | See reliable schedule immediately |
| **Cancellation Handling** | Same complexity either way | Emergency-only operation |
| **Complexity** | Higher (extra state, extra transitions, extra cron) | Lower (current model + minor tweaks) |
| **Business Value** | Solves a problem that doesn't exist | Matches actual operations |

---

## What Actually Needs to Change

### In Current Implementation

**Keep (Already Correct):**
- ✅ 'planned' as default state
- ✅ 'suspended' for season interruptions
- ✅ 'completed' as final state
- ✅ 'cancelled' as rare emergency state

**Add (New Behavior):**
- ✅ Automatic attendance generation when session created (same cron or immediate trigger)
- ✅ Cancellation requires confirmation dialog + mandatory reason
- ✅ Cancellation blocked if any attendance is 'present' (session already started)
- ✅ Guardian notification on cancellation (email + portal)
- ✅ Cron to auto-mark sessions 'completed' when date_end passes

**GUI Changes:**
- ✅ Hide/restrict "Cancel Session" button (emergency action, not prominent)
- ✅ Add "Mark Complete" button (for early completion after interruption)
- ✅ Attendance generation no longer needs explicit trigger (happens automatically)

---

## Conclusion: Simpler is Better

### The initial draft/confirmed proposal was based on incorrect assumptions:
- ❌ Assumed cancellations are frequent (they're rare)
- ❌ Assumed sessions need validation before commitment (cron already validates via templates)
- ❌ Assumed guardians can't rely on schedule (they can and do)

### The current model is actually correct, just needs operational clarity:
- ✅ 'planned' = committed and reliable (not tentative)
- ✅ Attendance created immediately (not delayed)
- ✅ Cancellation is emergency-only (not routine)
- ✅ Interrupted sessions count as complete (no partial states needed)

### Key Insight:
**Don't design for exceptions.** The academy runs smoothly 99% of the time. Sessions happen as scheduled. Cancellations are rare emergencies. The state model should reflect the normal case (smooth operations) with emergency procedures available but de-emphasized.

**Recommendation:** Keep the current 3-state model, add automatic attendance generation, improve cancellation workflow (confirmation + audit), and design GUI to reflect that cancellation is exceptional, not normal.

### Key Insight:
**Don't design for exceptions.** The academy runs smoothly 99% of the time. Sessions happen as scheduled. Cancellations are rare emergencies. The state model should reflect the normal case (smooth operations) with emergency procedures available but de-emphasized.

**Recommendation:** Keep the current 3-state model, add automatic attendance generation, improve cancellation workflow (confirmation + audit), and design GUI to reflect that cancellation is exceptional, not normal.

