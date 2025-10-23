# Academy Module Dependencies

## Overview

The Tennis Academy Management System consists of three interconnected modules that build upon each other in a clear dependency chain. Each module extends the functionality of its dependencies while maintaining clear separation of concerns.

## Dependency Chain

```
academy_core (Foundation)
    ↓
academy_schedule (Scheduling Layer)
    ↓
academy_billing (Business Layer)
```

## Module Breakdown

### 1. academy_core (Foundation Layer)

**Purpose**: Provides core domain models, security infrastructure, and base workflows for the tennis academy.

**Dependencies**:
- `base` - Odoo core framework
- `contacts` - Contact/partner management
- `portal` - Portal user infrastructure
- `sale` - Sales order integration
- `account` - Accounting integration

**Key Models**:
- `academy.player` - Tennis player records (inherits from `res.partner`)
- `academy.skill.group` - Skill level groupings (e.g., Green Ball, Orange Ball)
- `res.partner` extensions - Guardian tracking fields
- `res.users` extensions - Coach role management

**Security Groups** (defined in `security/academy_security.xml`):
- `group_academy_guardian` - Portal guardians (inherits `base.group_portal`)
- `group_academy_player_portal` - Elevated player accounts
- `group_academy_coach` - Coach access
- `group_academy_head_coach` - Head coach with scheduling authority
- `group_academy_site_admin` - Site administrators

**Key Features**:
- Player enrollment with automatic reference numbering (`PLR0001`, etc.)
- Guardian relationship management (primary + additional guardians)
- Age-based skill group assignment with validation
- Portal elevation wizard for creating player portal accounts
- Coach assignment and tracking
- Custom name display for players (`[Skill Group] Player Name`)

**Data Files**:
- `data/academy_sequences.xml` - Player reference number sequences

**Portal Access**:
- Guardian portal templates for viewing children's information
- Practice session visibility for guardians
- Portal user creation for players when elevated

---

### 2. academy_schedule (Scheduling Layer)

**Purpose**: Comprehensive scheduling module for session management, court allocation, and attendance tracking.

**Dependencies**:
- `academy_core` - Requires core models and security
- `calendar` - Odoo calendar integration

**Key Models**:
- `academy.court` - Court/facility management
- `academy.season` - Season definitions with start/end dates
- `academy.season.suspension` - Season-wide suspensions (dome installation, tournaments)
- `academy.session.template` - Weekly recurring session templates
- `academy.session.occurrence` - Individual session instances (generated from templates or ad-hoc)
- `academy.session.absence` - Absence tracking and reporting
- `academy.attendance` - Attendance records for billing

**Wizards**:
- `weekly_schedule_wizard` - Bulk template creation for regular schedules
- `individual_session_wizard` - Ad-hoc individual session booking with conflict detection
- `suspension_wizard` - Season suspension creation
- `attendance_wizard` - Mark attendance with walk-in support

**Key Features**:
- Automatic occurrence generation from weekly templates
- Court conflict detection and validation
- Player double-booking prevention
- Session suspension during academy closures
- Follow-up physical training session auto-linking
- Calendar visibility scoping by role (coaches see assigned sessions only)
- Absence reporting workflow (reported → acknowledged → excused/unexcused)
- Walk-in player support with skill group mismatch warnings

**Session Types**:
- `tennis_group` - Group tennis skills training
- `physical_group` - Group physical activities
- `tennis_individual` - Individual tennis coaching
- `physical_individual` - Individual physical training

**State Management**:
Session occurrences flow through states:
- `planned` - Normal scheduled session
- `suspended` - Temporarily suspended (preserves original state)
- `cancelled` - Cancelled permanently
- `completed` - Finished session

**Data Files**:
- `data/session_type_data.xml` - Default session type configurations

