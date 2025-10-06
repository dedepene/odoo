# Tennis Academy – User Stories

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

