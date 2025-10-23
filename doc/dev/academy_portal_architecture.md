# Academy Portal Architecture

## Overview

The Academy Portal provides differentiated web access for three distinct user types: **Guardians**, **Players**, and **Coaches**. Each role has tailored portal views and permissions appropriate to their needs while leveraging Odoo's built-in portal infrastructure.

## Portal User Types

### 1. Guardian Portal Access

**Security Group**: `academy_core.group_academy_guardian`
- Inherits from: `base.group_portal`
- Privilege: `academy_core.res_groups_privilege_academy`

**Purpose**: Allow parents/guardians to monitor their children's academy participation.

**Key Fields on `res.partner`**:
- `academy_is_guardian` - Boolean flag marking partner as guardian
- `academy_guardian_child_ids` - Many2many to `academy.player` (children as guardians)
- `academy_primary_player_ids` - Many2many to `academy.player` (children where primary guardian)

**Portal Features**:
- View children's upcoming sessions
- Report absences for scheduled sessions
- View session history and attendance
- Access billing information (via academy_billing module)

**Portal Routes** (defined in `academy_core/controllers/portal.py`):

```python
from odoo.addons.portal.controllers.portal import CustomerPortal

class AcademyPortal(CustomerPortal):
    
    @http.route(['/my/sessions'], type='http', auth='user', website=True)
    def portal_my_sessions(self, **kwargs):
        """Guardian view of children's sessions."""
        
    @http.route(['/my/children'], type='http', auth='user', website=True)
    def portal_my_children(self, **kwargs):
        """List guardian's children."""
        
    @http.route(['/my/sessions/<int:occurrence_id>/report_absence'], 
                type='http', auth='user', website=True)
    def portal_report_absence(self, occurrence_id, **kwargs):
        """Report absence for a session."""
```

**Critical Pattern - `.sudo()` Usage**:
Portal controllers must use `.sudo()` to bypass access control since portal users don't have internal user access:

```python
@http.route(['/my/sessions'], type='http', auth='user', website=True)
def portal_my_sessions(self, **kwargs):
    partner = request.env.user.partner_id
    players = partner.academy_guardian_child_ids.sudo()
    
    # Portal user can't normally read academy.session.occurrence
    # Use sudo() to bypass access control
    sessions = request.env['academy.session.occurrence'].sudo().search([
        ('skill_group_id', 'in', players.mapped('skill_group_id').ids),
        ('state', '=', 'planned'),
    ])
```

**Templates** (XML views in `academy_core/views/portal_guardian_templates.xml`):
- `portal_my_home` - Extended to show session counts
- `portal_my_sessions` - Session list view
- `portal_my_children` - Children list with details
- `portal_session_detail` - Individual session details with absence reporting

---

### 2. Player Portal Access

**Security Group**: `academy_core.group_academy_player_portal`
- Inherits from: `base.group_portal`
- Privilege: `academy_core.res_groups_privilege_academy`

**Purpose**: Elevated access for older/mature players to view their own schedules.

**Elevation Process**:
Players can be "elevated" to portal users via wizard in `academy_core/wizard/player_elevation_wizard.py`:

```python
class PlayerElevationWizard(models.TransientModel):
    _name = 'academy.player.elevation.wizard'
    
    def action_elevate(self):
        """Create portal user for player."""
        player = self.player_id
        
        # Create user linked to player's partner_id
        user = self.env['res.users'].create({
            'login': player.email,
            'partner_id': player.partner_id.id,
            'groups_id': [(6, 0, [
                self.env.ref('base.group_portal').id,
                self.env.ref('academy_core.group_academy_player_portal').id,
            ])],
        })
        
        player.portal_user_id = user
```

