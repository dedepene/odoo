# Tennis Academy Management System – Definitive Roadmap (Zero‑Compromise Version)

Audience: Engineer with Python skills, not necessarily Odoo‑savvy. This version removes all previous interim compromises. Anything not purely a base configuration toggle or branding adjustment is delivered via explicit custom modules. Guardians (Parents) ALWAYS authenticate (portal user accounts). Players (Kids) are managed entities (no account) with an optional controlled elevation path to become authenticated users (e.g., older competitive players) without data duplication.

Top-Level Sections:
1. Objectives & Non‑Negotiables
2. Identity & Access Model (IAM)
3. Domain Model (Canonical Entities)
4. Module Architecture Overview
5. Pure Configuration & Styling Scope (Hard Limits)
6. Custom Module Specifications
7. Security & Record Rules Design
8. Lifecycle & Elevation Flows (Player ➜ User, Session ➜ Billing)
9. Phase Delivery Plan
10. Risks & Mitigations
11. Enhancements & Future Extensions
12. Naming / Conventions
13. Requirements Mapping Matrix
14. Execution Checklist

---
## 1. Objectives & Non‑Negotiables
1. Guardians ALWAYS have authenticated portal accounts (no anonymous calendar sharing).
2. Players are first‑class managed records (no login) with an elevation path creating a linked user only when required.
3. All functional behaviors (attendance, absence notification, billing aggregation, session generation, consumables tracking) implemented via custom modules—no manual spreadsheet stopgaps.
4. Session visibility strictly scoped: Guardians only see sessions relevant to their children; Coaches see only their assigned or group sessions; Head Coaches have broader oversight.
5. No paid or proprietary Odoo apps; only core + custom.
6. Data integrity constraints enforced at the ORM layer (DOB required, at least one guardian, valid court allocation, no overlapping coach sessions).
7. Full audit trail: Every invoice line traceable to a Billing Item referencing either a Session Attendance or Consumable Line.
8. Indoor dome suspension is a domain concept halting future generation and optionally cancelling existing sessions in range.
9. All user‑facing terminology is domain aligned (no generic ERP vocabulary in portal).
10. Elevation of player to user never duplicates partner data—reuses partner row & attaches `res.users`.
11. Mandatory reporting deliverables: (a) Monthly Player Attendance Report (per player summarizing counts, breakdown by session type). (b) Versioned Player Progress Report (coach-authored, period-scoped, comment-rich, immutable after publish except new version). Both accessible to guardians (their children) and lead coach; progress also to elevated player account.

Out‑of‑Scope (Intentionally Excluded Initially): Payroll, HR contracts, generic CRM lead pipeline, manufacturing, inventory routing beyond consumables products, mass marketing automation.

---
## 2. Identity & Access Model (IAM)
| Actor | Authentication | Backing Model(s) | Notes |
|-------|----------------|------------------|-------|
| Guardian | Yes (portal) | `res.users` + `res.partner` (flags) | Always has login; manages children, billing, absences |
| Player | No (default) / Optional Elevation | `academy.player` + underlying `res.partner` | Elevation creates a `res.users` linked to same partner |
| Coach | Yes (internal user) | `res.users` (+ optional `hr.employee`) | Categorized: head, senior, associate, visiting |
| Site Admin | Yes (internal) | `res.users` | Billing + configuration |
| Head Coach | Yes | `res.users` | Scheduling authority |

Elevation Flow (Player ➜ Auth User): On demand wizard validates age/permission → creates `res.users` with restricted group set (read sessions, view own attendance, optional training feedback). Reversible by archiving user (player record persists).

## 3. Domain Model (Canonical Entities)
Core Models (all custom unless noted):
- `academy.player`  (inherits partner via _inherits) – holds player metadata (DOB, skill group, guardians, lead coach)
- `academy.guardian.link` (optional explicit link model if richer guardian attributes needed; else many2many with extra columns)
- `academy.skill.group` – predefined: red, orange, green, hard, advanced; includes constraints (age ranges, optional max size)
- `academy.coach` (could extend `res.users` with coach category field; thin model for search/grouping convenience)
- `academy.court` – court number, surface, active, indoor flag
- `academy.session.template` – weekly recurrence pattern
- `academy.session` – instantiated sessions (group or individual)
- `academy.session.participant` – explicit pivot (if per-player attributes needed e.g. fee override); else m2m
- `academy.attendance` – presence status per player per session
- `academy.absence.request` – structured absence notifications (pre- vs post-session)
- `academy.suspension` – time windows halting generation
- `academy.billing.item` – atomic billable unit
- `academy.consumable.line` – running tally items
- `academy.billing.batch` – monthly consolidation step (pre-invoice staging)
- `academy.progress.entry` (future) – evaluation/progression
- `academy.progress.report` – versioned progress documents (coach-entered) with period start/end, skill metrics, narrative, version sequence

