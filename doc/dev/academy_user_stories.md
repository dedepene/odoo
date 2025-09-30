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
