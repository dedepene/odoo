# Tennis Academy – User Stories

## Document Context & Design Philosophy

**Operational Realities:**
- Sessions are **committed when scheduled** by cron (not tentative/draft)
- Cancellations are **rare emergencies** (<5 per year, severe weather only)
- Interrupted sessions (rain) are **treated as complete** for billing
- Season suspensions handle planned interruptions (dome, tournaments)

**State Model:**
- `planned` = scheduled and committed (attendance created immediately)
- `suspended` = season-level suspension (existing mechanism)
- `cancelled` = rare emergency (requires confirmation + reason)
- `completed` = session occurred or started (billing applies)

**No draft/confirmed workflow** - sessions are born committed, attendance generated immediately.

---

## 1. Player Elevation Wizard (Managed Player ➜ Authenticated User)

### 1.1 Purpose
Enable selective promotion of a managed player (no login) into an authenticated portal user without duplicating partner data. Supports autonomy for older / competitive players while preserving guardian oversight and historical traceability.

### 1.2 Actors
| Role | Responsibility |
|------|----------------|
| Site Admin | Approves and executes elevation; defines policy parameters |
| Head Coach | May elevate players (permissions) based on maturity / program need |
| Primary Guardian (optional) | Can request elevation (if policy allows) |
| Player (target) | Gains limited portal access post elevation |
| System | Validates policy, creates `res.users`, assigns groups, sends onboarding |

### 1.3 Preconditions
- Player record (`academy.player`) exists, active, with: DOB, ≥1 guardian, primary_guardian set, skill group set.
- Player has no linked `res.users` (i.e., partner has no user).
- Policy constraints satisfied (age threshold, allowed skill groups, feature enabled).
- No pending unapproved elevation request (if request workflow used).

### 1.4 Triggers
1. Head Coach clicks "Elevate to Portal User" button on player form.
2. Site Admin runs batch action from player list (multi-select).
3. Guardian submits a portal "Request Direct Access" (creates request, later approved via wizard).
4. Scheduled review job suggests eligible players (optional future automation).

### 1.5 Happy Path Flow
1. User opens elevation wizard (modal). 
2. Wizard pre-populates: Player, age (computed), suggested email (player partner email or empty), proposed login.
3. User edits/enters email (must be unique), confirms options (send welcome, force reset).
4. System validates policy (age, skill group). 
5. On submit: 
   - Create `res.users` with partner_id pointing to existing partner.
   - Assign minimal groups: `group_portal`, `group_academy_player_portal`.
   - Generate reset token; optionally send welcome email.
   - Stamp `elevation_date` on player, post chatter message.
6. Wizard closes; user sees updated player status (portal enabled badge).

### 1.6 Alternative / Error Paths
| Condition | Outcome |
|-----------|---------|
| Age < min threshold | ValidationError; wizard remains open |
| Skill group not allowed | ValidationError; instruct coach to adjust / override policy |
| Email missing | Required field error |
| Email/login already used | ValidationError; user prompted to modify |
| Player already elevated | Action hidden / disabled |
| Guardian tries elevation (policy forbids) | Display informational denial message |
| Batch: some succeed, some fail | Summary dialog enumerating failures with reasons |

### 1.7 Postconditions
- New `res.users` linked to existing partner record.
- Player accessible via portal (scoped views only).
- Audit log entry created (mail.message with subtype `academy_mt_player_elevated`).
- Optional welcome/reset email dispatched.
- Billing, attendance, guardian relationships unchanged.

### 1.8 Data Entities & Fields
| Entity | Fields Impacted / Added |
|--------|-------------------------|
| academy.player | elevation_date (Datetime), (implicitly: derived has_user flag) |
| res.users | login, email, partner_id, groups_id |
| ir.config_parameter | `academy_core.elevation_min_age`, `academy_core.elevation_allowed_skill_groups`, `academy_core.allow_guardian_request` |
| mail.template | `academy_player_elevation_welcome` |
| wizard model | player_id, email, login, send_welcome, force_reset |

### 1.9 Security & Permissions
- Button / action visible to groups: head coach, site admin (configurable extension to allow guardian request initiation—request not direct creation).
- Guardian request uses separate model `academy.player.elevation.request` (optional future) with simple states: draft → approved → executed.
- Record rules ensure a guardian can only request elevation for their own child players.

### 1.10 Business Rules / Validation
- Age calculation: `age_years = floor((today - dob) / 365.25)`.
- Enforce allowed skill groups list (empty list means all).
- Unique login/email (case-insensitive) across active users.
- Elevation atomic; rollback on any failure (transaction integrity).

### 1.11 Auditing
- Chatter message body: `Player elevated to portal user (User <id>) by <operator> on <timestamp>.`
- Log includes old/new access state (no user → user_id).
- Optional model to track metrics (future): `academy.player.elevation.metric`.

### 1.12 UX Wireframe (Textual)
Modal: "Elevate Player to Portal User"
Sections:
1. Player Summary: Name | Age | Skill Group | Lead Coach
2. Credentials: Email (input), Username (auto = email)
3. Access: Groups (read-only list; maybe hyperlink to docs)
4. Options: [x] Send Welcome Email, [x] Force Password Reset
Footer: Cancel | Elevate (primary)
Inline warnings: Age threshold, missing progress report (optional hint)

### 1.13 Sequence (Textual)
User → Wizard: Open
Wizard → Config: Fetch policy params
Wizard → Player: Read DOB, guardians, skill group
User → Wizard: Submit
Wizard → Validation: Age + skill group + uniqueness
Wizard → Users: Create `res.users`
Wizard → Users: Assign groups
Wizard → Mail: Send template (optional)
Wizard → Player: Write elevation_date
Wizard → Chatter: Post message
Wizard → User: Close + refresh

### 1.14 Pseudo Code (Wizard Skeleton)
```python
class PlayerElevationWizard(models.TransientModel):
    _name = 'academy.player.elevation.wizard'
    _description = 'Player Elevation Wizard'

    player_id = fields.Many2one('academy.player', required=True)
    email = fields.Char(required=True)
    login = fields.Char()
    send_welcome = fields.Boolean(default=True)
    force_reset = fields.Boolean(default=True)

    @api.onchange('email')
    def _onchange_email(self):
        if self.email and not self.login:
            self.login = self.email.lower()

    def action_elevate(self):
        self.ensure_one()
        player = self.player_id
        player._check_elevation_policy()
        login_lower = self.login.lower()
        if self.env['res.users'].sudo().search_count([('login', '=', login_lower)]):
            raise ValidationError('Login already in use.')
        user = self.env['res.users'].sudo().create({
            'name': player.partner_id.name,
            'login': login_lower,
            'email': self.email,
            'partner_id': player.partner_id.id,
            'groups_id': [(6, 0, self._default_player_groups())],
        })
        if self.force_reset:
            user.action_reset_password()
        elif self.send_welcome:
            self._send_welcome_mail(user)
        player.write({'elevation_date': fields.Datetime.now()})
        player.message_post(body=f'Player elevated to portal user (User #{user.id}).')
        return {'type': 'ir.actions.act_window_close'}
```

### 1.15 Policy Check Example
```python
def _check_elevation_policy(self):
    cfg = self.env['ir.config_parameter'].sudo()
    min_age = int(cfg.get_param('academy_core.elevation_min_age', 13))
    allowed = cfg.get_param('academy_core.elevation_allowed_skill_groups', '')
    if self.age_years < min_age:
        raise ValidationError(f'Min age {min_age} not met.')
    if allowed:
        allowed_list = [c.strip() for c in allowed.split(',') if c.strip()]
        if self.skill_group_id.code not in allowed_list:
            raise ValidationError('Skill group not permitted for elevation.')
```

### 1.16 Edge Cases
| Case | Handling |
|------|----------|
| Duplicate email across siblings | Prompt alternate or tagged email (e.g. `child+name@example.com`) |
| Player demotion | Archive user; keep player; log chatter "Portal access revoked" |
| Batch partial failures | Aggregate messages; show summary wizard; log each failure |
| Guardian attempt outside policy | Provide clear denial + link to policy docs |

### 1.17 Acceptance Criteria
| ID | Criterion |
|----|-----------|
| AC1 | Elevating a valid player creates one and only one user bound to existing partner |
| AC2 | Under-age attempt blocked with specific age message |
| AC3 | Attendance, billing, guardians unchanged post elevation |
| AC4 | Player can log in and only see own data (sessions, attendance, progress) |
| AC5 | Chatter log entry always present |
| AC6 | Optional welcome/reset email delivered when configured |
| AC7 | Batch action processes N players with partial success reporting |
| AC8 | Re-elevation attempt prevented |

### 1.18 Non-Functional Notes
- Transactional: If mail send fails, user still created; log warning.
- Performance: O(1) per elevation; batch limited by email uniqueness checks.
- Security: No plain-text password stored; relies on token reset channel.

### 1.19 Future Extensions
- Guardian approval workflow & digital consent capture.
- Access scope matrix (attendance editing vs view-only).
- Player self-assessment appended to progress reports pre-publication.
- API endpoint for federation integration auto-elevating qualifying players.

---
(Additional user stories can be appended as modules mature.)

---

# 2. Scheduling & Calendar Management

The following user stories cover generation and ongoing management of recurring group training, individual sessions, court allocation, absence handling, seasonal suspension, and permission-scoped calendar visibility.

## 2.1 Weekly Group Schedule Definition (Head Coach)

### 2.1.1 Purpose
Provide a structured way for a Head Coach (or delegated Site Admin) to define a season-long weekly template of recurring group practice sessions per skill group (Red, Orange, Green, Hard, Advanced) without manually creating each dated event.

### 2.1.2 Actors
| Role | Responsibility |
|------|----------------|
| Head Coach | Creates / edits weekly group schedule template |
| Site Admin | Override + global conflict resolution |
| Coach (non-head) | Read-only view of global template (may propose changes via chatter) |
| System | Expands template into recurring session instances |

### 2.1.3 Preconditions
- Skill groups configured and active.
- Courts resource list configured (`academy.court`).
- Season configuration exists (`academy.season`) with start_date, end_date, active flag.
- No overlapping active season (enforced uniqueness / exclusivity).

### 2.1.4 Triggers
1. Head Coach opens "Season Schedule Wizard" from season form.
2. Coach edits an existing group’s slot (time/courts) and saves.
3. Site Admin re-generates future occurrences after a structural change (e.g., time shift mid-season) with selective update options.

### 2.1.5 Happy Path Flow
1. Wizard displays matrix (Days vs Skill Groups) with proposed default times (empty initially).
2. Coach selects: Skill Group = Green, Days = Mon/Wed/Fri, Time = 17:00–19:00, Session Type = Tennis Skills, Follow-up PA = 19:00–20:00 (flag adds chained session record).
3. Assign Courts: 1,3,5 (multi-select with availability check).
4. Repeat for remaining groups (Reds/Oranges Tue/Thu etc.).
5. Submit – system validates overlaps per court + group + coach constraints.
6. System generates recurring session definitions (`academy.session.template`) and expands dated occurrences for season window (`academy.session.occurrence`).
7. Confirmation summary lists counts per group and any skipped days (e.g., holidays placeholder for later integration).

### 2.1.6 Alternative / Error Paths
| Condition | Outcome |
|-----------|---------|
| Court conflict (same court, overlapping time) | Block save; highlight conflicting cells (list conflicting template refs) |
| Time end <= start | ValidationError on row |
| Attempt to modify past-dated portion mid-season | Offer radio choice: (a) future occurrences only (b) all (c) cancel |
| Season inactive | Wizard disabled with message |
| Missing courts | Soft warning; allow draft state until courts set |

### 2.1.7 Postconditions
- Templates persisted, occurrences generated (one record per date per session type within season date range, excluding inactive days).
- Chained PA/Strength sessions flagged `is_follow_up = True` with `parent_session_id` link.
- Audit chatter on season: summary with counts per group.

### 2.1.8 Data Entities & Fields
| Entity | Fields (new / impacted) |
|--------|-------------------------|
| academy.season | name, start_date, end_date, active, suspension_state (normal/suspended) |
| academy.session.template | season_id, skill_group_id, day_of_week (0–6), start_time, end_time, session_type (selection), court_ids (m2m), coach_id (optional / auto-assign later), follow_up_session (bool) |
| academy.session.occurrence | template_id, date, start_datetime, end_datetime, court_ids (snapshot), session_type, skill_group_id, coach_id, state (planned/cancelled/completed), visibility_scope |
| academy.court | name, surface_type (optional), is_indoor (bool) |
| mail.message | chatter on season & template changes |

### 2.1.9 Security & Permissions
- Create/update templates: Head Coach, Site Admin.
- Read-only: All Coaches (group_coach) for planning.
- No direct guardian edit; guardians only see published occurrences.