Key Invariants / Constraints:
- Player must have ≥1 guardian; exactly one primary guardian.
- DOB required and not future.
- Skill group required; domain ensures allowed age bracket at save (configurable tolerances).
- Session cannot overlap on the same court/time window.
- Coach cannot be double-booked overlapping times (unless flagged allow_overlap for visiting).
- Billing item unique per (session, player) with state machine (pending → rated → invoiced).
- Indoor suspension prevents generation & optionally mass-cancels pending sessions in window.

## 4. Module Architecture Overview
| Module | Purpose | Depends On |
|--------|---------|------------|
| `academy_core` | Players, guardians, skill groups, coaches, courts, base security | base, contacts |
| `academy_schedule` | Templates, session generation, suspension logic, overlap checks | academy_core, calendar |
| `academy_attendance` | Attendance + absence requests + check-in mechanisms | academy_schedule |
| `academy_billing` | Billing items, batch monthly aggregation, invoice creation | academy_attendance, account |
| `academy_consumables` | Consumable capture + integration to billing | academy_billing, product |
| `academy_portal` | Guardian & (elevated) player portal pages | academy_* modules |
| `academy_security` | Centralized record rules & groups (can merge into core if preferred) | academy_core |
| `academy_reporting` | KPIs, dashboards, pivot views | academy_billing |
| `academy_progress` | Player development tracking | academy_core |

Dependency Principles: No circular deps; portal sits atop stack; reporting aggregates; progress isolated.

## 5. Pure Configuration & Styling Scope (Hard Limits)
Only the following are handled via configuration (no custom logic):
- Installation of core base modules: base, web, portal, contacts, calendar, account, product.
- Company branding (logo, colors) & portal theme adjustments.
- Removal/hiding of irrelevant menus (via security group XML, not ad hoc manual toggling).
- Translation overrides / label renames (Players, Guardians, Sessions, Courts).
Everything else (even if “could be hacked” through tags or generic calendars) is intentionally delivered as code for consistency, validation, and auditability.

## 6. Custom Module Specifications
### 6.1 `academy_core`
Features:
- Models: player, skill.group, coach (or coach category on res.users), court.
- Player inherits partner; fields: partner_id, dob, skill_group_id, guardian_ids (m2m), primary_guardian_id, emergency_contact_id, lead_coach_id, active.
- Constraints: guardian & dob presence; age vs skill group range.
- On player create: assign a generated reference (sequence).
- Wizards: Player elevation to user (generate portal or limited user account) with group assignment; revocation.
- Security groups: guardian_portal, player_portal (elevated), coach, head_coach, site_admin.

Pseudo (selected excerpts):
```python
class AcademyPlayer(models.Model):
    _name = 'academy.player'
    _inherits = {'res.partner': 'partner_id'}
    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade')
    reference = fields.Char(default=lambda self: self.env['ir.sequence'].next_by_code('academy.player'))
    dob = fields.Date(required=True)
    skill_group_id = fields.Many2one('academy.skill.group', required=True)
    guardian_ids = fields.Many2many('res.partner', relation='academy_player_guardian_rel',
                                    column1='player_id', column2='guardian_id',
                                    domain=[('is_guardian','=',True)])
    primary_guardian_id = fields.Many2one('res.partner', domain=[('is_guardian','=',True)], required=True)
    lead_coach_id = fields.Many2one('res.users', domain=[('is_coach','=',True)])

    @api.constrains('dob')
    def _check_dob(self):
        today = fields.Date.today()
        for rec in self:
            if rec.dob > today:
                raise ValidationError('DOB cannot be in the future.')
```

### 6.2 `academy_schedule`
Features:
- Session Template: weekday, start_time, duration, session_type, skill_group_id, court_ids, coach_id, active season range.
- Cron: generate rolling horizon (e.g., 6 weeks) honoring suspension windows.
- Conflict checks: court & coach overlaps.
- Individual sessions: wizard selecting players + court/time ad hoc.
- Session types: tennis_group, tennis_individual, physical_group, physical_individual.

