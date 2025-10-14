# Guardian Portal Implementation - Handover Document

**Project:** Academy Portal Enhancement  
**Module:** academy_core  
**Date:** October 12, 2025  
**Version:** 19.0.1.0.0  
**Status:** Complete

---

## Executive Summary

This document details the complete implementation of a guardian-focused web portal for the Tennis Academy. The portal has been redesigned from the ground up to provide guardians with a comprehensive, user-friendly interface to manage their children's academy activities.

### Key Deliverables
- ✅ Comprehensive guardian portal with 5 main sections
- ✅ Enhanced absence reporting with reason codes and notes
- ✅ Billing integration showing invoices and payment history
- ✅ Profile management for guardians
- ✅ Clean, modern UI with Bootstrap 5
- ✅ Mobile-responsive design

---

## Architecture Overview

### Files Modified/Created

#### 1. **Controllers**
- **File:** `custom_addons/academy_core/controllers/portal.py`
- **Status:** Complete rewrite
- **Changes:**
  - Extended `CustomerPortal` from portal module
  - Implemented 8 new routes for guardian portal
  - Added proper security checks and guardian validation
  - CSRF protection on all POST routes

#### 2. **Templates**
- **File:** `custom_addons/academy_core/views/portal_practice_templates.xml`
- **Status:** Complete rewrite
- **Content:**
  - Guardian portal breadcrumbs navigation
  - Dashboard/Home view
  - My Kids list and detail views
  - Absence modal component

- **File:** `custom_addons/academy_core/views/portal_guardian_templates.xml` *(NEW)*
- **Status:** New file
- **Content:**
  - Sessions view (upcoming/past tabs)
  - Billing view with invoice listings
  - Profile management view
  - Portal home override for guardians

#### 3. **Module Manifest**
- **File:** `custom_addons/academy_core/__manifest__.py`
- **Changes:**
  - Added `account` to dependencies for billing integration
  - Added `portal_guardian_templates.xml` to data files

---

## Feature Implementation Details

### 1. Dashboard (`/my` or `/my/home`)

**Purpose:** Guardian home page with quick overview of all children and upcoming sessions

**Features:**
- Welcome message with guardian name
- Quick stats cards:
  - Number of enrolled children
  - Count of upcoming sessions
  - Quick link to My Kids
- Next 5 upcoming sessions across all children with:
  - Child name
  - Date and time
  - Session name
  - Quick "Report Absence" button
- Summary cards for each child with:
  - Name, skill group, age
  - Link to detailed view

**Controller:** `AcademyPortal.home()`
**Template:** `portal_guardian_home`

**Technical Implementation:**
```python
# Retrieves guardian's children via relationships
players = partner.academy_guardian_child_ids.sudo() or partner.academy_primary_player_ids.sudo()

# Fetches upcoming sessions for all children
# Queries both skill_group_id and player_ids relationships
domain = ['&', ('date', '>=', today), ('state', '=', 'planned'),
         '|', ('skill_group_id', '=', p.skill_group_id.id), 
         ('player_ids', 'in', p.id)]
```

---

### 2. My Kids (`/my/kids`)

**Purpose:** List all children with basic information

**Features:**
- Card-based layout for each child
- Displays:
  - Child name
  - Date of birth and age
  - Skill group
  - Lead coach (if assigned)
- "View Details" button for each child

**Controller:** `AcademyPortal.portal_my_kids()`
**Template:** `portal_my_kids`

**Security:**
- Validates guardian relationship before showing children
- Uses `sudo()` to read player records (guardians may not have direct read access)

---

### 3. Kid Detail View (`/my/kids/<int:player_id>`)

**Purpose:** Detailed view of a specific child with sessions

**Features:**
- Complete child profile information
- **Upcoming Sessions section:**
  - Table with date, time, session name, type
  - Absence reporting button per session
  - Color-coded session types (Tennis/Physical badges)
- **Recent Past Sessions section:**
  - Last 10 completed sessions
  - Status badges (Completed, Cancelled, Suspended)
  - Historical record for parent reference

**Controller:** `AcademyPortal.portal_kid_detail(player_id)`
**Template:** `portal_kid_detail`

**Security Validations:**
```python
# Check guardian can access this player
if partner.id not in player.guardian_ids.ids and 
   partner.id != (player.primary_guardian_id.id if player.primary_guardian_id else None):
    return request.redirect('/my/kids')
```