### 2.1.10 Business Rules
- Court overlap rule: (court, start < other.end AND end > other.start) disallowed within same date.
- Session types (enum): tennis, group_physical, individual_skills, individual_physical (extensible via selection).
- Follow-up generation duplicates base template with offset start = previous end.
- Occurrence generation stops at season.end_date inclusive.

### 2.1.11 Auditing
- Each template creation logs message on season with structured JSON summary (for diff tooling) or formatted bullet list.
- Re-generation logs before/after counts.

### 2.1.12 Edge Cases
| Case | Handling |
|------|----------|
| Daylight savings shift | Store naive local times; recompute datetimes at generation respecting timezone context |
| Season extension | New occurrences appended for new range only |
| Template deletion mid-season | Option: remove only future occurrences or mark past as historical (no unlink) |
| Court deactivation | Warn; exclude from future generation; mark existing occurrences with warning tag |

### 2.1.13 Acceptance Criteria
| ID | Criterion |
|----|----------|
| SCH1 | Generating schedule creates correct number of occurrences = (#weeks in range * selected weekdays * sessions) |
| SCH2 | Conflicting court allocations are blocked with explicit listing |
| SCH3 | Editing a template can target only future occurrences when chosen |
| SCH4 | Follow-up physical session auto-created with correct timing |
| SCH5 | Chatter log entry present after generation |

### 2.1.14 Pseudo Code (Generation Skeleton)
```python
def generate_occurrences(self):
    for tmpl in self:
        current = season.start_date
        while current <= season.end_date:
            if current.weekday() == tmpl.day_of_week:
                start_dt = datetime.combine(current, tmpl.start_time)
                end_dt = datetime.combine(current, tmpl.end_time)
                self.env['academy.session.occurrence'].create({
                    'template_id': tmpl.id,
                    'date': current,
                    'start_datetime': start_dt,
                    'end_datetime': end_dt,
                    'court_ids': [(6, 0, tmpl.court_ids.ids)],
                    'skill_group_id': tmpl.skill_group_id.id,
                    'session_type': tmpl.session_type,
                })
            current += timedelta(days=1)
```

## 2.2 Individual Session Booking (Coach ➜ Player(s))

### 2.2.1 Purpose
Allow any Coach (permissions) to schedule ad-hoc individual or small group sessions with one or more players outside the recurring group template while enforcing court availability.

### 2.2.2 Actors
| Role | Responsibility |
|------|----------------|
| Coach | Creates individual session occurrence |
| Player / Guardian | View (and optionally confirm) |
| Site Admin | Override, reassign court |
| System | Detect conflicts |

### 2.2.3 Preconditions
- Player(s) exist and active.
- Courts available in requested time range.

### 2.2.4 Flow (Happy Path)
1. Coach clicks "New Individual Session".
2. Select players (multi), propose date/time, duration, court(s), session type (individual_skills / individual_physical / tennis).
3. System runs conflict check against occurrences + templates (for same time window).
4. Save creates standalone `academy.session.occurrence` with `is_individual = True` and m2m `player_ids`.
5. Notifications (mail / portal feed) dispatched to players/guardians.

### 2.2.5 Error Paths
| Condition | Outcome |
|-----------|---------|
| Court clash | ValidationError naming conflicting occurrence(s) |
| Player already booked (double-book) | Soft warning or blocking per config flag |
| Past datetime | Block creation |

### 2.2.6 Data / Fields
Add to `academy.session.occurrence`: is_individual (bool), player_ids (m2m), booking_origin ('manual','template').

### 2.2.7 Acceptance
| ID | Criterion |
|----|----------|
| IND1 | Conflict-free save succeeds |
| IND2 | Player double-book rule enforced when enabled |
| IND3 | Guardians can view but not edit session |

## 2.3 Absence Notification (Guardian ➜ Attendance Planning)

### 2.3.1 Purpose
Permit a guardian (or elevated player) to proactively flag a future absence from a specific scheduled occurrence without needing chat-style interaction; enabling coaches to adjust planning.

### 2.3.2 Actors
| Role | Responsibility |
|------|----------------|
| Guardian / Player | Creates absence record |
| Coach | Views aggregated absence list per session |
| System | Surfaces suggested replacements (future extension) |

### 2.3.3 Preconditions
- Session occurrence exists in planned state and is in the future.
- Player is assigned to the occurrence via skill group or direct link (individual session).

### 2.3.4 Flow
1. Guardian opens session (portal calendar or list) and clicks "Report Absence".
2. Simple form with reason (selection + free-text), optional attachment (doctor note etc.).
3. System creates `academy.session.absence` with state = reported.
4. Chatter message on occurrence; coach notification email optional.
5. Coach may mark state = acknowledged.

### 2.3.5 Invite Guardian → Portal (New: Staff-invited guardian portal access)

#### Purpose
Provide a low-friction, auditable way for staff to convert an existing guardian contact (`res.partner`) into a portal user so they can use the portal to report absences, view child schedules, and receive notifications.

#### Actors
| Role | Responsibility |
|------|----------------|
| Site Admin / Head Coach | Initiates invite and configures guardian portal group membership |
| Coach / Staff | May invite guardians from player form |
| Guardian (partner) | Receives invite email and completes onboarding |

#### Preconditions
- Guardian exists as a `res.partner` with a valid email.
- No existing `res.users` with the same login/email (case-insensitive).

#### Triggers
1. Staff clicks **Invite Guardian to Portal** on a player form or guardian partner record.
2. Batch invite from a guardian list (future enhancement).

#### Happy Path Flow
1. Staff clicks invite action and confirms the email/login.
2. System validates email presence and uniqueness.
3. Create `res.users` linked to the guardian partner and add groups: `group_portal`, `group_academy_guardian_portal`.
4. System calls `action_reset_password()` to send the invite token email.
5. System posts chatter on partner and related player indicating portal access granted.
6. Guardian logs into portal and sees the child's scheduled occurrences and the "Report Absence" action.

#### Alternative / Error Paths
| Condition | Outcome |
|-----------|---------|
| Missing email | Block invite; show action to edit partner and add email |
| Email/login already used | ValidationError; suggest using different email or linking existing user |
| Shared family email (policy disallows) | Offer manual review or require unique email per guardian |

#### Postconditions
- `res.users` created and linked to partner; guardian can authenticate.
- Chatter messages created for audit trail.

#### Security & Permissions
- New technical group `group_academy_guardian_portal` (inherits `portal`) to scope guardian permissions.
- Record rules restrict guardian portal users to only see their child's occurrences and absence records.

#### Acceptance Criteria
| ID | Criterion |
|----|-----------|
| GINV1 | Invite creates one `res.users` per guardian and reuses the existing partner |
| GINV2 | Login/email uniqueness enforced (case-insensitive) |
| GINV3 | Guardian receives invite email with a reset token |
| GINV4 | After onboarding, guardian can report absence via the portal (story 2.3 flow) |


### 2.3.5 Data Model
| Entity | Fields |
|--------|--------|
| academy.session.absence | occurrence_id, player_id, reason_code, reason_note, state (reported/acknowledged/withdrawn), create_uid, create_date |

### 2.3.6 Business Rules
- Only one open absence per (player, occurrence).
- Past occurrences cannot be marked absent (use attendance correction process instead).
- Withdrawal allowed until start_datetime.

### 2.3.7 Acceptance
| ID | Criterion |
|----|----------|
| ABS1 | Guardian can record absence for eligible future session |
| ABS2 | Duplicate absence attempt blocked |
| ABS3 | Coach sees absence count badge on occurrence view |

## 2.4 Dome / Seasonal Suspension

### 2.4.1 Purpose
Temporarily suspend all scheduled (template-derived) sessions for a specified date range (e.g., indoor dome installation) without deleting underlying templates.

### 2.4.2 Flow
1. Site Admin opens Season → action "Suspend Sessions".
2. Dialog: suspension_start, suspension_end, apply_to = (group sessions only | all including individual), reason.
3. System: marks occurrences in range as state = suspended (new state) unless already completed/cancelled.
4. Optionally auto-create catch-up placeholders (future extension backlog).

### 2.4.3 Data / Fields
`academy.session.occurrence.state` adds 'suspended'. Season adds suspension windows (one2many `academy.season.suspension` with start/end, reason).

### 2.4.4 Acceptance
| ID | Criterion |
|----|----------|
| SUSP1 | All targeted future occurrences in window set to suspended |
| SUSP2 | Individual sessions excluded when option unchecked |
| SUSP3 | Resuming (removal of window) reverts only previously suspended ones still in future back to planned |

## 2.5 Calendar Visibility & Access Control

### 2.5.1 Purpose
Ensure that players and guardians only see: (a) group sessions for the player's skill group(s), (b) individual sessions they are part of, and (c) lead coach's availability summary; while coaches see all sessions relevant to their role.

### 2.5.2 Visibility Matrix (Conceptual)
| Viewer | Sessions Visible |
|--------|------------------|
| Guardian | Child's group occurrences, child's individual sessions |
| Player (portal) | Own group + individual |
| Coach | All sessions where coach_id matches OR skill group in portfolio |
| Head Coach | All sessions in active seasons |
| Site Admin | All |

### 2.5.3 Implementation Notes
- Record rules filter `academy.session.occurrence` by skill_group_id via join on player mapping.
- For group membership: dynamic domain using player's skill_group_id.
- Lead coach schedule exposed as read-only aggregated calendar (may mask other players' names – show counts only) for privacy.

### 2.5.4 Acceptance
| ID | Criterion |
|----|----------|
| VIS1 | Guardian attempting to access unrelated group session gets access error |
| VIS2 | Player sees lead coach time blocks without unrelated player identities |
| VIS3 | Coach sees own and assigned group sessions; head coach sees all |

## 2.6 Non-Functional & Future Extensions
| Area | Note |
|------|------|
| Performance | Bulk generation O(N) where N = occurrences; use batch create for efficiency |
| Timezones | Store UTC datetimes; display localized; templates keep local wall time semantics |
| Auditing | All mass operations log summary entries (count changed, range) |
| Future | Holiday calendar integration; automated make-up session suggestion; capacity management per court; weather API triggers for outdoor cancellations |

---

## 2.7 Open Questions / Assumptions
| Topic | Assumption (to validate) |
|-------|-------------------------|
| Coach assignment for group sessions | Default unset; attendance ties player to lead coach implicitly |
| Player multi-group membership | Not supported initially (one active skill group) |
| Court granularity | Simple discrete courts; no sub-slot partitioning |
| Absence notifications channel | Email + portal badge; no SMS initial phase |
| Billing link | Attendance (not mere scheduling) drives invoice lines |

---

## 2.8 Acceptance Traceability Summary
Linking requirements to stories:
- Weekly recurring schedule (Req: Scheduling) → Story 2.1 (SCH1–SCH5)
- Individual coach sessions → Story 2.2 (IND1–IND3)
- Guardian absence reporting → Story 2.3 (ABS1–ABS3)
- Suspension during dome period → Story 2.4 (SUSP1–SUSP3)
- Visibility restrictions (lead coach & guardians) → Story 2.5 (VIS1–VIS3)
- Court assignment & conflict detection → Story 2.1 (SCH2), Story 2.2 (IND1)

---

# 3. Attendance Tracking via Check-In & Absence Management

## Context: Check-In Driven Model

**Core Principle**: Attendance records are created by **actual check-ins** (not pre-generated expectations).

**Workflow**:
1. Guardian reports absence (portal form) → Creates absence request (no attendance record)
2. Player checks in at kiosk/tablet → Creates attendance record
3. Coach supplements missed check-ins → Creates attendance record
4. Billing runs → Bills only checked-in players

**Key Difference from Traditional Model**:
- ❌ NO pre-generated "expected" attendance for all registered players
- ✅ Attendance records exist ONLY for players who checked in
- ✅ Absence requests are notifications, not attendance state changes
- ✅ No-shows (neither check-in nor absence) → No attendance record, no billing

---

## 3.1 Guardian Absence Request Submission (Portal Form)

### 3.1.1 Purpose
Allow guardians to proactively notify the academy when their child will not attend a scheduled session, creating an absence request record that prevents no-show follow-up alerts without creating an attendance record.

### 3.1.2 Actors
| Role | Responsibility |
|------|----------------|
| Guardian (portal user) | Submits absence request via portal form |
| System | Validates submission deadline; creates absence request record; notifies coach |
| Lead Coach | Receives notification; views absence list during session |
| Billing System | Does NOT bill players with absence requests (no attendance record exists) |

### 3.1.3 Preconditions
- Guardian authenticated and logged into portal
- Guardian has linked player(s) with upcoming sessions
- Sessions scheduled and visible in portal
- Absence request submission deadline configured (default: 2 hours before session start)
- Guardian has not already submitted absence for the same player/session

### 3.1.4 Triggers
1. Guardian navigates to **My Kids ▸ Sessions** in portal
2. Guardian clicks **"Report Absence"** button next to an upcoming session
3. System reminder notification prompts guardian about upcoming session (optional future)

### 3.1.5 Happy Path Flow
1. Guardian logs into portal, navigates to **My Kids ▸ Sessions**
2. System displays table per child:
   - Columns: Date, Time, Session, Actions
   - Each row has "Report Absence" button (red outline, secondary style)
3. Guardian clicks "Report Absence" for session (e.g., "Зелени - Monday 15:00" on 10/13/2025 12:00-14:00)
4. System displays absence request form modal:
   - **Player**: [Player Name] (read-only, pre-filled)
   - **Session**: [Session Name] (read-only)
   - **Date/Time**: [Date Time Range] (read-only)
   - **Reason**: [Dropdown] - Required
     - Options: Illness, Travel, Family Emergency, Other
   - **Additional Notes**: [Text area] - Optional, max 500 chars
   - Buttons: [Cancel] [Submit Absence Report]
5. Guardian selects reason "Illness", enters note "Has a fever", clicks Submit
6. System validates:
   - Current time < (session start time - 2 hours): PASS
   - No existing absence request for this player/session: PASS
7. System processes:
   - Creates `academy.absence.request`:
     - player_id, session_id, guardian_id, reason, notes, submission_time
   - **DOES NOT create attendance record** (absence is just notification)
   - Posts chatter message on session: "Absence reported by [Guardian] for [Player]: [Reason]"
   - Optional: Sends notification to lead_coach_id
8. Modal closes; portal displays confirmation: "Absence reported successfully."
9. Button changes to "Absence Reported" (disabled, check icon)
10. Clicking button shows detail card: Reason, submission time, notes

### 3.1.6 Alternative / Error Paths
| Condition | Outcome |
|-----------|---------|
| Submission within 2-hour cutoff | Error: "Cannot report absence within 2 hours of session start. Please contact the academy directly." Form remains open. |
| Session already started/completed | Error: "Cannot report absence for past or in-progress sessions." |
| Absence already submitted | Info message: "Absence already reported for this session on [date]. View details." Link to existing request. |
| Session cancelled by academy | Info: "This session has been cancelled. No absence report needed." Button hidden. |
| Guardian tries to report for non-child player | Access denied (record rule blocks) |
| Network failure during submission | Auto-retry; on persistent failure, show error with retry button |

### 3.1.7 Postconditions
- Absence request record created and linked to player and session
- **NO attendance record created** (key principle)
- Lead coach notified via email and/or portal badge
- Guardian portal reflects updated status (button disabled)
- Chatter audit trail documents request
- Player will NOT appear in no-show alerts if they don't check in

### 3.1.8 Data Entities & Fields
| Entity | Fields Created/Updated |
|--------|------------------------|
| academy.absence.request | id, player_id, session_id, guardian_id, reason (Selection), notes (Text), submission_time (Datetime), state ('submitted') |
| academy.session.occurrence | No direct changes (absence requests queried via relationship) |
| mail.message | Chatter post on session |
| ir.config_parameter | `academy.absence_cutoff_hours` (default: 2) |

### 3.1.9 Security & Permissions
- Portal controllers enforce: guardians can only submit for their children (player.guardian_ids contains current_user.partner_id)
- Absence request model:
  - Create: portal guardians (group_academy_guardian_portal)
  - Read: Guardian (own requests), coaches (sessions they lead), admin (all)
  - Write/Delete: Admin only (requests immutable after submission for audit)

### 3.1.10 Business Rules / Validation
- Cutoff enforcement: `submission_time < (session.date_start - cutoff_hours)`
- Reason mandatory; notes optional
- One absence request per (player, session) - SQL constraint or check
- Retroactive: Guardian cannot delete/edit submitted request (contact admin for cancellation)
- **No attendance record impact**: Absence request exists independently; if player checks in anyway, attendance overrides absence

### 3.1.11 Auditing
- Chatter message on session: `Absence reported by {guardian} for {player} at {timestamp}. Reason: {reason}. Notes: {notes}.`
- Optional email to lead coach with session summary
- Dashboard metric: Absence rate by reason, advance notice time distribution

### 3.1.12 UX Wireframe (Textual)
**Guardian Portal – Sessions Table:**
```
My Kids ▸ Стела Величкова
────────────────────────────────────────────────────────────
Date         Time          Session                  Actions
10/13/2025   12:00-14:00   Зелени - Monday 15:00   [Report Absence]
10/20/2025   12:00-14:00   Зелени - Monday 15:00   [Report Absence]
10/27/2025   13:00-15:00   Зелени - Monday 15:00   [Report Absence]
────────────────────────────────────────────────────────────
```

**Absence Request Modal:**
```
Report Absence
────────────────────────────────────────────
Player: Стела Величкова (read-only)
Session: Зелени - Monday 15:00 (read-only)
Date: 10/13/2025 12:00 - 14:00 (read-only)

Reason: [Dropdown ▼]
  Illness
  Travel
  Family Emergency
  Other

Additional Notes (optional):
[Text area: max 500 chars]

[Cancel]  [Submit Absence Report]
────────────────────────────────────────────
```

### 3.1.13 Sequence (Textual)
```
Guardian → Portal: Navigate to My Kids ▸ Sessions
Portal → System: Fetch upcoming sessions for guardian's children
System → Portal: Display sessions table with "Report Absence" buttons
Guardian → Portal: Click "Report Absence" for specific session
Portal → System: Fetch session and player details
System → Portal: Display absence request form (pre-filled)
Guardian → Portal: Select reason, enter notes, submit
Portal → System: Validate cutoff, uniqueness
System → AbsenceRequest: Create record (player, session, guardian, reason, notes, time)
System → Chatter: Post audit message on session
System → LeadCoach: Send notification (if configured)
System → Portal: Display confirmation message
Portal → Guardian: Update button to "Absence Reported" (disabled)
```

### 3.1.14 Pseudo Code
```python
class AcademyAbsenceRequest(models.Model):
    _name = 'academy.absence.request'
    _description = 'Player Absence Request'
    _sql_constraints = [
        ('unique_player_session', 'UNIQUE(player_id, session_id)', 
         'Absence request already exists for this player and session.')
    ]
    
    player_id = fields.Many2one('academy.player', required=True, ondelete='cascade')
    session_id = fields.Many2one('academy.session.occurrence', required=True, ondelete='cascade')
    guardian_id = fields.Many2one('res.partner', required=True)
    reason = fields.Selection([
        ('illness', 'Illness'),
        ('travel', 'Travel'),
        ('emergency', 'Family Emergency'),
        ('other', 'Other')
    ], required=True)
    notes = fields.Text(string='Additional Notes')
    submission_time = fields.Datetime(default=fields.Datetime.now, required=True)
    state = fields.Selection([('submitted', 'Submitted')], default='submitted')

    @api.model
    def create(self, vals):
        # Validate submission timing
        session = self.env['academy.session.occurrence'].browse(vals['session_id'])
        cutoff_hours = int(self.env['ir.config_parameter'].sudo().get_param(
            'academy.absence_cutoff_hours', 2))
        cutoff_time = session.date_start - timedelta(hours=cutoff_hours)
        submission = vals.get('submission_time', fields.Datetime.now())
        
        if submission >= session.date_start:
            raise ValidationError(_('Cannot report absence for past or in-progress sessions.'))
        
        if submission >= cutoff_time:
            raise ValidationError(_(
                'Cannot report absence within {hours} hours of session start. '
                'Please contact the academy directly.'
            ).format(hours=cutoff_hours))
        
        # Create absence request (NO attendance record created)
        request = super().create(vals)
        
        # Audit trail
        reason_label = dict(request._fields['reason'].selection).get(request.reason)
        session.message_post(
            body=f"Absence reported by {request.guardian_id.name} for {request.player_id.name}: "
                 f"{reason_label}. Notes: {request.notes or 'None'}."
        )
        
        # Notify lead coach
        if session.player_id.lead_coach_id:  # Adjust based on session/player relationship
            request._send_coach_notification()
        
        return request

    def _send_coach_notification(self):
        # Email notification to lead coach
        template = self.env.ref('academy_attendance.absence_notification_email')
        template.send_mail(self.id, force_send=True)
```

### 3.1.15 Acceptance Criteria
| ID | Criterion |
|----|-----------|
| ABS-REQ1 | Guardian can submit absence request for upcoming session (>2 hours away) via portal form |
| ABS-REQ2 | Form fields match portal screenshot: player, session, date/time (read-only), reason dropdown, notes |
| ABS-REQ3 | Absence request record created; NO attendance record created |
| ABS-REQ4 | Submission within cutoff blocked with clear error message |
| ABS-REQ5 | Lead coach receives notification of absence |
| ABS-REQ6 | Duplicate submission for same player/session prevented |
| ABS-REQ7 | Portal button changes to "Absence Reported" after submission |
| ABS-REQ8 | Player with absence request does NOT appear in no-show alerts |

---

## 3.2 Tablet/Kiosk Check-In at Court Entrance

### 3.2.1 Purpose
Provide frictionless self-service check-in for players arriving at the court, creating attendance records in real-time without manual staff intervention.

### 3.2.2 Actors
| Role | Responsibility |
|------|----------------|
| Player | Taps their name on kiosk to check in |
| System (Kiosk App) | Displays current session roster; creates attendance record on tap |
| Database | Stores attendance record with check-in timestamp |
| Coach | Views check-in status in real-time (optional) |

### 3.2.3 Preconditions
- Tablet/kiosk set up at court entrance in full-screen mode
- Network connectivity available
- Session scheduled and active (within check-in window: 15 min before start to 15 min after end)
- Players registered for session (via skill group or individual enrollment)

### 3.2.4 Triggers
1. Player arrives at court entrance
2. Kiosk displays current session(s) with player roster
3. Player taps their name

### 3.2.5 Happy Path Flow
1. Tablet at court entrance runs kiosk web app (URL: `/academy/kiosk/checkin`)
2. Kiosk displays current and upcoming sessions on nearby courts:
   ```
   Academy Check-In
   ════════════════════════════════════════
   Court 1 • NOW: Зелени - Monday 15:00
   13:00 - 15:00
   
   Tap your name to check in:
   
   [Стела Величкова    ]  Age 12
   [Jordan Player       ]  Age 11
   [Taylor Smith        ]  Age 13
   ... (scrollable list)
   ════════════════════════════════════════
   ```
3. Player taps their name (e.g., "Стела Величкова")
4. System validates:
   - Session within check-in window: PASS
   - Player registered for session: PASS
   - Player not already checked in: PASS
5. System creates `academy.attendance` record:
   - session_id = current session
   - player_id = tapped player
   - checkin_time = now
   - state = 'present'
   - checkin_method = 'kiosk'
6. Confirmation screen displays (2 seconds):
   ```
   ✓ Checked In Successfully!
   
   Стела Величкова
   Зелени - Monday 15:00
   13:05
   
   Enjoy your session!
   ```
7. Screen auto-returns to player list
8. If absence request exists for this player/session, system logs override (player showed up despite reported absence)

### 3.2.6 Alternative / Error Paths
| Condition | Outcome |
|-----------|---------|
| Player already checked in | Show: "You're already checked in at [time]!" (idempotent, no error) |
| Player taps wrong name by mistake | Display includes "Undo" button for 5 seconds to reverse check-in |
| Session not within check-in window (>15 min before start) | Show: "Check-in opens 15 minutes before session start." |
| Session ended >15 min ago | Session not displayed in active list |
| Network interruption | Cache check-in locally, sync when connection restored (offline capability) |
| Tablet frozen/crashed | Reloading page resumes normal operation (stateless kiosk) |

### 3.2.7 Postconditions
- Attendance record created with state='present', method='kiosk'
- Session's attendee count increments (one-to-many relationship)
- If absence request exists, it's marked as overridden (player attended anyway)
- Coach can view real-time check-in status on their device
- Player name moves to "checked in" section if coach is viewing simultaneously

### 3.2.8 Data Entities & Fields
| Entity | Fields Created |
|--------|----------------|
| academy.attendance | id, session_id, player_id, checkin_time, state='present', checkin_method='kiosk' |
| academy.session.occurrence | attendance_ids (One2many), attendance_count (computed) |
| academy.absence.request | overridden_by_checkin (Boolean) - optional field to track |

### 3.2.9 Security & Permissions
- Kiosk endpoint: Public access (no authentication) but restricted to valid sessions only
- IP whitelist: Optional restrict kiosk URL to tablet's IP range (academy network)
- Rate limiting: Prevent spam (max 1 check-in per player per minute)
- Session validation: Check-in only allowed for sessions in active window

### 3.2.10 Business Rules / Validation
- Check-in window: `session.date_start - 15 min` to `session.date_end + 15 min`
- Player must be registered for session (either via skill_group_id match or explicit participant link)
- Idempotent: Tapping same player multiple times shows "already checked in" (doesn't create duplicate)
- Attendance overrides absence: If absence request exists, check-in takes precedence (player showed up)

### 3.2.11 Auditing
- Optional chatter message on session (if verbose logging enabled): `Kiosk check-in: {player_name} at {timestamp}`
- System log (INFO): `[KIOSK-CHECKIN] Player {player_id} checked in for session {session_id} at {time}`
- Dashboard metric: Check-in method distribution (kiosk vs coach), average check-in time vs session start

### 3.2.12 UX Wireframe (Textual)
```
[Full-Screen Kiosk Display]

        Academy Check-In
════════════════════════════════════════════
Court 1 • NOW
Зелени - Monday 15:00
13:00 - 15:00

Tap your name to check in:

┌────────────────────────────┐
│ Стела Величкова       12 y │
└────────────────────────────┘
┌────────────────────────────┐
│ Jordan Player         11 y │
└────────────────────────────┘
┌────────────────────────────┐
│ Taylor Smith          13 y │
└────────────────────────────┘
... (scroll for more)

────────────────────────────────────────────
Next: Court 2 • 15:00
Advanced - Monday 17:00
════════════════════════════════════════════

[Confirmation Screen - 2 second display]

        ✓ Checked In!
════════════════════════════════════════════

     Стела Величкова
     
  Зелени - Monday 15:00
       13:05
       
  Enjoy your session!
  
════════════════════════════════════════════
```

### 3.2.13 Sequence (Textual)
```
Player → Kiosk: Arrive at court entrance
Kiosk → System: Fetch current sessions within check-in window
System → Kiosk: Return session list with registered players
Kiosk: Display player roster for current session
Player → Kiosk: Tap name
Kiosk → System: POST check-in request (session_id, player_id)
System → Validation: Check window, registration, not duplicate
System → Attendance: Create record (session, player, time, method='kiosk')
System → Kiosk: Return success with confirmation data
Kiosk: Display "Checked In!" confirmation (2 sec)
Kiosk: Auto-return to player list
System → Coach (if viewing): Push notification or refresh attendee list
```

### 3.2.14 Pseudo Code
```python
class AcademyKioskController(http.Controller):
    @http.route('/academy/kiosk/checkin', type='http', auth='public', website=True)
    def kiosk_display(self, **kwargs):
        # Fetch active sessions (within check-in window)
        now = fields.Datetime.now()
        window_minutes = 15
        sessions = request.env['academy.session.occurrence'].sudo().search([
            ('date_start', '<=', now + timedelta(minutes=window_minutes)),
            ('date_end', '>=', now - timedelta(minutes=window_minutes)),
            ('state', '=', 'planned')
        ])
        
        # Prepare session data with registered players
        session_data = []
        for session in sessions:
            players = self._get_registered_players(session)
            checked_in_ids = session.attendance_ids.mapped('player_id').ids
            session_data.append({
                'session': session,
                'players': players,
                'checked_in_ids': checked_in_ids
            })
        
        return request.render('academy_attendance.kiosk_checkin', {
            'session_data': session_data
        })
    
    @http.route('/academy/kiosk/checkin/submit', type='json', auth='public', csrf=False)
    def kiosk_checkin_submit(self, session_id, player_id):
        session = request.env['academy.session.occurrence'].sudo().browse(session_id)
        player = request.env['academy.player'].sudo().browse(player_id)
        
        # Validate check-in window
        now = fields.Datetime.now()
        if not (session.date_start - timedelta(minutes=15) <= now <= session.date_end + timedelta(minutes=15)):
            return {'success': False, 'error': 'Check-in window not active'}
        
        # Check for existing attendance
        existing = request.env['academy.attendance'].sudo().search([
            ('session_id', '=', session_id),
            ('player_id', '=', player_id)
        ])
        if existing:
            return {
                'success': True, 
                'already_checked_in': True,
                'checkin_time': existing.checkin_time
            }
        
        # Create attendance record
        attendance = request.env['academy.attendance'].sudo().create({
            'session_id': session_id,
            'player_id': player_id,
            'checkin_time': now,
            'state': 'present',
            'checkin_method': 'kiosk'
        })
        
        # Check for absence override
        absence = request.env['academy.absence.request'].sudo().search([
            ('session_id', '=', session_id),
            ('player_id', '=', player_id)
        ])
        if absence:
            absence.write({'overridden_by_checkin': True})
            session.message_post(
                body=f"{player.name} checked in (overriding absence request: {absence.reason})"
            )
        
        return {
            'success': True,
            'already_checked_in': False,
            'player_name': player.name,
            'session_name': session.name,
            'checkin_time': now
        }
    
    def _get_registered_players(self, session):
        # Get players registered for this session
        if session.session_type in ['tennis_group', 'physical_group']:
            return request.env['academy.player'].sudo().search([
                ('skill_group_id', '=', session.skill_group_id.id),
                ('active', '=', True)
            ])
        else:  # individual sessions
            return session.participant_ids
```

### 3.2.15 Acceptance Criteria
| ID | Criterion |
|----|-----------|
| KIOSK1 | Tablet displays current session(s) with registered players in large, tappable list |
| KIOSK2 | Tapping player name creates attendance record with state='present', method='kiosk' |
| KIOSK3 | Confirmation screen displays for 2 seconds then auto-returns to player list |
| KIOSK4 | Tapping same player again shows "Already checked in" (idempotent) |
| KIOSK5 | Check-in only allowed within window (15 min before to 15 min after session) |
| KIOSK6 | Absence request overridden if player checks in (logged in chatter) |
| KIOSK7 | Multiple simultaneous sessions displayed with clear separation by court |

---

## 3.3 Coach Supplemental Check-In (Mobile Interface)

### 3.3.1 Purpose
Enable coach to check in players who forgot to use the kiosk or arrived late, ensuring complete attendance records without requiring players to return to the kiosk.

### 3.3.2 Actors
| Role | Responsibility |
|------|----------------|
| Coach | Views session attendance; checks in missing players |
| System | Displays real-time check-in status; creates attendance records |
| Database | Stores coach-initiated attendance records |

### 3.3.3 Preconditions
- Coach authenticated (internal user with coach role)
- Coach assigned to session or has permission to view
- Session active or recently completed
- Some players checked in via kiosk, some haven't

### 3.3.4 Triggers
1. Coach opens mobile app/web interface
2. Navigates to **Today's Sessions** → selects their current session
3. Sees list of players: checked in vs not yet checked in
4. Taps "Check In Now" for player physically present

### 3.3.5 Happy Path Flow
1. Coach opens Academy mobile app on phone/tablet
2. Navigates to **Today's Sessions**
3. Selects current session: "Зелени - Monday 15:00"
4. System displays attendance summary:
   ```
   Зелени - Monday 15:00
   Court 1 • 13:00 - 15:00
   ═══════════════════════════════════
   Checked In: 8 of 12
   
   ✓ Стела Величкова     13:03 (Kiosk)
   ✓ Jordan Player        13:05 (Kiosk)
   ✓ Taylor Smith         13:02 (Kiosk)
   ... (5 more)
   
   ───────────────────────────────────
   Not Yet Checked In:
   
   Sam Anderson      [Check In Now]
   Jamie Garcia      [Check In Now]
   Drew Thompson     [Check In Now]
   
   ───────────────────────────────────
   Absences Reported:
   🅧 Chris Evans    Illness
   ═══════════════════════════════════
   [Mark Session Complete]
   ```
5. Coach sees Sam Anderson is present but forgot to check in at kiosk
6. Coach taps **"Check In Now"** next to Sam Anderson
7. System creates `academy.attendance` record:
   - session_id, player_id=Sam Anderson
   - checkin_time=now, state='present', checkin_method='coach_manual'
8. Sam Anderson moves to "Checked In" section with timestamp
9. Count updates: "Checked In: 9 of 12"
10. Coach repeats for other late arrivals
11. When satisfied, coach taps **"Mark Session Complete"** to finalize

### 3.3.6 Alternative / Error Paths
| Condition | Outcome |
|-----------|---------|
| Coach tries to check in player already checked in | Button disabled/hidden; shows "Already checked in at [time]" |
| Coach tries to check in after session marked complete | Warning: "Session completed. Contact admin to adjust attendance." |
| Network interruption | Cache check-in; sync when reconnected; show "Pending sync" indicator |
| Player not registered for session | Not in list (filtered out during display) |

### 3.3.7 Postconditions
- Attendance records created with checkin_method='coach_manual'
- Session's checked-in count updates
- Billing pipeline can process these attendances normally (same as kiosk check-ins)
- Coach can mark session complete to transition to billing phase

### 3.3.8 Data Entities & Fields
| Entity | Fields Created/Updated |
|--------|------------------------|
| academy.attendance | session_id, player_id, checkin_time, state='present', checkin_method='coach_manual' |
| academy.session.occurrence | attendance_count (computed), state (when marked complete) |

### 3.3.9 Security & Permissions
- Action visible to: Coaches assigned to session, head coaches, site admin
- Record rules: Coach can only check in for sessions where session.coach_id = user OR user in group_head_coach
- Cannot check in players for other coaches' sessions (unless head coach/admin)

### 3.3.10 Business Rules / Validation
- Can check in during session or up to 1 hour after session end (grace period)
- Cannot check in >1 hour after session end (requires admin override)
- Cannot mark "absent" - only add check-ins (players without check-ins simply have no attendance record)
- "Mark Session Complete" available anytime during/after session

### 3.3.11 Auditing
- Attendance record includes marked_by_id = coach user
- Optional chatter on session: "Coach {name} checked in {player} at {time}"
- Metric tracking: Coach check-in rate (how many players needed manual check-in vs kiosk)

### 3.3.12 UX Wireframe (Textual)
```
[Mobile App - Coach View]

═══════════════════════════════════════
Зелени - Monday 15:00
Court 1 • 13:00 - 15:00
State: In Progress
═══════════════════════════════════════

📊 Checked In: 8 of 12 registered

✅ Checked In (8)
─────────────────────────────────────
Стела Величкова     13:03  Kiosk
Jordan Player       13:05  Kiosk
Taylor Smith        13:02  Kiosk
Casey Lee           13:04  Kiosk
Morgan Davis        13:06  Kiosk
Riley Brown         13:08  Kiosk
Avery Wilson        13:07  Kiosk
Parker Martinez     13:10  Kiosk

⏳ Not Yet Checked In (3)
─────────────────────────────────────
Sam Anderson        [Check In Now]
Jamie Garcia        [Check In Now]
Drew Thompson       [Check In Now]

🚫 Absences Reported (1)
─────────────────────────────────────
Chris Evans         Illness
                    (No action needed)

═══════════════════════════════════════
[Mark Session Complete]
═══════════════════════════════════════
```

### 3.3.13 Sequence (Textual)
```
Coach → App: Open Today's Sessions
App → System: Fetch coach's sessions for today
System → App: Return session list
Coach → App: Select current session
App → System: Fetch session attendance data
System → Query: Registered players, attendance records, absence requests
System → App: Return attendance summary (checked in, not checked in, absences)
App: Display attendance interface
Coach → App: Tap "Check In Now" for Sam Anderson
App → System: POST check-in request (session_id, player_id, method='coach_manual')
System → Attendance: Create record with coach as marked_by
System → App: Return success
App: Move Sam Anderson to "Checked In" section, update count
Coach → App: Tap "Mark Session Complete"
App → System: Update session state to 'completed'
System → Session: Write state='completed', log chatter
System → App: Confirm completion
App: Show "Session marked complete. Billing will process attendees."
```

### 3.3.14 Pseudo Code
```python
class AcademyAttendanceCoach(models.Model):
    _name = 'academy.attendance'
    
    marked_by_id = fields.Many2one('res.users', string='Checked In By')
    
    @api.model
    def coach_checkin(self, session_id, player_id):
        """Coach-initiated check-in for player who missed kiosk."""
        session = self.env['academy.session.occurrence'].browse(session_id)
        player = self.env['academy.player'].browse(player_id)
        
        # Check for existing attendance
        existing = self.search([
            ('session_id', '=', session_id),
            ('player_id', '=', player_id)
        ])
        if existing:
            return {'success': False, 'error': 'Player already checked in', 'attendance': existing}
        
        # Validate grace period (during session or up to 1 hour after)
        now = fields.Datetime.now()
        if now > session.date_end + timedelta(hours=1):
            raise ValidationError(_('Check-in window closed. Contact admin for retroactive attendance.'))
        
        # Create attendance record
        attendance = self.create({
            'session_id': session_id,
            'player_id': player_id,
            'checkin_time': now,
            'state': 'present',
            'checkin_method': 'coach_manual',
            'marked_by_id': self.env.user.id
        })
        
        # Audit
        session.message_post(body=f"Coach {self.env.user.name} checked in {player.name} at {now}.")
        
        return {'success': True, 'attendance': attendance}

class AcademySessionOccurrence(models.Model):
    _name = 'academy.session.occurrence'
    
    def action_mark_complete(self):
        """Coach marks session as complete (triggers billing phase)."""
        for session in self:
            if session.state == 'completed':
                raise UserError(_('Session is already marked complete.'))
            
            session.write({'state': 'completed'})
            session.message_post(
                body=f"Session marked complete by {self.env.user.name}. "
                     f"{session.attendance_count} players checked in."
            )
        
        return True
```

### 3.3.15 Acceptance Criteria
| ID | Criterion |
|----|-----------|
| COACH-CHK1 | Coach sees real-time list of checked-in vs not-yet-checked-in players |
| COACH-CHK2 | Tapping "Check In Now" creates attendance record with method='coach_manual' |
| COACH-CHK3 | Player moves to "Checked In" section after coach check-in |
| COACH-CHK4 | Absence requests displayed separately (no action needed) |
| COACH-CHK5 | "Mark Session Complete" button available during/after session |
| COACH-CHK6 | Coach cannot check in players for other coaches' sessions (permission check) |
| COACH-CHK7 | Check-in grace period enforced (up to 1 hour after session end) |

---

## 3.4 Billing Integration - Attendance-Driven Invoicing

### 3.4.1 Purpose
Generate billing items only for players who actually attended (checked in via kiosk or coach), ensuring accurate charges based on actual attendance rather than expectations.

### 3.4.2 Actors
| Role | Responsibility |
|------|----------------|
| Billing System (Cron) | Queries attendance records; creates billing items |
| Database | Stores attendance and billing item records with traceability |
| Admin | Reviews billing items before invoice generation |

### 3.4.3 Preconditions
- Sessions completed (state='completed')
- Attendance records exist for checked-in players
- Absence requests recorded for notified absences
- Billing pricing configured (group session price, individual session price)
- No existing billing items for the attendance records (prevent duplicates)

### 3.4.4 Triggers
1. Monthly billing cron runs (configurable: weekly, bi-weekly, or monthly)
2. Manual billing generation action invoked by admin
3. Session marked complete (optional: create billing items immediately)

### 3.4.5 Happy Path Flow
1. Billing cron runs on first of month
2. System queries `academy.attendance` for:
   - state = 'present' (checked in)
   - session.state = 'completed'
   - billing_item_id = NULL (not yet billed)
3. For each attendance record:
   - Determine price based on session type:
     - Group session: $25
     - Individual session: $60
     - Physical training: $20
   - Create `academy.billing.item`:
     - player_id, session_id, primary_guardian_id
     - amount = session price
     - source_attendance_id (Many2one for traceability)
     - state = 'pending'
4. Set attendance.billing_item_id = created billing item (prevent duplicate billing)
5. System groups billing items by primary_guardian_id
6. For each guardian with billing items:
   - Create draft invoice (or add to existing monthly invoice)
   - Invoice lines reference billing items
7. Billing summary email sent to guardians
8. **No billing for:**
   - Players with absence requests (no attendance record exists)
   - Players who didn't check in (no-shows, no attendance record)

### 3.4.6 Alternative / Error Paths
| Condition | Outcome |
|-----------|---------|
| Attendance already billed | Skip (billing_item_id not NULL); log info |
| Session not completed | Skip; billing only processes completed sessions |
| Missing pricing config | Error logged; billing item creation skipped for that session type; admin notified |
| Guardian archived/inactive | Billing item created but flagged for admin review |
| Duplicate billing attempt | Prevented by attendance.billing_item_id uniqueness |

### 3.4.7 Postconditions
- Billing items created for all checked-in players
- Attendance records linked to billing items (traceability)
- Draft invoices created per guardian
- **No charges for:** Absence requests, no-shows (neither have attendance records)
- Admin can review billing items before finalizing invoices

### 3.4.8 Data Entities & Fields
| Entity | Fields Created/Updated |
|--------|------------------------|
| academy.billing.item | id, player_id, session_id, primary_guardian_id, amount, source_attendance_id, state='pending' |
| academy.attendance | billing_item_id (to prevent duplicate billing) |
| account.move (Invoice) | invoice_line_ids referencing billing items |

### 3.4.9 Security & Permissions
- Billing cron runs as system user (superuser access)
- Billing items: Create (system/admin), Read (admin, guardians for their own), Write (admin only), Delete (admin only with reason)
- Invoices: Standard Odoo accounting permissions

### 3.4.10 Business Rules / Validation
- **Only checked-in players are billed**: No attendance record = no billing
- **Absence requests prevent no-show flags** but don't create billing (no attendance = no charge)
- **No-shows (no check-in, no absence)**: Not billed, but flagged for follow-up
- **Coach manual check-ins**: Billed same as kiosk check-ins (method doesn't affect billing)
- **Interrupted sessions**: If marked complete, all checked-in players billed (no partial refunds)
- **Duplicate prevention**: attendance.billing_item_id ensures one billing item per attendance

### 3.4.11 Auditing
- Billing item creation logged in chatter: "Billing item created for {player} - {session} - {amount}"
- Dashboard metrics: Billing by session type, check-in method, average attendance rate
- Monthly billing summary report: Total billed, players attended, absence rate, no-show rate

### 3.4.12 UX Wireframe (Textual)
**Admin Billing Review:**
```
Billing Items - October 2025
═══════════════════════════════════════════════════════════
Date       Player              Session          Method   Amount
10/13      Стела Величкова     Зелени - Mon     Kiosk    $25.00
10/13      Jordan Player       Зелени - Mon     Kiosk    $25.00
10/13      Sam Anderson        Зелени - Mon     Coach    $25.00
10/20      Стела Величкова     Зелени - Mon     Kiosk    $25.00
... (hundreds more)
───────────────────────────────────────────────────────────
Total: $12,350.00 (494 attendances)

[Export CSV] [Generate Invoices]
═══════════════════════════════════════════════════════════
```

### 3.4.13 Sequence (Textual)
```
Cron → System: Trigger monthly billing
System → Attendance: Query records (state='present', session.completed, not billed)
System → Loop: For each attendance record
  System → Pricing: Lookup session type price
  System → BillingItem: Create (player, session, guardian, amount, source_attendance)
  System → Attendance: Set billing_item_id (prevent duplicate)
System → BillingItem: Group by primary_guardian_id
System → Loop: For each guardian with items
  System → Invoice: Create/update draft invoice
  System → InvoiceLine: Add lines referencing billing items
System → Guardian: Send billing summary email
System → Admin: Send billing completion notification
```

### 3.4.14 Pseudo Code
```python
class AcademyBillingCron(models.AbstractModel):
    _name = 'academy.billing.cron'
    
    @api.model
    def run_monthly_billing(self):
        """Generate billing items for checked-in players."""
        # Find unbilled attendances
        attendances = self.env['academy.attendance'].search([
            ('state', '=', 'present'),
            ('session_id.state', '=', 'completed'),
            ('billing_item_id', '=', False)  # Not yet billed
        ])
        
        if not attendances:
            _logger.info("[BILLING] No unbilled attendances found.")
            return
        
        # Group by pricing needs (could optimize with SQL)
        billing_items = []
        for att in attendances:
            # Determine price based on session type
            price = self._get_session_price(att.session_id)
            
            # Create billing item
            billing_item = self.env['academy.billing.item'].create({
                'player_id': att.player_id.id,
                'session_id': att.session_id.id,
                'primary_guardian_id': att.player_id.primary_guardian_id.id,
                'amount': price,
                'source_attendance_id': att.id,
                'state': 'pending'
            })
            
            # Link back to attendance (prevent duplicate billing)
            att.write({'billing_item_id': billing_item.id})
            
            billing_items.append(billing_item)
        
        _logger.info(f"[BILLING] Created {len(billing_items)} billing items.")
        
        # Group by guardian and create invoices
        self._create_guardian_invoices(billing_items)
        
        return billing_items
    
    def _get_session_price(self, session):
        """Lookup pricing based on session type."""
        price_config = {
            'tennis_group': 25.0,
            'tennis_individual': 60.0,
            'physical_group': 20.0,
            'physical_individual': 50.0
        }
        return price_config.get(session.session_type, 25.0)  # Default fallback
    
    def _create_guardian_invoices(self, billing_items):
        """Group billing items by guardian and create invoices."""
        # Group by guardian
        guardian_items = {}
        for item in billing_items:
            guardian_id = item.primary_guardian_id.id
            if guardian_id not in guardian_items:
                guardian_items[guardian_id] = []
            guardian_items[guardian_id].append(item)
        
        # Create invoice per guardian
        for guardian_id, items in guardian_items.items():
            guardian = self.env['res.partner'].browse(guardian_id)
            
            # Create draft invoice
            invoice = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': guardian_id,
                'invoice_date': fields.Date.today(),
                'invoice_line_ids': [(0, 0, {
                    'name': f"{item.session_id.name} - {item.player_id.name}",
                    'quantity': 1,
                    'price_unit': item.amount,
                    # Link to billing item for traceability
                }) for item in items]
            })
            
            # Mark billing items as invoiced
            self.env['academy.billing.item'].browse([i.id for i in items]).write({
                'state': 'invoiced',
                'invoice_id': invoice.id
            })
            
            _logger.info(f"[BILLING] Created invoice {invoice.name} for guardian {guardian.name} with {len(items)} items.")
```

### 3.4.15 Acceptance Criteria
| ID | Criterion |
|----|-----------|
| BILL1 | Billing cron creates billing items only for attendance records with state='present' |
| BILL2 | Each billing item links to source attendance record (traceability) |
| BILL3 | Players with absence requests have no attendance → no billing item created |
| BILL4 | No-shows (no attendance record) are NOT billed |
| BILL5 | Coach manual check-ins billed same as kiosk check-ins (method irrelevant) |
| BILL6 | Duplicate billing prevented via attendance.billing_item_id |
| BILL7 | Draft invoices created per guardian with line items for each attendance |
| BILL8 | Billing summary sent to guardians after processing |

---

## 3.5 Acceptance Traceability Summary
Linking requirements to revised attendance stories:
- Absence request portal form (User feedback) → Story 3.1 (ABS-REQ1–ABS-REQ8)
- Tablet/kiosk check-in (User feedback) → Story 3.2 (KIOSK1–KIOSK7)
- Coach supplemental check-in (User feedback) → Story 3.3 (COACH-CHK1–COACH-CHK7)
- Billing only for checked-in players (User feedback) → Story 3.4 (BILL1–BILL8)
- One-to-many session→attendees relationship → Story 3.2 (attendance records), Story 3.3 (coach view), Story 3.4 (audit trail)

**Key Paradigm Shift:**
- ❌ OLD: Pre-generate expected attendance for all registered players
- ✅ NEW: Attendance records created only by actual check-ins
- ❌ OLD: Absence changes attendance state from "expected" to "absent"
- ✅ NEW: Absence is a separate notification; no attendance record exists
- ❌ OLD: Billing based on attendance state (present/absent)
- ✅ NEW: Billing based on existence of attendance record (checked in = billed)



### 3.1.2 Actors
| Role | Responsibility |
|------|----------------|
| System | Detects session confirmation; creates attendance records with state='expected' |
| Session Manager (Coach/Admin) | Confirms sessions, triggering attendance generation |
| Database | Enforces uniqueness constraint on (session_id, player_id) |

### 3.1.3 Preconditions
- Session record exists (created by cron or manual wizard)
- Session state = 'planned' (committed, not draft)
- Session has one or more registered participants (either via skill_group_id for group sessions or explicit player links for individual sessions)
- `academy.attendance` model and security rules configured
- No existing attendance records for the (session, player) pairs

### 3.1.4 Triggers
1. **Primary trigger**: Cron job that generates sessions immediately creates attendance records (same transaction or immediately after)
2. Players are added to an already-created session (manual enrollment or late registration)
3. Manual "Regenerate Attendance" action invoked by admin (for data repair)

### 3.1.5 Happy Path Flow
1. Cron job generates weekly sessions (Sunday 00:00) with state='planned'
2. Immediately after session creation (same cron or trigger), system generates attendance records
3. For each session `S` created:
   - System queries all active players with skill_group_id = session.skill_group_id (for group sessions) or explicit participant IDs (for individual sessions)
   - For each player `P`:
     - Check if attendance record exists for (session_id=S, player_id=P)
     - If not, create `academy.attendance`:
       - session_id = S
       - player_id = P
       - state = 'expected'
       - attendance_date = session.date_start (date only)
       - session_type = session.session_type
       - primary_guardian_id = player.primary_guardian_id (for billing lookup)
       - create_date, create_uid = current timestamp and system user
4. System commits batch insert (all attendance records in single transaction for efficiency)
5. Optional: Post chatter message on session: "Attendance records created for X players"
6. Portal and coach views refresh to show new attendance records immediately
7. Guardians can now view upcoming sessions and submit absence requests

### 3.1.6 Alternative / Error Paths
| Condition | Outcome |
|-----------|---------|
| Session has no participants | Skip attendance generation; log warning or post chatter note |
| Player archived between generation and attendance creation | Exclude archived players from generation |
| Duplicate attendance attempt (race condition) | Database unique constraint prevents; log error, continue with remaining records |
| Session date in past (rare: manual session creation backdated) | Allow generation but flag as late (attendance state remains 'expected' but system warning logged) |
| Skill group has no active players | Skip; post informational message on session |
| Manual regeneration with existing attendance | Option: Skip duplicates; warn admin if trying to regenerate for session with existing attendance |

### 3.1.7 Postconditions
- One `academy.attendance` record per participating player, all with state='expected'.
- Attendance records queryable by session, player, date, and guardian.
- Coach and guardian portal views display attendance list.
- Billing pipeline can now scan for attendance state changes.
- Chatter history on session documents the generation event.

### 3.1.8 Data Entities & Fields
| Entity | Fields Created/Updated |
|--------|------------------------|
| academy.attendance | id, session_id, player_id, state='expected', attendance_date, session_type, primary_guardian_id, create_date, create_uid, write_date, write_uid |
| academy.session | attendance_ids (One2many reverse), attendance_count (computed), state (trigger field) |
| academy.player | active (filter criterion during generation) |

### 3.1.9 Security & Permissions
- Generation runs as system/superuser to bypass record rules during batch creation.
- Post-creation, record rules apply: guardians see only their children's attendance; coaches see sessions they lead or assist.
- Manual regeneration action visible only to site admins and head coaches (group check).

### 3.1.10 Business Rules / Validation
- Uniqueness: (session_id, player_id) must be unique via SQL constraint or Python `_sql_constraints`.
- State initialization: All new records default to 'expected'; no skipping to 'present' without explicit check-in.
- Date alignment: attendance_date extracted from session.date_start (date component only) for filtering efficiency.
- Billing guardian: Always link to player.primary_guardian_id (not all guardians) to avoid double-billing.

### 3.1.11 Auditing
- Chatter message on session: `Attendance records generated for {count} players by {user} at {timestamp}.`
- System log entry (INFO level): `[ATTENDANCE] Generated {count} records for session {session.name} (ID: {session.id}).`
- Optional metrics model: `academy.attendance.generation.log` with session_id, player_count, duration_ms, status (success/partial/failed).

### 3.1.12 UX Wireframe (Textual)
**Session Form – Attendance Tab:**
```
Attendance (Badge: 12 records)
┌─────────────────────────────────────────────────────┐
│ [Generate Attendance] (button, visible if count=0)  │
│ Player               | State      | Check-In Time    │
│ Jordan Player        | Expected   | —                │
│ Taylor Smith         | Expected   | —                │
│ ... (list continues)                                 │
│                                                      │
│ [Mark All Present] [Export CSV]                     │
└─────────────────────────────────────────────────────┘
```

### 3.1.13 Sequence (Textual)
```
Coach → Session: Confirm (button click)
Session → System: State = 'confirmed' (write trigger)
System → Attendance Service: generate_attendance(session_id)
Service → Players: Query active players (filter: skill_group or participant_ids)
Service → Database: Batch insert attendance records
Database → Service: Commit confirmation
Service → Session: Post chatter message
Service → System: Return success count
System → Coach: Refresh session form (attendance tab badge updates)
```

### 3.1.14 Pseudo Code
```python
class AcademySession(models.Model):
    _name = 'academy.session'
    
    state = fields.Selection([('draft', 'Draft'), ('confirmed', 'Confirmed'), ('completed', 'Completed'), ('cancelled', 'Cancelled')])
    attendance_ids = fields.One2many('academy.attendance', 'session_id', string='Attendance')
    attendance_count = fields.Integer(compute='_compute_attendance_count')

    def action_confirm(self):
        for session in self:
            session.write({'state': 'confirmed'})
            session._generate_attendance()
        return True

    def _generate_attendance(self):
        self.ensure_one()
        # Determine participants
        if self.session_type in ['tennis_group', 'physical_group']:
            players = self.env['academy.player'].search([
                ('skill_group_id', '=', self.skill_group_id.id),
                ('active', '=', True)
            ])
        else:  # individual sessions
            players = self.participant_ids
        
        # Filter out existing attendance
        existing_pairs = self.attendance_ids.mapped(lambda a: a.player_id.id)
        new_players = players.filtered(lambda p: p.id not in existing_pairs)
        
        # Batch create
        attendance_vals = [{
            'session_id': self.id,
            'player_id': player.id,
            'state': 'expected',
            'attendance_date': fields.Date.from_string(self.date_start),
            'session_type': self.session_type,
            'primary_guardian_id': player.primary_guardian_id.id,
        } for player in new_players]
        
        if attendance_vals:
            self.env['academy.attendance'].create(attendance_vals)
            self.message_post(body=f"Attendance records generated for {len(attendance_vals)} players.")
            _logger.info(f"[ATTENDANCE] Generated {len(attendance_vals)} records for session {self.name} (ID: {self.id})")

class AcademyAttendance(models.Model):
    _name = 'academy.attendance'
    _description = 'Session Attendance'
    _sql_constraints = [
        ('unique_session_player', 'UNIQUE(session_id, player_id)', 'Attendance record already exists for this session and player.')
    ]
    
    session_id = fields.Many2one('academy.session', required=True, ondelete='cascade')
    player_id = fields.Many2one('academy.player', required=True)
    state = fields.Selection([
        ('expected', 'Expected'),
        ('present', 'Present'),
        ('abs_notified', 'Absent (Notified)'),
        ('abs_notified_late', 'Absent (Late Notice)'),
        ('abs_unnotified', 'Absent (Unnotified)')
    ], default='expected', required=True)
    attendance_date = fields.Date(required=True)
    session_type = fields.Selection(related='session_id.session_type', store=True)
    primary_guardian_id = fields.Many2one('res.partner', string='Billing Guardian', required=True)
    checkin_time = fields.Datetime(string='Check-In Timestamp')
    marked_by = fields.Many2one('res.users', string='Marked By')
    absence_request_id = fields.Many2one('academy.absence.request', string='Absence Request')
```

### 3.1.15 Acceptance Criteria
| ID | Criterion |
|----|-----------|
| ATT-GEN1 | When session created by cron, attendance records generated immediately for all active players |
| ATT-GEN2 | Each attendance record has state='expected', correct date, session_type, and primary_guardian_id |
| ATT-GEN3 | Duplicate prevention: attempting to create second record for same (session, player) fails gracefully |
| ATT-GEN4 | Manual regeneration action available to admins; skips existing records with warning |
| ATT-GEN5 | Batch insert completes in <2 seconds for groups of up to 30 players |
| ATT-GEN6 | Guardians can view sessions and submit absence requests immediately after generation |

---

## 3.2 Coach-Driven Attendance Marking

### 3.2.1 Purpose
Enable coaches to efficiently mark attendance during or immediately after a session using a streamlined list view with quick-action buttons, ensuring accurate real-time attendance tracking without administrative overhead.

### 3.2.2 Actors
| Role | Responsibility |
|------|----------------|
| Coach | Views session attendance list; marks players present/absent |
| System | Updates attendance state; logs timestamp and user |
| Database | Persists state changes with audit trail |

### 3.2.3 Preconditions
- Attendance records exist for the session (state='expected' or already marked).
- Coach has access to session (session.coach_id = current user OR user in group_head_coach).
- Session date is today or in recent past (configurable window, e.g., past 7 days).

### 3.2.4 Triggers
1. Coach navigates to **Academy ▸ Attendance ▸ Today's Sessions**.
2. Coach opens a specific session from the schedule view.
3. Coach accesses attendance tab on session form.
4. Automated reminder notification prompts coach to complete attendance (optional future).

### 3.2.5 Happy Path Flow
1. Coach opens "Today's Sessions" view (filtered by date = today).
2. Coach selects session `S` from list.
3. System displays attendance records for session `S` in kanban or list view, grouped by state.
4. Coach sees quick-action buttons for each player:
   - **Present** (green checkmark)
   - **Absent (Notified)** (yellow icon with note)
   - **Absent (Unnotified)** (red X)
5. Coach clicks **Present** for player `P1`:
   - Attendance state changes to 'present'.
   - checkin_time = current timestamp.
   - marked_by = current user.
   - Visual feedback: Row background turns green; button disabled.
6. Coach clicks **Absent (Unnotified)** for player `P2`:
   - Attendance state changes to 'abs_unnotified'.
   - marked_by = current user.
   - Optional: Prompt to add brief note (free text).
7. Coach selects multiple players using checkboxes and clicks **Mark All Present** (bulk action):
   - All selected records transition to 'present' with timestamp.
8. Coach clicks **Save** or **Close** (auto-save on state change).
9. System posts chatter message on session: "Attendance completed by {coach} at {timestamp}."

### 3.2.6 Alternative / Error Paths
| Condition | Outcome |
|-----------|---------|
| Coach tries to mark attendance for session >7 days old | Warning: "Session date is past the editing window. Contact admin to adjust." Action blocked |
| Coach tries to change already-billed attendance | Error: "Attendance record is locked (billed). Use credit note to adjust." |
| Coach not assigned to session | Access denied; record rule blocks view |
| Network interruption during save | Auto-retry once; on failure, cache changes locally and sync on reconnect (future enhancement) |
| Player already marked 'present' | Button disabled; informational tooltip: "Already checked in at {time}" |
| Bulk action with mixed states | Confirm dialog: "3 players are already marked. Mark remaining 5 as present?" |
| Session interrupted (rain) after marking some present | Coach marks remaining as 'abs_unnotified' or clicks "Mark Session Complete" - session treated as complete for billing (all present players charged) |

### 3.2.7 Postconditions
- Attendance records updated with new states, timestamps, and marked_by user.
- Billing pipeline can process 'present' records.
- Guardian portal reflects updated attendance status.
- Chatter audit trail documents who marked attendance and when.
- Optional: Absence notification sent to guardians (for unnotified absences).

### 3.2.8 Data Entities & Fields
| Entity | Fields Updated |
|--------|----------------|
| academy.attendance | state, checkin_time, marked_by, write_date, write_uid |
| mail.message | Chatter post on session (subtype: attendance_marked) |

### 3.2.9 Security & Permissions
- Action visible to groups: `group_academy_coach`, `group_academy_head_coach`.
- Record rules ensure coach can only edit attendance for sessions where:
  - session.coach_id = user OR
  - user in group_academy_head_coach OR
  - session.skill_group_id in user's assigned groups (if coach portfolio model exists).
- Site admin can override with unrestricted access.

### 3.2.10 Business Rules / Validation
- State transitions:
  - 'expected' → 'present', 'abs_notified', 'abs_unnotified': Always allowed.
  - 'present' → 'abs_unnotified': Allowed with confirmation (reversal).
  - Any state → locked if attendance.billing_item_id.state = 'invoiced': Block edit.
- Timestamp required: checkin_time must be set when state = 'present'.
- marked_by always set to current user on state change.

### 3.2.11 Auditing
- Chatter message on session: `Attendance marked by {coach} at {timestamp}. Present: {count_present}, Absent: {count_absent}.`
- State transition log in `mail.tracking.value` (Odoo's built-in change tracking).
- Optional dashboard metric: Average time to complete attendance per coach.

### 3.2.12 UX Wireframe (Textual)
**Attendance List View (Today's Sessions):**
```
Academy ▸ Attendance ▸ Today's Sessions
┌────────────────────────────────────────────────────────────┐
│ Session: Group Tennis - Green Ball (Court 1, 14:00-15:00)  │
│                                                             │
│ [✓] Jordan Player        [Present] [Absent ▼]    09:58     │
│ [✓] Taylor Smith         [Present] [Absent ▼]    10:01     │
│ [ ] Alex Johnson         [Present] [Absent ▼]    —         │
│ [ ] Casey Lee            [Present] [Absent ▼]    —         │
│                                                             │
│ Selected: 2  [Mark All Present] [Export]                   │
└────────────────────────────────────────────────────────────┘
Absent Dropdown Options: Absent (Notified) | Absent (Unnotified)
```

### 3.2.13 Sequence (Textual)
```
Coach → UI: Open Today's Sessions
UI → System: Fetch sessions (filter: date=today, coach=current_user)
System → UI: Return session list
Coach → UI: Select session
UI → System: Fetch attendance records for session
System → UI: Display attendance list with action buttons
Coach → UI: Click "Present" for player P1
UI → System: Update attendance (state='present', checkin_time=now, marked_by=coach)
System → Database: Persist changes
Database → System: Commit confirmation
System → UI: Refresh row (green highlight, button disabled)
System → Chatter: Post audit message on session
System → Guardian Portal: Trigger notification (if configured)
```

### 3.2.14 Pseudo Code
```python
class AcademyAttendance(models.Model):
    _name = 'academy.attendance'
    
    def action_mark_present(self):
        self.ensure_one()
        if self.state in ['present']:
            raise UserError(_('Player is already marked present.'))
        if self._is_locked():
            raise UserError(_('Attendance is locked (already billed). Contact admin.'))
        self.write({
            'state': 'present',
            'checkin_time': fields.Datetime.now(),
            'marked_by': self.env.user.id
        })
        self.session_id.message_post(body=f"{self.player_id.name} marked present by {self.env.user.name}.")
        return True

    def action_mark_absent(self, notify=False):
        self.ensure_one()
        state = 'abs_notified' if notify else 'abs_unnotified'
        self.write({
            'state': state,
            'marked_by': self.env.user.id
        })
        if not notify:
            # Optional: Send notification to guardian about unnotified absence
            self._send_absence_notification()
        return True

    def _is_locked(self):
        return self.billing_item_id and self.billing_item_id.state == 'invoiced'

    def action_bulk_mark_present(self, attendance_ids):
        # Bulk action for multiple records
        attendances = self.browse(attendance_ids)
        unlocked = attendances.filtered(lambda a: not a._is_locked())
        unlocked.write({
            'state': 'present',
            'checkin_time': fields.Datetime.now(),
            'marked_by': self.env.user.id
        })
        if unlocked:
            session = unlocked.mapped('session_id')
            if len(session) == 1:
                session.message_post(body=f"Bulk attendance: {len(unlocked)} players marked present by {self.env.user.name}.")
        return True
```

### 3.2.15 Acceptance Criteria
| ID | Criterion |
|----|-----------|
| ATT-MARK1 | Coach can mark individual player present/absent with single click |
| ATT-MARK2 | Bulk "Mark All Present" action updates multiple records simultaneously |
| ATT-MARK3 | Timestamp and marked_by user recorded on every state change |
| ATT-MARK4 | Locked (billed) attendance records block editing with clear error message |
| ATT-MARK5 | Chatter audit trail documents all attendance changes |

---

## 3.3 Guardian Absence Request Submission

### 3.3.1 Purpose
Allow guardians to proactively notify the academy when their child cannot attend a scheduled session, converting attendance status from 'expected' to 'abs_notified' and enabling appropriate billing treatment and operational planning.

### 3.3.2 Actors
| Role | Responsibility |
|------|----------------|
| Guardian (portal user) | Submits absence request via portal for upcoming sessions |
| System | Validates submission deadline; updates attendance state; creates absence record |
| Lead Coach | Receives notification of absence (optional email/portal badge) |
| Billing System | Adjusts charges based on absence timing (on-time vs. late) |

### 3.3.3 Preconditions
- Guardian authenticated and logged into portal.
- Guardian has linked player(s) with upcoming confirmed sessions.
- Attendance records exist for sessions (state='expected').
- Absence request submission deadline configured (e.g., 2 hours before session start).
- Guardian has not already submitted absence for the same attendance record.

### 3.3.4 Triggers
1. Guardian navigates to **My Kids ▸ Sessions** or **Attendance** in portal.
2. Guardian clicks **Report Absence** button next to an upcoming session.
3. Guardian receives reminder notification of upcoming session (optional future).
4. System prompts guardian to explain repeated absences (after N consecutive).

### 3.3.5 Happy Path Flow
1. Guardian logs into portal, navigates to **My Kids ▸ Sessions**.
2. System displays upcoming sessions for guardian's children with state='expected'.
3. Guardian selects session `S` for player `P` (scheduled tomorrow at 14:00).
4. Guardian clicks **Report Absence** button.
5. System displays absence request form modal:
   - Pre-filled: Player name, session details (date, time, type).
   - Required: Reason dropdown (Illness, Travel, Family Emergency, Other).
   - Optional: Notes (free text, max 500 chars).
6. Guardian selects reason "Illness", adds note "Has a cold, will return next week", and clicks **Submit**.
7. System validates:
   - Current time < (session start time - 2 hours): PASS.
   - Attendance record exists and state='expected': PASS.
8. System processes:
   - Updates attendance: state='abs_notified', marked_by=guardian user.
   - Creates `academy.absence.request`:
     - attendance_id, player_id, guardian_id, reason, notes, submission_time.
     - Links to attendance record.
   - Posts chatter message on attendance: "Absence reported by {guardian} at {time}. Reason: {reason}."
   - Optional: Sends email notification to lead_coach_id.
9. Modal closes; portal displays confirmation: "Absence reported successfully. No charge will be applied."
10. Session card in portal updates status badge: "Absent (Notified)".

### 3.3.6 Alternative / Error Paths
| Condition | Outcome |
|-----------|---------|
| Submission within 2-hour cutoff | Error: "Cannot submit absence within 2 hours of session start. Please contact the academy directly." Attendance remains 'expected'. |
| Session already completed | Error: "Cannot report absence for past sessions." |
| Absence already submitted | Info message: "Absence already reported for this session on {date}. View details." Link to existing request. |
| Session cancelled by academy | Info: "This session has been cancelled. No absence report needed." |
| Guardian tries to report for sibling not their child | Access denied (record rule blocks viewing) |
| Network failure during submission | Auto-retry; on persistent failure, cache locally and prompt guardian to resubmit when online (future) |
| Late absence (submitted after session start) | Allowed but state set to 'abs_notified_late'; warning: "Late absence reported. Partial charge may apply per academy policy." |

### 3.3.7 Postconditions
- Attendance state updated to 'abs_notified' (or 'abs_notified_late' if late).
- Absence request record created and linked to attendance.
- Billing pipeline excludes attendance from charges (or applies partial charge if late).
- Lead coach notified via email and/or portal badge.
- Guardian portal reflects updated status.
- Chatter audit trail documents request.

### 3.3.8 Data Entities & Fields
| Entity | Fields Created/Updated |
|--------|------------------------|
| academy.attendance | state='abs_notified', marked_by=guardian_user, absence_request_id |
| academy.absence.request | id, attendance_id, player_id, guardian_id, reason, notes, submission_time, state='submitted' |
| mail.message | Chatter post on attendance and optionally player record |
| ir.config_parameter | `academy.absence_cutoff_hours` (e.g., 2) |

### 3.3.9 Security & Permissions
- Portal controllers enforce record rules: guardians can only submit for their children (player.guardian_ids contains current_user.partner_id).
- Absence request model secured:
  - Create: portal guardians (group_academy_guardian_portal).
  - Read: Guardian (own requests), lead coach (assigned players), head coach/admin (all).
  - Write/Delete: Site admin only (requests immutable after submission).

### 3.3.10 Business Rules / Validation
- Cutoff enforcement:
  - `submission_time < (session.date_start - cutoff_hours)`: On-time ('abs_notified').
  - `submission_time >= (session.date_start - cutoff_hours)`: Late ('abs_notified_late').
  - `submission_time >= session.date_end`: Error (cannot report after session completed).
- Reason mandatory; notes optional.
- One absence request per attendance record (uniqueness constraint or business logic check).
- Retroactive cancellation: Guardian cannot delete/edit submitted request (immutable); must contact admin.

### 3.3.11 Auditing
- Chatter message on attendance: `Absence reported by {guardian} at {timestamp}. Reason: {reason}. Notes: {notes}.`
- Optional email to lead coach with attendance summary.
- Dashboard metric: Absence rate by reason, by player, by time-to-notification.

### 3.3.12 UX Wireframe (Textual)
**Guardian Portal – Report Absence Modal:**
```
Report Absence
────────────────────────────────────────────
Player: Jordan Player
Session: Group Tennis - Green Ball
Date: Tomorrow, Oct 8, 2025, 14:00-15:00
Court: Court 1

Reason: [Dropdown ▼]
  Illness
  Travel
  Family Emergency
  Other

Notes (Optional):
[Text area: Has a cold, will return next week]

[Cancel]  [Submit Absence]
────────────────────────────────────────────
```

### 3.3.13 Sequence (Textual)
```
Guardian → Portal: Navigate to My Kids ▸ Sessions
Portal → System: Fetch upcoming sessions (filter: guardian's children, state='expected')
System → Portal: Display session list
Guardian → Portal: Click "Report Absence" for session S
Portal → System: Fetch session and attendance details
System → Portal: Display absence request form (pre-filled)
Guardian → Portal: Select reason, enter notes, submit
Portal → System: Validate cutoff, uniqueness
System → Attendance: Update state='abs_notified', marked_by=guardian
System → AbsenceRequest: Create record (attendance_id, player_id, guardian_id, reason, notes, time)
System → Chatter: Post audit message
System → LeadCoach: Send notification email (if configured)
System → Portal: Display confirmation message
Portal → Guardian: Refresh session list (status badge updated)
```

### 3.3.14 Pseudo Code
```python
class AcademyAbsenceRequest(models.Model):
    _name = 'academy.absence.request'
    _description = 'Player Absence Request'
    _sql_constraints = [
        ('unique_attendance', 'UNIQUE(attendance_id)', 'Absence request already exists for this attendance record.')
    ]
    
    attendance_id = fields.Many2one('academy.attendance', required=True, ondelete='cascade')
    player_id = fields.Many2one('academy.player', related='attendance_id.player_id', store=True)
    guardian_id = fields.Many2one('res.partner', required=True)
    reason = fields.Selection([
        ('illness', 'Illness'),
        ('travel', 'Travel'),
        ('emergency', 'Family Emergency'),
        ('other', 'Other')
    ], required=True)
    notes = fields.Text()
    submission_time = fields.Datetime(default=fields.Datetime.now, required=True)
    state = fields.Selection([('submitted', 'Submitted'), ('acknowledged', 'Acknowledged')], default='submitted')

    @api.model
    def create(self, vals):
        # Validate submission timing
        attendance = self.env['academy.attendance'].browse(vals['attendance_id'])
        cutoff_hours = int(self.env['ir.config_parameter'].sudo().get_param('academy.absence_cutoff_hours', 2))
        cutoff_time = attendance.session_id.date_start - timedelta(hours=cutoff_hours)
        submission = vals.get('submission_time', fields.Datetime.now())
        
        if submission >= attendance.session_id.date_end:
            raise ValidationError(_('Cannot report absence for past sessions.'))
        
        # Determine attendance state based on timing
        if submission < cutoff_time:
            absence_state = 'abs_notified'
            message = _('Absence reported successfully. No charge will be applied.')
        else:
            absence_state = 'abs_notified_late'
            message = _('Late absence reported. Partial charge may apply per academy policy.')
        
        # Update attendance
        attendance.write({
            'state': absence_state,
            'marked_by': self.env.user.id
        })
        
        # Create absence request
        request = super().create(vals)
        attendance.write({'absence_request_id': request.id})
        
        # Audit trail
        attendance.message_post(body=f"Absence reported by {request.guardian_id.name} at {request.submission_time}. Reason: {dict(request._fields['reason'].selection).get(request.reason)}. Notes: {request.notes or 'None'}.")
        
        # Notify lead coach
        if attendance.player_id.lead_coach_id:
            request._send_coach_notification()
        
        return request

    def _send_coach_notification(self):
        # Send email to lead coach
        template = self.env.ref('academy_attendance.absence_notification_email')
        template.send_mail(self.id, force_send=True)
```

### 3.3.15 Acceptance Criteria
| ID | Criterion |
|----|-----------|
| ABS1 | Guardian can submit absence request for upcoming session (>2 hours away) |
| ABS2 | Attendance state changes to 'abs_notified' with audit trail |
| ABS3 | Submission within cutoff blocked with clear error message |
| ABS4 | Late submission (after cutoff but before session end) creates 'abs_notified_late' state |
| ABS5 | Lead coach receives email notification of absence |
| ABS6 | Duplicate submission for same attendance prevented |
| ABS7 | Portal displays confirmation message and updated session status |

---

## 3.4 QR Code Check-In at Session Venue

### 3.4.1 Purpose
Provide a frictionless, contactless attendance check-in method for players and guardians at the court entrance using QR codes, reducing administrative overhead and enabling real-time attendance tracking without manual coach intervention.

### 3.4.2 Actors
| Role | Responsibility |
|------|----------------|
| System | Generates unique, time-limited QR codes per session with security token |
| Guardian/Player | Scans QR code using mobile device camera or portal app |
| Public Endpoint | Validates token, session timing, player registration; updates attendance |
| Coach | Displays QR code at venue (optional printed sign or mobile device) |

### 3.4.3 Preconditions
- Session confirmed with attendance records in state='expected' or already marked.
- QR code generated for session (unique token + session_id encoded).
- Player registered for session (attendance record exists).
- Check-in window active: session.date_start - 30 minutes to session.date_end + 30 minutes (configurable).
- Mobile device with camera or portal app installed.

### 3.4.4 Triggers
1. Coach clicks **Generate QR Code** button on session form or mobile app.
2. Site admin prints QR code poster for court entrance.
3. Guardian/player arrives at court and scans QR code.
4. Portal displays session check-in page with QR scanner.

### 3.4.5 Happy Path Flow
1. Coach opens session form (starts in 15 minutes), clicks **Generate QR Code**.
2. System generates unique token:
   - Token structure: `{session_id}:{timestamp}:{hmac_signature}` (Base64 encoded).
   - HMAC signed using secret key from `ir.config_parameter`.
   - Token valid for session duration + grace window (e.g., ±30 minutes).
3. System displays QR code modal with:
   - QR code image (encoded URL: `https://dev.smarts4.homes/academy/attendance/checkin?token={encoded_token}`).
   - Session details: Name, time, court, participant count.
   - Optional: Print/Download buttons.
4. Guardian arrives at court, opens camera app, and scans QR code.
5. Camera app opens URL in mobile browser: `/academy/attendance/checkin?token=ABC123XYZ`.
6. Public endpoint (no auth required) receives request:
   - Decodes and validates token (signature, expiry, session exists).
   - Checks current time within check-in window.
   - Displays player selection page (if URL lacks `player_id`):
     - Lists all players registered for session with state='expected' or 'abs_notified'.
     - Guardian selects their child (or multiple if applicable).
7. Guardian clicks **Check In** for player `P`.
8. System validates:
   - Player registered for session: PASS.
   - Attendance state not already 'present': PASS.
   - Session within check-in window: PASS.
9. System updates attendance:
   - state='present'
   - checkin_time=now
   - marked_by=public (or guardian user if authenticated)
   - checkin_method='qr_code'
10. System displays confirmation page:
    - "Check-in successful for Jordan Player!"
    - Session details and next steps (e.g., "Proceed to Court 1").
11. Optional: Send push notification to guardian app (future).

### 3.4.6 Alternative / Error Paths
| Condition | Outcome |
|-----------|---------|
| Token expired (>30 min past session end) | Error page: "QR code expired. Please request a new code from your coach." |
| Token signature invalid (tampered) | Error page: "Invalid QR code. Please verify the source." |
| Session not found (session_id invalid) | Error page: "Session not found. Contact academy support." |
| Player already checked in | Info page: "You're already checked in for this session at {time}!" (Idempotent—no error, just confirmation) |
| Player not registered for session | Error page: "You are not registered for this session. Please contact the academy." |
| Check-in outside window (>30 min before session) | Error page: "Check-in not available yet. You can check in starting 30 minutes before the session." |
| Check-in far after session (>30 min past end) | Error page: "Check-in window closed. Please contact your coach for manual attendance marking." |
| Network timeout during validation | Retry prompt: "Network error. Please try again." (Client-side retry logic) |
| Player state='abs_notified' (absence already reported) | Override prompt: "An absence was reported for this session. Check in anyway? [Yes] [No]" (Allows correction if guardian/player arrives unexpectedly) |

### 3.4.7 Postconditions
- Attendance state updated to 'present' with check-in timestamp and method.
- Guardian/player receives visual confirmation.
- Coach can view real-time check-in status on session attendance tab.
- Billing pipeline processes 'present' attendance as usual.
- Optional: Chatter message on session logs QR check-in event.

### 3.4.8 Data Entities & Fields
| Entity | Fields Created/Updated |
|--------|------------------------|
| academy.attendance | state='present', checkin_time, checkin_method='qr_code', marked_by (public or authenticated user) |
| academy.session | qr_token (computed or transient; regenerated on demand), qr_generated_at |
| ir.config_parameter | `academy.qr_secret_key`, `academy.qr_checkin_window_minutes` (default 30) |

### 3.4.9 Security & Permissions
- QR endpoint: Public access (no authentication required) but token validation mandatory.
- Token security:
  - HMAC-SHA256 signature prevents tampering.
  - Timestamp validates token age.
  - Session-bound: token includes session_id; cannot be reused for other sessions.
- Rate limiting: Max 10 requests per IP per minute to prevent brute-force scanning.
- CORS: Endpoint allows cross-origin requests (mobile browsers).

### 3.4.10 Business Rules / Validation
- Check-in window: `session.date_start - 30 min` to `session.date_end + 30 min`.
- Token expiry: Tokens invalid after check-in window closes.
- Idempotent: Scanning QR code multiple times for same player harmless (displays "already checked in").
- Override absence: If player state='abs_notified', allow check-in with confirmation (overrides absence, updates to 'present').
- Billing impact: QR check-in equivalent to coach marking present (generates billable item).

### 3.4.11 Auditing
- Chatter message on session (if verbose logging enabled): `QR check-in: {player_name} at {timestamp} via token {token_id}.`
- System log (INFO): `[QR-CHECKIN] Player {player_id} checked in for session {session_id} at {time}.`
- Optional metrics: QR check-in adoption rate, average check-in time vs. session start.

### 3.4.12 UX Wireframe (Textual)
**QR Code Generation Modal (Coach View):**
```
Generate QR Code – Session: Group Tennis - Green Ball
──────────────────────────────────────────────────────
[QR Code Image]            Session Details:
                           Date: Oct 8, 2025, 14:00-15:00
                           Court: Court 1
                           Players: 12 registered
                           
                           Check-in window: 
                           13:30 - 15:30

[Print] [Download PNG] [Close]
──────────────────────────────────────────────────────
```

**Mobile Check-In Page (Public Endpoint):**
```
Academy Check-In
──────────────────────────────────────────────────────
Session: Group Tennis - Green Ball
Date: Today, 14:00-15:00
Court: Court 1

Select Your Player:
○ Jordan Player
○ Taylor Smith

[Check In]
──────────────────────────────────────────────────────
```

**Confirmation Page:**
```
✅ Check-In Successful!
──────────────────────────────────────────────────────
Player: Jordan Player
Session: Group Tennis - Green Ball
Time: 13:58 (2 minutes early)

Proceed to Court 1. Enjoy your session!

[View My Sessions] [Done]
──────────────────────────────────────────────────────
```

### 3.4.13 Sequence (Textual)
```
Coach → SessionForm: Click "Generate QR Code"
SessionForm → System: Invoke generate_qr_token(session_id)
System → Crypto: Create HMAC-signed token
Crypto → System: Return encoded token
System → SessionForm: Display QR code modal (URL with token)
Guardian → Camera: Scan QR code
Camera → Browser: Open URL (/academy/attendance/checkin?token=...)
Browser → PublicEndpoint: HTTP GET with token
PublicEndpoint → System: Validate token (decode, verify HMAC, check expiry)
System → PublicEndpoint: Return session details + player list
PublicEndpoint → Browser: Display player selection page
Guardian → Browser: Select player, click "Check In"
Browser → PublicEndpoint: HTTP POST (token, player_id)
PublicEndpoint → System: Validate player registration, check-in window
System → Attendance: Update state='present', checkin_time=now, method='qr_code'
System → PublicEndpoint: Return success
PublicEndpoint → Browser: Display confirmation page
System → Chatter: Post audit message (optional)
```

### 3.4.14 Pseudo Code
```python
import hmac
import hashlib
import base64
from datetime import timedelta
from odoo import http, fields
from odoo.http import request

class AcademySession(models.Model):
    _name = 'academy.session'
    
    qr_token = fields.Char(compute='_compute_qr_token')
    qr_generated_at = fields.Datetime()

    def action_generate_qr_code(self):
        self.ensure_one()
        token = self._generate_qr_token()
        return {
            'type': 'ir.actions.act_url',
            'url': f'/academy/attendance/checkin?token={token}',
            'target': 'new'
        }

    def _generate_qr_token(self):
        secret = self.env['ir.config_parameter'].sudo().get_param('academy.qr_secret_key')
        timestamp = int(fields.Datetime.now().timestamp())
        payload = f"{self.id}:{timestamp}"
        signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()
        token = base64.urlsafe_b64encode(f"{payload}:{signature}".encode()).decode()
        self.write({'qr_generated_at': fields.Datetime.now()})
        return token

class AcademyAttendancePublic(http.Controller):
    @http.route('/academy/attendance/checkin', type='http', auth='public', website=True)
    def checkin_page(self, token=None, **kwargs):
        if not token:
            return request.render('academy_attendance.error_invalid_qr')
        
        # Decode and validate token
        try:
            decoded = base64.urlsafe_b64decode(token.encode()).decode()
            session_id, timestamp, signature = decoded.split(':')
            session_id = int(session_id)
        except:
            return request.render('academy_attendance.error_invalid_qr')
        
        # Verify HMAC signature
        secret = request.env['ir.config_parameter'].sudo().get_param('academy.qr_secret_key')
        expected_sig = hmac.new(secret.encode(), f"{session_id}:{timestamp}".encode(), hashlib.sha256).hexdigest()
        if signature != expected_sig:
            return request.render('academy_attendance.error_invalid_qr')
        
        # Check session exists and within check-in window
        session = request.env['academy.session'].sudo().browse(session_id)
        if not session.exists():
            return request.render('academy_attendance.error_session_not_found')
        
        window_minutes = int(request.env['ir.config_parameter'].sudo().get_param('academy.qr_checkin_window_minutes', 30))
        now = fields.Datetime.now()
        start_window = session.date_start - timedelta(minutes=window_minutes)
        end_window = session.date_end + timedelta(minutes=window_minutes)
        
        if now < start_window:
            return request.render('academy_attendance.error_too_early', {'session': session, 'start_window': start_window})
        if now > end_window:
            return request.render('academy_attendance.error_too_late', {'session': session})
        
        # Fetch players with expected attendance
        attendances = request.env['academy.attendance'].sudo().search([
            ('session_id', '=', session_id),
            ('state', 'in', ['expected', 'abs_notified'])
        ])
        
        return request.render('academy_attendance.checkin_select_player', {
            'session': session,
            'attendances': attendances,
            'token': token
        })

    @http.route('/academy/attendance/checkin/confirm', type='http', auth='public', methods=['POST'], website=True, csrf=False)
    def checkin_confirm(self, token=None, attendance_id=None, **kwargs):
        # Re-validate token (same logic as above, omitted for brevity)
        # ...
        
        attendance = request.env['academy.attendance'].sudo().browse(int(attendance_id))
        if not attendance.exists() or attendance.state == 'present':
            return request.render('academy_attendance.already_checked_in', {'attendance': attendance})
        
        # Override absence if needed
        if attendance.state in ['abs_notified', 'abs_notified_late']:
            # Optional: Log override event
            attendance.message_post(body="Absence overridden by QR check-in.")
        
        attendance.write({
            'state': 'present',
            'checkin_time': fields.Datetime.now(),
            'checkin_method': 'qr_code',
            'marked_by': request.env.user.id if not request.env.user._is_public() else False
        })
        
        return request.render('academy_attendance.checkin_success', {'attendance': attendance})
```

### 3.4.15 Acceptance Criteria
| ID | Criterion |
|----|-----------|
| QR1 | QR code generated with unique, HMAC-signed token per session |
| QR2 | Scanning QR code within check-in window displays player selection page |
| QR3 | Selecting player and confirming updates attendance to 'present' with timestamp |
| QR4 | Expired or tampered tokens display clear error messages |
| QR5 | Player already checked in displays confirmation (idempotent) |
| QR6 | Check-in outside window blocked with informative error |
| QR7 | Absence override prompt displayed if player state='abs_notified' |

---

## 3.5 Acceptance Traceability Summary
Linking requirements to attendance stories:
- Attendance model & generation (Roadmap Checklist) → Story 3.1 (ATT-GEN1–ATT-GEN5)
- Coach marking attendance (Roadmap Checklist) → Story 3.2 (ATT-MARK1–ATT-MARK5)
- Absence request flow (Roadmap Checklist) → Story 3.3 (ABS1–ABS7)
- QR endpoint & token security (Roadmap Checklist) → Story 3.4 (QR1–QR7)
- Billing integration with attendance states (Roadmap Section 6.4) → Story 3.2 (ATT-MARK4), Story 3.3 (ABS2–ABS4)