### 6.3 `academy_attendance`
Features:
- Attendance states: expected, present, abs_notified, abs_unnotified.
- Automatic creation for each (session, player) at session confirmation.
- Guardian portal absence request converts expected → abs_notified if submitted prior cutoff.
- Check-in methods: (a) Coach list view action, (b) QR kiosk (per-session token endpoint), (c) Optional PIN for elevated player user.

### 6.4 `academy_billing`
Features:
- Billing Item creation from attendance (present) with pricing logic (group vs individual vs physical) referencing configurable price matrix.
- Monthly cron aggregates items by primary guardian → creates draft invoices (grouped by category lines).
- Traceability: invoice line has Many2one to billing item; billing item state set to invoiced post creation.
- Adjustments: Manual credit/debit note wizard referencing original billing items.

### 6.5 `academy_consumables`
Features:
- Consumable entry form (guardian, optional player, product, qty, unit price default from product; allow override).
- Recomputes guardian outstanding total (computed field).
- Integrates with billing batch to emit billing items (origin_type = consumable).

### 6.6 `academy_portal`
Features:
- Pages: Dashboard (kids summary + next sessions), Sessions (filter by date & skill group), Attendance History, Billing Summary (open invoices + unpaid total), Submit Absence, Profile.
- Controllers enforce guardian scoping: query domain on player_ids in guardian relation.
- Elevated player view: limited to own sessions/history.

### 6.7 `academy_security`
Features:
- Record rules: guardians see only players they guard; sessions limited to those tied through skill group or explicit participant mapping; attendance limited similarly; billing items only those of their players.
- Coaches: see sessions they coach or group sessions of their assigned players.
- Head Coach: unrestricted session + schedule design rights.

### 6.8 `academy_reporting`
Features:
- Monthly Player Attendance Report: parameterized by month/year (or arbitrary date range) generating per player metrics: total sessions scheduled, present count, absence (notified vs unnotified), attendance percentage, breakdown by session_type.
- Aggregated coach utilization: total coached hours vs capacity, per coach.
- Court utilization heatmap: occupancy ratio per court per hour block.
- Revenue split: session fees vs consumables vs extras.
- Age eligibility export (DOB + skill group + attendance count) – CSV / XLSX.
- Technical Implementation: SQL views / materialized helper model `academy.report.player_attendance` regenerated nightly; dynamic pivot views for ad-hoc drill.

Data Sources:
- Attendance & Sessions (academy_attendance / academy_schedule)
- Billing Items (academy_billing)
- Players & Skill Groups (academy_core)
- Consumables (academy_consumables)

Access:
- Guardians: Only rows for their children (filtered domain on report view or served via portal endpoint).
- Coaches: Only players they lead (except head coach: full academy).

Performance Approach:
- Monthly snapshot table (optional) to avoid recomputation for historical months; incremental refresh at month boundary.

Pseudo SQL View (illustrative):
```sql
CREATE OR REPLACE VIEW academy_report_player_attendance AS
SELECT
  a.player_id,
  p.primary_guardian_id AS guardian_id,
  DATE_TRUNC('month', s.date_start AT TIME ZONE 'UTC')::date AS month_start,
  COUNT(*) FILTER (WHERE att.status = 'present') AS present_count,
  COUNT(*) FILTER (WHERE att.status = 'abs_notified') AS abs_notified_count,
  COUNT(*) FILTER (WHERE att.status = 'abs_unnotified') AS abs_unnotified_count,
  COUNT(*) AS total_scheduled,
  ROUND(
    CASE WHEN COUNT(*) = 0 THEN 0
         ELSE (COUNT(*) FILTER (WHERE att.status = 'present')::decimal / COUNT(*)::decimal)*100 END, 2
  ) AS attendance_pct,
  COUNT(*) FILTER (WHERE s.session_type = 'tennis_group' AND att.status='present') AS present_tennis_group,
  COUNT(*) FILTER (WHERE s.session_type = 'tennis_individual' AND att.status='present') AS present_tennis_individual,
  COUNT(*) FILTER (WHERE s.session_type = 'physical_group' AND att.status='present') AS present_physical_group,
  COUNT(*) FILTER (WHERE s.session_type = 'physical_individual' AND att.status='present') AS present_physical_individual
FROM academy_session s
JOIN academy_attendance att ON att.session_id = s.id
JOIN academy_player a ON a.id = att.player_id
JOIN res_partner rp ON rp.id = a.partner_id
JOIN academy_player p ON p.id = a.id -- alias for clarity
GROUP BY a.player_id, p.primary_guardian_id, DATE_TRUNC('month', s.date_start AT TIME ZONE 'UTC');
```

