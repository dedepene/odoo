# Academy Core – Implementation Handover

## Summary
- Introduced a new `academy_core` custom module delivering the foundational models, security, and processes required by the roadmap’s execution checklist (core items).
- Added canonical skill group and player models, constraints enforcing guardian relationships and age alignment, and the initial player elevation wizard.
- Established dedicated security groups, menus, and sequences tailored to the tennis academy domain.

## Module Contents
| Area | Key Elements |
|------|--------------|
| Models | `academy.player`, `academy.skill.group`, partner/user extensions for guardian and coach flags |
| Wizards | `academy.player.elevation.wizard` for controlled portal user creation |
| Security | New module category plus guardian, player, coach, head coach, and site admin groups |
| Data | Player reference sequence `academy.player` |
| Views | Player & skill group CRUD, elevation wizard form, academy menu shell |
| Tests | Constraint coverage in `tests/test_player_constraints.py` |

### Dependencies
- Base apps: `base`, `contacts`, `portal`.
- External libraries: relies on `python-dateutil` already bundled with Odoo for `relativedelta`.

## Models & Constraints
### `academy.player`
- Delegates to `res.partner` via `_inherits` ensuring unified contact management.
- Mandatory fields: DOB, skill group, guardians, primary guardian.
- Constraints:
  - Prevent future DOB entries.
  - Enforce at least one guardian and ensure the primary guardian is among them.
  - Require guardian partners to have both an email and a phone (or mobile) number.
  - Validate age alignment against the linked skill group’s range when enforced.
- Automations:
  - Autogenerates a `reference` code via `ir.sequence`.
  - Flags linked partner as `academy_is_player` and guardians as `academy_is_guardian`.

### `academy.skill.group`
- Defines age band metadata with optional enforcement toggle.
- Supplies uniqueness constraints on `name` and `code` and validates age bounds.

### Partner & User Extensions
- `res.partner`: adds guardian/player flags plus read-only linkages to players.
- `res.users`: introduces coach/category attributes; supports domain filtering and future rule building.

## Security & Navigation
- `ir.module.category` **Academy** groups the new roles for clarity.
- Groups created:
  - `group_academy_guardian` → inherits portal access.
  - `group_academy_player_portal` → limited player portal rights.
  - `group_academy_coach`, `group_academy_head_coach`, `group_academy_site_admin` → internal roles.
- Access controls: head coaches (RW create) and site admins (full CRUD) on players/skill groups; coaches read-only player visibility.
- Menus: new “Academy” root with Players workspace and Configuration → Skill Groups.

## Elevation Wizard
- Located under `wizard/player_elevation_wizard.py`.
- Presents login/email inputs, optional inheritance of guardian portal groups, and a toggle to send welcome/reset emails.
- Generates a `res.users` for the player, attaches portal groups, and stores the link on `academy.player.portal_user_id`.
- Exposed via form header button, disabled once a user exists.

## Tests
- Transactional coverage validates:
  - Guardian requirement and primary guardian selection.
  - Guardian contact completeness.
  - Skill group age enforcement.
  - Successful creation path including reference sequencing.
- Tagging: `@tagged('post_install', '-at_install')` for execution after module install.

## Configuration Steps Post-Deploy
1. Install `academy_core` with the academy database enabled.
2. Seed canonical skill groups (red/orange/green/hard/advanced) via the new menu or data import.
3. Create guardian partners (ensuring email + phone) and assign them portal credentials.
4. Create players using the new interface, linking guardians and lead coaches.
5. Elevate players selectively through the form action once prerequisites are met.

## Follow-Up / Open Items
- Record rules are still pending (targeted for portal/security checklist tasks).
- Player elevation currently supports welcome email via standard reset flow; customize template later if desired.
- Coach flagging is manual; consider automation once scheduling module lands.
- Review guardian data migration from legacy sources before production cutover.