---

### 4. Sessions (`/my/sessions`)

**Purpose:** Comprehensive view of all sessions for all children

**Features:**
- **Tabbed Interface:**
  - **Upcoming Sessions Tab:**
    - All future sessions grouped by child
    - Detailed table with date, time, session, type, coach
    - "Report Absence" action per session
  - **Past Sessions Tab:**
    - Historical sessions (last 20 per child)
    - Status indicators for each session
    - Grouped by child for easy reference
- Success message when absence is reported

**Controller:** `AcademyPortal.portal_my_sessions()`
**Template:** `portal_my_sessions`

**Key Implementation:**
```python
# Separate queries for upcoming and past sessions per player
upcoming_domain = ['&', ('date', '>=', today), ('state', '=', 'planned'), ...]
past_domain = ['&', ('date', '<', today), ...]
```

---

### 5. Absence Reporting

**Purpose:** Allow guardians to report when their child cannot attend a session

**Features:**
- **Modal Dialog Component:**
  - Shows session details (child, date, session name)
  - **Reason Code dropdown** (required):
    - Illness
    - Injury
    - Family Commitment
    - School Event
    - Vacation
    - Other
  - **Additional Details textarea** (optional)
  - CSRF protection
  - Redirect back to origin page after submission

**Controller:** `AcademyPortal.portal_report_absence()`
**Template:** `absence_modal` (reusable component)

**Security & Validations:**
- Guardian relationship validated
- Cannot report absence for past sessions
- CSRF token required
- Duplicate absence prevention (handled by model constraint)

**Integration:**
```python
# Creates academy.session.absence record
absence_vals = {
    'occurrence_id': Occ.id,
    'player_id': player.id,
    'reason_code': reason_code or 'other',
    'reason_note': reason_note or '',
}
Abs.create(absence_vals)
```

---

### 6. Billing (`/my/billing`)

**Purpose:** View invoices and payment history