Pseudo Progress Report Model Snippet:
```python
class ProgressReport(models.Model):
    _name = 'academy.progress.report'
    _description = 'Player Progress Report'
    _order = 'player_id, version_number desc'

    player_id = fields.Many2one('academy.player', required=True)
    lead_coach_id = fields.Many2one('res.users', required=True, domain=[('is_coach','=',True)])
    period_start = fields.Date(required=True)
    period_end = fields.Date(required=True)
    narrative = fields.Html()
    technique_score = fields.Integer()
    tactics_score = fields.Integer()
    physical_score = fields.Integer()
    mental_score = fields.Integer()
    version_number = fields.Integer(required=True, default=1)
    state = fields.Selection([('draft','Draft'),('published','Published'),('archived','Archived')], default='draft')
    published_date = fields.Datetime(readonly=True)

    def action_publish(self):
        for rec in self:
            if rec.state != 'draft':
                continue
            rec.write({'state': 'published', 'published_date': fields.Datetime.now()})

    def action_new_version(self):
        self.ensure_one()
        if self.state != 'published':
            raise UserError('Can only version a published report')
        new_vals = self.copy_data()[0]
        new_vals.update({'state': 'draft', 'version_number': self.version_number + 1})
        return self.create(new_vals)
```

### 6.9 `academy_progress` (Future)
Features:
- Evaluation rubric entries (per dimension: technique, tactics, physical, mental) normalized in child model for potential analytics.
- Versioned Progress Report model `academy.progress.report` with: player_id, lead_coach_id, period_start, period_end, narrative, skill_group_recommendation, version_number (auto increment per player), state (draft, published, archived), published_date.
- Security: Once published, immutable except archival; new edits require creating a new version (wizard clones previous metrics).
- Portal Exposure: Guardians & elevated player can view all published versions; lead coach can create new versions; other coaches read-only if they have player relationship.
- Integration: Optionally attach progress report link on scheduling/attendance views for quick context.

## 7. Security & Record Rules Design
Principles:
- Deny by default; open via explicit group & domain.
- Portal guardians never access `res.partner` generic lists—only filtered players via custom controllers.
- Elevated players: a separate portal group; cannot view siblings or other players.
- Coach overlap prevention adhered at create/write of session.

Example Rules (Conceptual Domains):
- Attendance (guardian): `[('player_id.guardian_ids','in', user.partner_id.id)]`
- Session (guardian): `[('skill_group_id.player_ids.guardian_ids','in', user.partner_id.id)] OR explicit participant link`
- Billing Item (guardian): `[('player_id.guardian_ids','in', user.partner_id.id)]`

## 8. Lifecycle & Elevation Flows
### Player Creation Flow
1. Create guardians (partners + users auto if not existing).
2. Create player with guardians, DOB, skill group.
3. System assigns default lead coach (group rule or manual).

### Session Generation Flow
Template → Cron → Sessions (6 weeks) → Attendance rows materialized → Portal visible.

### Absence Flow
Guardian submits absence request (before configurable cutoff) → Attendance state updated to abs_notified → Billing engine excludes or applies absence policy (e.g., still bill if late notice).

### Billing Flow
End of month cron selects uninvoiced billing items (present attendances + consumables) → groups by guardian → creates draft invoice → marks billing items invoiced.

### Elevation Flow (Player ➜ Auth User)
Wizard: select player → validate age/flag allow_elevation → create `res.users` with limited group `group_academy_player_portal` → link to same partner → add portal pages subset.

## 9. Phase Delivery Plan
| Phase | Deliverables | Modules |
|-------|--------------|---------|
| 1 | Core identities, guardians as users, players model, skill groups, courts | academy_core, academy_security |
| 2 | Scheduling engine & session generation | academy_schedule |
| 3 | Attendance + absence requests + portal basic pages | academy_attendance, academy_portal |
| 4 | Billing items + monthly invoicing + consumables integration | academy_billing, academy_consumables |
| 5 | Reporting dashboards | academy_reporting |
| 6 | Player elevation + progress tracking | elevation wizard (core), academy_progress |
| 7 | Optimization & enhancements (QR check-in, analytics refinements) | iterative |