**Critical Pattern - Data Loading Order**:
The `__manifest__.py` demonstrates a critical Odoo pattern:
```python
'data': [
    'security/ir.model.access.csv',
    'data/session_type_data.xml',
    
    # Actions defined first
    'views/academy_session_occurrence_views.xml',  # Defines actions
    'wizard/individual_session_wizard_views.xml',
    
    # Menus loaded LAST - they reference actions above
    'views/academy_schedule_menu_views.xml',
]
```

---

### 3. academy_billing (Business Layer)

**Purpose**: Automated billing generation from attendance records with accounting integration.

**Dependencies**:
- `academy_schedule` - Requires attendance records
- `account` - Invoice generation (inherited from academy_core)

**Key Models**:
- `academy.billing.template` - Configurable billing templates per guardian
- `academy.billing.item` - Individual billable items (linked to attendance)
- `academy.attendance.billing` - Monthly billing aggregation

**Key Features**:
- Automatic billing item creation from attendance records
- Template-based pricing (group vs individual, tennis vs physical)
- Guardian-specific billing configurations
- Monthly billing aggregation via cron job
- Invoice generation integration with Odoo accounting
- Support for custom line items (fees, equipment, etc.)

**Cron Jobs** (defined in `data/attendance_billing_cron.xml`):
- `cron_generate_monthly_billing` - Monthly billing generation (runs 1st of month)

**Configuration Parameters** (system-wide pricing):
- `academy.billing.group_tennis_price` - Default: $25.00
- `academy.billing.group_physical_price` - Default: $20.00
- `academy.billing.individual_tennis_price` - Default: $60.00
- `academy.billing.individual_physical_price` - Default: $50.00

**Billing Workflow**:
1. Attendance marked in `academy_schedule`
2. Attendance record creates `academy.billing.item`
3. Items associated with guardian billing template
4. Monthly cron aggregates items into invoices
5. Invoices created in Odoo accounting system

---

## Integration Points

### academy_core → academy_schedule
- **Players** enrolled in core are scheduled in sessions
- **Skill groups** from core determine session eligibility
- **Coaches** from core are assigned to sessions
- **Guardians** from core receive session notifications (portal)

### academy_schedule → academy_billing
- **Attendance records** automatically generate billing items
- **Session types** determine pricing (group vs individual, tennis vs physical)
- **Session dates** used for monthly billing aggregation
- **Guardians** linked from players receive consolidated invoices

### Cross-Module Data Flow

```
Player Enrolled (core)
    ↓
Assigned to Skill Group (core)
    ↓
Sessions Created for Group (schedule)
    ↓
Attendance Marked (schedule)
    ↓
Billing Item Generated (billing)
    ↓
Monthly Invoice Created (billing → accounting)
```

## Installation Order

When installing modules, follow the dependency chain:

```bash
# 1. Install core first
python odoo-bin -c odoo.conf -i academy_core -d odoo

# 2. Install scheduling
python odoo-bin -c odoo.conf -i academy_schedule -d odoo

# 3. Install billing
python odoo-bin -c odoo.conf -i academy_billing -d odoo

# Or install all at once (Odoo resolves dependencies automatically)
python odoo-bin -c odoo.conf -i academy_core,academy_schedule,academy_billing -d odoo
```

## Upgrade Order

When upgrading modules, upgrade in dependency order or use `-u all`:

```bash
# Upgrade specific modules in order
python odoo-bin -c odoo.conf -u academy_core,academy_schedule,academy_billing -d odoo --stop-after-init

# Or upgrade all modules
python odoo-bin -c odoo.conf -u all -d odoo --stop-after-init
```

## Module Independence

Each module maintains clear boundaries:

- **academy_core**: No knowledge of scheduling or billing - focuses purely on domain entities
- **academy_schedule**: Depends on core models but has no billing logic - pure scheduling
- **academy_billing**: Only depends on attendance data - doesn't modify scheduling logic

This separation allows:
- Independent testing of each layer
- Potential replacement of billing module without affecting scheduling
- Clear upgrade paths and rollback strategies
- Easier debugging (failures isolated to specific layers)