**Access Control**:
- Players can only view their own sessions (not siblings')
- Limited to viewing schedule and attendance
- Cannot report absences (must be done by guardian)

**Portal Features**:
- View personal upcoming sessions
- View personal session history
- View skill group information
- View assigned coach details

**Elevation Criteria** (configurable per player):
- `elevation_allowed` field must be `True` on player record
- Player must have valid email address
- Player must not already have portal user

**Button in Player Form** (`academy_core/views/academy_player_views.xml`):
```xml
<header>
    <button name="action_open_elevation_wizard" 
            string="Elevate to Portal" 
            type="object"
            class="btn-primary" 
            invisible="portal_user_id"/>
    <field name="portal_user_id" widget="badge" 
           invisible="not portal_user_id"/>
</header>
```

---

### 3. Coach Internal Access (Not Portal)

**Security Group**: `academy_core.group_academy_coach`
- Does NOT inherit from portal
- Full internal user access
- Privilege: `academy_core.res_groups_privilege_academy`

**Key Fields on `res.users`**:
- `academy_is_coach` - Boolean flag marking user as coach
- `academy_coach_skill_groups` - Many2many to `academy.skill.group` (assigned groups)
- `is_academy_head_coach` - Computed field checking group membership
- `is_academy_site_admin` - Computed field checking admin status

**Access Levels**:

**Regular Coach** (`group_academy_coach`):
- View assigned players and skill groups
- View assigned sessions (via `Today's Sessions` menu)
- Mark attendance for assigned sessions
- Create individual sessions for assigned players
- View but cannot modify session templates

**Head Coach** (`group_academy_head_coach`):
- Inherits all coach permissions
- Create and modify session templates
- Create weekly schedules
- Assign sessions to coaches
- Suspend sessions/seasons
- Full scheduling authority

**Site Admin** (`group_academy_site_admin`):
- Inherits head coach permissions
- Configure skill groups
- Configure courts and resources
- Manage security settings
- Access billing configuration
- System configuration access

**Calendar Scoping**:
Coaches only see sessions relevant to them (implemented via domain filters):

```python
# In academy_session_occurrence_views.xml
<record id="action_academy_today_sessions" model="ir.actions.act_window">
    <field name="domain">[
        ('date', '=', context_today().strftime('%Y-%m-%d')),
        ('state', '=', 'planned'),
        '|',
        ('coach_id', '=', uid),  # Assigned as coach
        ('skill_group_id', 'in', user.academy_coach_skill_groups.ids),  # Assigned skill group
    ]</field>
</record>
```

---

## Portal Infrastructure

### CustomerPortal Base Class

All portal controllers inherit from `odoo.addons.portal.controllers.portal.CustomerPortal`:

```python
from odoo.addons.portal.controllers.portal import CustomerPortal

class AcademyPortal(CustomerPortal):
    
    def _prepare_home_portal_values(self, counters):
        """Override to add academy-specific counts to portal home."""
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        
        # Get guardian's children
        players = (partner.academy_guardian_child_ids.sudo() or 
                  partner.academy_primary_player_ids.sudo())
        
        if 'session_count' in counters:
            # Count upcoming sessions for all children
            session_count = 0
            for player in players:
                session_count += self.env['academy.session.occurrence'].sudo().search_count([
                    ('date', '>=', fields.Date.today()),
                    ('state', '=', 'planned'),
                    '|',
                    ('skill_group_id', '=', player.skill_group_id.id),
                    ('player_ids', 'in', player.id),
                ])
            values['session_count'] = session_count
        
        return values
```

### Portal Menu Integration

Portal menus added to `/my` home (template inheritance):

```xml
<template id="portal_my_home_menu_academy" 
          inherit_id="portal.portal_my_home">
    <xpath expr="//div[hasclass('o_portal_docs')]" position="inside">
        <t t-call="portal.portal_docs_entry">
            <t t-set="title">Sessions</t>
            <t t-set="url" t-value="'/my/sessions'"/>
            <t t-set="count" t-value="session_count"/>
        </t>
    </xpath>
</template>
```

---

## Security Patterns

### Record Rules (Row-Level Security)

Portal users require record rules to access data (defined in `security/academy_security.xml`):

```xml
<!-- Guardians can read their children's players -->
<record id="academy_player_guardian_rule" model="ir.rule">
    <field name="name">Guardian: Read Own Children</field>
    <field name="model_id" ref="model_academy_player"/>
    <field name="domain_force">[
        '|',
        ('guardian_ids', 'in', [user.partner_id.id]),
        ('primary_guardian_id', '=', user.partner_id.id)
    ]</field>
    <field name="groups" eval="[(4, ref('group_academy_guardian'))]"/>
    <field name="perm_read" eval="True"/>
    <field name="perm_write" eval="False"/>
    <field name="perm_create" eval="False"/>
    <field name="perm_unlink" eval="False"/>
</record>

<!-- Players can read their own sessions -->
<record id="academy_session_player_rule" model="ir.rule">
    <field name="name">Player Portal: Read Own Sessions</field>
    <field name="model_id" ref="academy_schedule.model_academy_session_occurrence"/>
    <field name="domain_force">[
        '|',
        ('player_ids', 'in', [user.partner_id.academy_player_id.id]),
        ('skill_group_id', '=', user.partner_id.academy_player_id.skill_group_id.id)
    ]</field>
    <field name="groups" eval="[(4, ref('group_academy_player_portal'))]"/>
    <field name="perm_read" eval="True"/>
    <field name="perm_write" eval="False"/>
    <field name="perm_create" eval="False"/>
    <field name="perm_unlink" eval="False"/>
</record>
```

### Model Access Rights (Table-Level Security)

Defined in `security/ir.model.access.csv`:

```csv
id,name,model_id:id,group_id:id,perm_read,perm_write,perm_create,perm_unlink
access_academy_player_guardian,academy.player.guardian,model_academy_player,group_academy_guardian,1,0,0,0
access_academy_session_guardian,academy.session.occurrence.guardian,academy_schedule.model_academy_session_occurrence,group_academy_guardian,1,0,0,0
access_academy_player_portal,academy.player.portal,model_academy_player,group_academy_player_portal,1,0,0,0
```

---

## Absence Reporting Workflow

Guardians can report absences through portal (key feature):

```python
@http.route(['/my/sessions/<int:occurrence_id>/report_absence'], 
            type='http', auth='user', website=True, methods=['POST'])
def portal_report_absence(self, occurrence_id, **kwargs):
    """Guardian reports child absence."""
    occurrence = request.env['academy.session.occurrence'].sudo().browse(occurrence_id)
    player_id = int(kwargs.get('player_id'))
    reason = kwargs.get('reason', '')
    
    # Verify guardian owns this player
    partner = request.env.user.partner_id
    player = request.env['academy.player'].sudo().browse(player_id)
    
    if partner not in (player.guardian_ids | player.primary_guardian_id):
        raise werkzeug.exceptions.Forbidden()
    
    # Create absence record
    request.env['academy.session.absence'].sudo().create({
        'occurrence_id': occurrence_id,
        'player_id': player_id,
        'reason': reason,
        'state': 'reported',
        'reported_by': partner.id,
    })
    
    return request.redirect('/my/sessions')
```

**Absence States**:
- `reported` - Guardian submitted absence
- `acknowledged` - Coach acknowledged the report
- `excused` - Marked as excused absence
- `unexcused` - Marked as unexcused absence

---

## Multi-User-Type Architecture Summary

The portal architecture supports three distinct access patterns:

1. **External Portal Users (Guardians/Players)**:
   - Limited web access via portal routes
   - `.sudo()` required in controllers for data access
   - Record rules enforce data visibility
   - No backend UI access

2. **Internal Users (Coaches)**:
   - Full Odoo backend access
   - Menu items filtered by security groups
   - Domain filters limit data visibility
   - Can access all Odoo apps based on groups

3. **Administrators (Site Admin)**:
   - Full system access
   - Configuration abilities
   - User management
   - System settings access

This architecture provides appropriate access levels while maintaining security boundaries and preventing unauthorized data access.