## 10. Risks & Mitigations
| Risk | Impact | Mitigation |
|------|--------|------------|
| Time drift / DST in session generation | Misaligned times | Store timezone & use pytz conversions at generation |
| Overbilling due to absence timing | Disputes | Configurable cutoff & audit log on absence modifications |
| Double booking courts | Operational conflict | Constraint + SQL uniqueness across (court_id, time range) |
| Performance with large attendance sets | Slow billing run | Batch processing + indexed foreign keys |
| Data privacy leakage | Legal / trust issues | Strict record rules + portal only via custom controllers |
| Elevation misuse | Unneeded user proliferation | Age/approval gate + group auditing |

## 11. Enhancements & Future Extensions
- Push notifications (web push) for last-minute schedule changes.
- Skill progression analytics microservice (lightweight scoring).
- AI-based session load balancing (coach workload fairness).
- Federation export formats (CSV/JSON spec mapping).
- Auto-generated progress deltas (highlight changes vs previous version) using computed comparison fields.

## 12. Naming / Conventions
- Module prefix: `academy_`.
- External IDs: `academy_<module>.<model>_<slug>`.
- Sequences: `ACADEMY_PLAYER`, `ACADEMY_SESSION`, `ACADEMY_BILLING_ITEM`.
- Security Groups: `group_academy_guardian`, `group_academy_player_portal`, `group_academy_coach`, `group_academy_head_coach`, `group_academy_site_admin`.
- Python: snake_case fields, explicit compute/inverse names.

## 13. Requirements Mapping Matrix
| Original Requirement | Delivery Mechanism | Module |
|----------------------|--------------------|--------|
| Player DOB mandatory | ORM constraint | academy_core |
| Skill grouping | Skill group model + relation | academy_core |
| Guardian association + primary/emergency | Player guardian m2m + primary field | academy_core |
| Guardians act on behalf of kids | Portal controllers with guardian scoping | academy_portal |
| Guardian mandatory contact info | Required fields on guardian partner/user create | academy_core |
| Coach categories | Field on user + selection | academy_core |
| Lead coach assignment | m2o field + default assignment rule | academy_core |
| Weekly recurring schedule | Template + cron generation | academy_schedule |
| Indoor dome suspension | Suspension model halting cron + mass cancel | academy_schedule |
| Individual sessions | Ad hoc session wizard | academy_schedule |
| Restricted schedule visibility | Record rules + filtered portal controllers | academy_security / academy_portal |
| Attendance capture frictionless | Attendance model + QR / coach UI | academy_attendance |
| Absence notification | Absence request model + state transition | academy_attendance |
| Monthly invoice w/ sessions & consumables | Billing aggregation cron + invoice creation | academy_billing |
| Running consumables total | Consumable lines + outstanding computed | academy_consumables |
| Trace invoice to attendance | Billing item foreign keys | academy_billing |
| Elevate player to user | Elevation wizard | academy_core |
| Progress / evaluations | Progress entries | academy_progress |
| Monthly attendance report per player | Player attendance reporting view + portal/pdf | academy_reporting |
| Versioned progress report (period, comments) | Versioned progress.report model + publish workflow | academy_progress |

## 14. Execution Checklist
Core:
- [ ] Scaffold `academy_core` (models, sequences, security groups)
- [ ] Implement guardian & player constraints
- [ ] Elevation wizard skeleton

Schedule:
- [ ] Session template model & cron
- [ ] Overlap constraints (court/coach)
- [ ] Suspension handling

Attendance:
- [ ] Attendance model & generation
- [ ] Absence request flow
- [ ] QR endpoint & token security

Billing & Consumables:
- [ ] Billing item pipeline
- [ ] Monthly batch cron
- [ ] Invoice builder & trace links
- [ ] Consumables entry & integration

Portal & Security:
- [ ] Portal controllers (dashboard, sessions, attendance, billing)
- [ ] Record rules implementation
- [ ] Access group tests

Reporting / Progress:
- [ ] KPI pivot views
- [ ] Progress evaluation forms
- [ ] Monthly player attendance report view + guardian portal access
- [ ] Versioned progress report model & publish workflow
- [ ] Export actions (CSV/XLSX) for attendance & eligibility

Quality / Ops:
- [ ] Unit tests (constraints, generation, billing)
- [ ] Data load scripts (skill groups, courts)
- [ ] Documentation (ER diagram, sequence flows)