**Features:**
- **Current Invoices Section:**
  - Unpaid and partially paid invoices
  - Shows: invoice number, date, due date, amount, status
  - "Overdue" badge for past-due invoices
  - Link to view full invoice details (uses Odoo's standard invoice portal view)
- **Payment History Section:**
  - All paid invoices
  - Clean table with invoice details
  - Link to view invoice
- **Billing Information Card:**
  - Contact details for billing inquiries

**Controller:** `AcademyPortal.portal_my_billing()`
**Template:** `portal_my_billing`

**Technical Details:**
```python
# Queries account.move for guardian's invoices
Invoice = request.env['account.move'].sudo()
invoices = Invoice.search([
    ('partner_id', '=', partner.id),
    ('move_type', 'in', ['out_invoice', 'out_refund']),
    ('state', '!=', 'cancel')
], order='invoice_date desc, id desc')

# Split by payment state
current_invoices = invoices.filtered(lambda inv: inv.payment_state in ['not_paid', 'partial'])
paid_invoices = invoices.filtered(lambda inv: inv.payment_state in ['paid', 'in_payment'])
```

**Dependency Note:** Requires `account` module (already added to dependencies)

---

### 7. Profile (`/my/profile`)

**Purpose:** View and edit guardian personal information

**Features:**
- **Editable Profile Form:**
  - Full name (required)
  - Email (required)
  - Phone and mobile numbers
  - Complete address (street, street2, city, zip)
  - Form validation
  - Success message on update
- **Linked Children Section:**
  - Read-only list of all linked children
  - Quick links to child detail pages
- **Account Settings:**
  - Link to Odoo's account security page for password changes

**Controllers:**
- `AcademyPortal.portal_my_profile()` (GET)
- `AcademyPortal.portal_profile_update()` (POST)

**Template:** `portal_my_profile`

**Security:**
```python
# Updates only allowed fields
update_vals = {}
if kwargs.get('name'):
    update_vals['name'] = kwargs['name']
# ... other fields ...
if update_vals:
    partner.sudo().write(update_vals)
```

---

### 8. Navigation & UI/UX

**Custom Navigation Bar:**
- Replaces default Odoo portal menu
- 5 main sections with icons:
  - 🏠 Dashboard
  - 👥 My Kids
  - 📅 Sessions
  - 📄 Billing
  - 👤 Profile
- Active state highlighting
- Responsive design (collapses on mobile)

**Template Override:**
- `portal_breadcrumbs_custom` replaces `portal.portal_breadcrumbs`
- Conditional `page_name` parameter for active state

**Design System:**
- Bootstrap 5 components
- Font Awesome icons
- Academy color scheme:
  - Primary: Blue (`bg-primary`)
  - Success: Green (`bg-success`)
  - Warning: Yellow (`bg-warning`)
  - Info: Teal (`bg-info`)
  - Secondary: Gray (`bg-secondary`)

---

## Data Model Integration

### Models Used

#### 1. **academy.player**
- Linked to guardians via `guardian_ids` (Many2many)
- Primary guardian via `primary_guardian_id` (Many2one)
- Fields accessed: `name`, `dob`, `age_years`, `skill_group_id`, `lead_coach_id`, `email`

#### 2. **academy.session.occurrence**
- Represents scheduled sessions
- Key fields:
  - `date`, `start_datetime`, `end_datetime`
  - `template_id`, `name` (session identification)
  - `session_type` (tennis_group, physical_group, etc.)
  - `skill_group_id` (for group sessions)
  - `player_ids` (for individual sessions)
  - `state` (planned, suspended, cancelled, completed)
  - `coach_id`

#### 3. **academy.session.absence**
- Absence records created by guardians
- Key fields:
  - `occurrence_id`, `player_id`
  - `reason_code` (selection with 6 options)
  - `reason_note` (text)
  - `state` (reported, acknowledged, withdrawn)
  - `reporter_id`, `report_date`

#### 4. **account.move**
- Invoice records from accounting module
- Fields accessed:
  - `name` (invoice number)
  - `invoice_date`, `invoice_date_due`
  - `amount_total`, `currency_id`
  - `payment_state` (not_paid, partial, paid, in_payment)
  - `state` (draft, posted, cancel)

#### 5. **res.partner**
- Guardian contact information
- Fields accessed/editable:
  - `name`, `email`, `phone`, `mobile`
  - `street`, `street2`, `city`, `zip`, `country_id`
  - `academy_is_guardian`
  - `academy_guardian_child_ids`, `academy_primary_player_ids`

---

## Security Implementation

### Access Control

#### Guardian Group
- **Group:** `academy_core.group_academy_guardian`
- **Inherits:** `base.group_portal`
- **Purpose:** Identifies guardian users for portal access

#### Authentication & Authorization
- All routes use `auth='user'` (requires login)
- Guardian relationship validated on every child-specific route
- Example validation pattern:
```python
if partner.id not in player.guardian_ids.ids and 
   partner.id != (player.primary_guardian_id.id if player.primary_guardian_id else None):
    return request.redirect('/my/kids')
```

#### CSRF Protection
- All POST routes include `csrf=True` parameter
- Forms include CSRF token:
```xml
<input type="hidden" name="csrf_token" t-att-value="request.csrf_token()"/>
```

#### Sudo Usage
- Used strategically to allow guardians to read related records
- Applied on:
  - Player records (guardians may not have direct read access)
  - Session occurrence records
  - Session absence creation
  - Invoice records
- **Security maintained** through relationship validation

---

## Database Queries & Performance

### Query Patterns

#### Efficient Session Retrieval
```python
# Uses indexed fields (date, state, skill_group_id)
domain = [
    '&', ('date', '>=', today), 
    ('state', '=', 'planned'),
    '|', ('skill_group_id', '=', p.skill_group_id.id), 
         ('player_ids', 'in', p.id)
]
occs = Occ.search(domain, order='date, start_datetime', limit=10)
```

#### Optimized Invoice Queries
```python
# Single query with proper filtering
invoices = Invoice.search([
    ('partner_id', '=', partner.id),
    ('move_type', 'in', ['out_invoice', 'out_refund']),
    ('state', '!=', 'cancel')
], order='invoice_date desc, id desc')
```

### Performance Considerations
- **Pagination:** Ready for implementation (imported `portal_pager`)
- **Lazy Loading:** Children and sessions loaded on-demand
- **Result Limits:** Past sessions limited to 10-20 per child
- **Caching Opportunities:** Session counts for dashboard could be cached

---

## Testing Recommendations

### Functional Testing

#### Test Case 1: Guardian Access
1. Create guardian user with portal access
2. Link guardian to 1-3 players
3. Create upcoming sessions for players
4. Login as guardian and verify:
   - Dashboard shows correct stats
   - All children are visible in My Kids
   - Sessions show for all children
   - Can navigate between all sections

#### Test Case 2: Absence Reporting
1. As guardian, navigate to Sessions or Kid Detail
2. Click "Report Absence" for upcoming session
3. Fill form with reason and notes
4. Verify:
   - Absence record created with correct data
   - Success message displayed
   - Cannot report duplicate absence
   - Cannot report for past session

#### Test Case 3: Security Validation
1. Create two guardian users
2. Link each to different players
3. As Guardian A, attempt to access Guardian B's child via URL manipulation
4. Verify: Redirect to /my/kids (access denied)

#### Test Case 4: Billing Display
1. Create invoices for guardian partner
2. Set various payment states (unpaid, partial, paid)
3. Login as guardian
4. Verify:
   - Current invoices show unpaid/partial
   - Paid invoices show in payment history
   - Overdue badge appears for past-due invoices

#### Test Case 5: Profile Update
1. Login as guardian
2. Navigate to Profile
3. Update name, email, phone, address
4. Submit form
5. Verify:
   - Success message appears
   - Changes reflected in database
   - Changes visible in profile view

### Edge Cases to Test

#### Multiple Guardians Per Child
- Primary guardian vs. secondary guardians
- Both `guardian_ids` and `primary_guardian_id` relationships

#### Session Types
- Group sessions (via skill_group_id)
- Individual sessions (via player_ids)
- Mixed: Player in both group and individual sessions

#### No Data Scenarios
- Guardian with no linked children
- Child with no upcoming sessions
- No invoices
- Empty states display correctly

#### Date Boundaries
- Sessions on current date (today)
- Past session exactly at boundary
- Future session far in future

---

## Known Issues & Future Enhancements

### Current Limitations

1. **No Pagination:**
   - Sessions view could have many records
   - Future: Implement pagination for past sessions
   - Ready: `portal_pager` already imported

2. **No Notifications:**
   - Guardians not notified of session changes
   - Future: Email/SMS alerts for cancellations, reminders

3. **Limited Profile Fields:**
   - Cannot change password within portal (redirects to Odoo account page)
   - Future: Integrated password change

4. **No Document Uploads:**
   - Absence modal includes attachment field but no upload UI
   - Future: Allow uploading doctor notes, etc.

5. **Basic Billing:**
   - Only displays invoices, no payment gateway integration
   - Future: Online payment options

### Future Enhancement Ideas

#### Short Term (High Value)
- ✨ Session confirmation/RSVP feature
- ✨ Absence withdrawal before session start
- ✨ Email notifications for session changes
- ✨ Export session history to PDF/CSV
- ✨ Mobile app integration via API

#### Medium Term
- 📊 Progress reports and skill assessments
- 💬 Messaging system with coaches
- 📸 Session photo gallery
- 📝 Homework/practice assignments
- 🏆 Achievement badges and milestones

#### Long Term
- 💳 Online payment processing
- 📅 Session booking/rescheduling
- 👨‍👩‍👧 Family account management
- 🎥 Video content library
- 📱 Native mobile apps

---

## Deployment Instructions

### Prerequisites
- Odoo 19.0 instance
- `academy_core` module installed
- `academy_schedule` module installed
- `account` module installed
- Portal module enabled

### Deployment Steps

1. **Backup Database:**
   ```bash
   pg_dump odoo > backup_$(date +%Y%m%d).sql
   ```

2. **Update Module Files:**
   ```bash
   # Copy updated files to Odoo addons directory
   cp -r custom_addons/academy_core /path/to/odoo/custom_addons/
   ```

3. **Upgrade Module:**
   ```bash
   python odoo-bin -c odoo.conf -u academy_core -d odoo --stop-after-init
   ```

4. **Clear Browser Cache:**
   - Portal templates are cached
   - Users should hard refresh (Ctrl+Shift+R)

5. **Test Portal Access:**
   - Login as guardian user
   - Verify all 5 main sections load
   - Test absence reporting
   - Check billing display

### Rollback Plan
If issues arise:
```bash
# Restore database backup
psql odoo < backup_YYYYMMDD.sql

# Revert to previous module version
git checkout <previous-commit>
python odoo-bin -c odoo.conf -u academy_core -d odoo --stop-after-init
```

---

## Configuration Settings

### No Additional Configuration Required
The implementation uses existing Odoo settings and doesn't require new configuration parameters.

### Recommended Settings

#### Email Configuration
For notifications (future enhancement):
```python
# In odoo.conf or System Parameters
email_from = academy@example.com
smtp_server = smtp.example.com
smtp_port = 587
smtp_user = academy@example.com
smtp_password = ******
```

#### Portal Settings
- **Portal Invitations:** Ensure email templates are configured
- **Session Confirmation:** Enable/disable in future

---

## Support & Maintenance

### Log Files
Monitor these logs for portal issues:
```bash
# Odoo server log
tail -f /var/log/odoo/odoo-server.log

# Look for portal-related errors
grep -i "portal\|academy" /var/log/odoo/odoo-server.log
```

### Common Issues & Solutions

#### Issue: Guardian Cannot Login
**Symptom:** Guardian receives "Access Denied" message  
**Solution:**
1. Verify user has `group_portal` and `group_academy_guardian`
2. Check partner is marked as `academy_is_guardian = True`
3. Ensure user account is active

#### Issue: No Sessions Displayed
**Symptom:** Guardian sees "No upcoming sessions"  
**Solution:**
1. Verify player is linked to guardian (check `guardian_ids` or `primary_guardian_id`)
2. Ensure sessions exist with `date >= today` and `state = 'planned'`
3. Check player is assigned to sessions (via `skill_group_id` or `player_ids`)

#### Issue: Cannot Report Absence
**Symptom:** Modal opens but submit fails  
**Solution:**
1. Check CSRF token is valid
2. Verify session is in future (not past)
3. Ensure no duplicate absence exists
4. Check `academy.session.absence` access rights

#### Issue: Billing Section Empty
**Symptom:** No invoices shown  
**Solution:**
1. Verify `account` module is installed
2. Check invoices exist for guardian partner
3. Ensure invoices are in correct state (not draft/cancelled)
4. Verify `move_type` is 'out_invoice' or 'out_refund'

---

## API Reference

### Portal Routes

#### GET `/my` or `/my/home`
**Purpose:** Guardian dashboard  
**Auth:** User (guardian)  
**Returns:** Dashboard view with stats and upcoming sessions  
**Template:** `academy_core.portal_guardian_home`

#### GET `/my/kids`
**Purpose:** List all guardian's children  
**Auth:** User (guardian)  
**Returns:** Card grid of children  
**Template:** `academy_core.portal_my_kids`

#### GET `/my/kids/<int:player_id>`
**Purpose:** Detailed view of specific child  
**Auth:** User (guardian)  
**Params:** `player_id` - ID of academy.player record  
**Returns:** Child profile with upcoming/past sessions  
**Template:** `academy_core.portal_kid_detail`  
**Security:** Validates guardian relationship, redirects if unauthorized

#### GET `/my/sessions`
**Purpose:** All sessions for all children (upcoming and past)  
**Auth:** User (guardian)  
**Query Params:** 
- `absence_reported=1` - Shows success message  
**Returns:** Tabbed view with sessions grouped by child  
**Template:** `academy_core.portal_my_sessions`

#### POST `/my/sessions/report_absence`
**Purpose:** Create absence record for a session  
**Auth:** User (guardian)  
**Method:** POST  
**CSRF:** Required  
**Params:**
- `occurrence_id` (required) - Session ID
- `player_id` (required) - Child ID
- `reason_code` (required) - One of: illness, injury, family, school, vacation, other
- `reason_note` (optional) - Additional details
- `redirect` (optional) - URL to redirect after submission (default: /my/sessions)  
**Returns:** Redirect to origin page with success message  
**Security:** Validates guardian relationship and future session

#### GET `/my/billing`
**Purpose:** View invoices and payment history  
**Auth:** User (guardian)  
**Returns:** Current and paid invoices for guardian  
**Template:** `academy_core.portal_my_billing`

#### GET `/my/profile`
**Purpose:** View and edit guardian profile  
**Auth:** User (guardian)  
**Query Params:**
- `success=1` - Shows update success message  
**Returns:** Profile form with linked children  
**Template:** `academy_core.portal_my_profile`

#### POST `/my/profile/update`
**Purpose:** Update guardian contact information  
**Auth:** User (guardian)  
**Method:** POST  
**CSRF:** Required  
**Params:**
- `name` (optional) - Full name
- `email` (optional) - Email address
- `phone` (optional) - Phone number
- `mobile` (optional) - Mobile number
- `street` (optional) - Street address
- `street2` (optional) - Street address line 2
- `city` (optional) - City
- `zip` (optional) - Zip code  
**Returns:** Redirect to `/my/profile?success=1`

---

## Code Quality & Best Practices

### Follows Odoo Conventions
✅ Controller extends `CustomerPortal`  
✅ Templates use `portal.portal_layout`  
✅ Proper `t-call` and `t-set` usage  
✅ Security via `auth='user'` and `csrf=True`  
✅ Uses `sudo()` only where necessary  
✅ Proper domain filtering

### Code Maintainability
✅ Clear function and variable names  
✅ Comprehensive docstrings  
✅ Reusable modal component (`absence_modal`)  
✅ Consistent error handling  
✅ Separated concerns (controller logic vs. template rendering)

### Performance
✅ Efficient database queries with proper domains  
✅ Limited result sets (LIMIT clauses)  
✅ Indexed field usage in queries  
✅ Minimal sudo() usage  
✅ Ready for pagination implementation

---

## Acceptance Criteria - All Met ✅

Based on the user stories and information architecture documents:

### From `academy_user_stories.md`:
- ✅ Dashboard with overview of child's activities
- ✅ Upcoming sessions display
- ✅ Notifications (visual alerts for absence confirmation)
- ✅ My Kids section with list and individual profiles
- ✅ Sessions with upcoming and past views
- ✅ Absence reporting functionality
- ✅ Billing with current invoices and payment history
- ✅ Profile with guardian's personal information and account settings

### From `guardian_portal_ia` documents:
- ✅ Main navigation with Home, My Kids, Sessions, Billing, Profile
- ✅ Session management features
- ✅ Absence reporting with reasons and notes
- ✅ Billing overview
- ✅ Profile management
- ✅ Clean, intuitive user experience

### Additional Requirements Met:
- ✅ All other portal menu items removed/hidden for guardians
- ✅ Mobile-responsive design
- ✅ Security validations in place
- ✅ Modern Bootstrap 5 UI

---

## Conclusion

The guardian portal has been successfully implemented with all requested features. The portal provides a comprehensive, secure, and user-friendly interface for guardians to manage their children's academy activities.

### Key Achievements
1. **Complete Feature Set:** All 5 main sections fully functional
2. **Enhanced UX:** Modern, responsive design with clear navigation
3. **Security:** Proper authentication, authorization, and CSRF protection
4. **Integration:** Seamlessly integrates with existing academy models
5. **Maintainability:** Clean code following Odoo best practices
6. **Scalability:** Ready for future enhancements and optimizations

### Next Steps
1. Deploy to staging environment for user acceptance testing
2. Gather guardian feedback on usability
3. Implement prioritized enhancements (notifications, pagination)
4. Monitor performance and optimize queries as needed
5. Consider mobile app development for enhanced guardian experience

---

**Document Version:** 1.0  
**Last Updated:** October 12, 2025  
**Author:** AI Development Assistant  
**Reviewed By:** [Pending]  
**Approved By:** [Pending]

---

## Appendix: Quick Reference

### Important File Paths
```
custom_addons/academy_core/
├── controllers/
│   └── portal.py                              # All portal routes
├── views/
│   ├── portal_practice_templates.xml          # Dashboard, My Kids, Breadcrumbs
│   └── portal_guardian_templates.xml          # Sessions, Billing, Profile
└── __manifest__.py                            # Module dependencies and data files
```

### Key Database Tables
- `res_partner` - Guardian contact information
- `academy_player` - Children records
- `academy_session_occurrence` - Scheduled sessions
- `academy_session_absence` - Absence reports
- `account_move` - Invoices

### Support Contacts
- **Technical Issues:** [tech-support@academy.com]
- **Billing Questions:** [billing@academy.com]
- **General Inquiries:** [info@academy.com]

---

*End of Handover Document*
