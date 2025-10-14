# Player Attendance System - Documentation Index

## Overview
This directory contains documentation for the Tennis Academy Player Attendance Management System, implemented in the `academy_schedule` module.

## Documentation Files

### 1. [IMPLEMENTATION_HANDOVER.md](./IMPLEMENTATION_HANDOVER.md)
**Audience**: Developers, Technical Staff

Comprehensive technical documentation covering:
- Complete architecture and data model specifications
- Business logic and workflow diagrams
- Security and access control details
- Deployment instructions
- SQL schema and relationships
- Testing procedures
- Troubleshooting guide
- Future enhancement recommendations

**Length**: ~40 pages | **Detail Level**: Expert

---

### 2. [QUICK_REFERENCE.md](./QUICK_REFERENCE.md)
**Audience**: Coaches, Admins, End Users

Quick reference guide covering:
- Daily attendance confirmation steps
- Walk-in player procedures
- Billing review process
- Common troubleshooting
- Monthly checklist
- Keyboard shortcuts

**Length**: 4 pages | **Detail Level**: Beginner-Friendly

---

## System Summary

### What Was Built
The attendance system implements coach-validated attendance tracking with automated billing generation. Key features:

✅ **Coach Attendance Confirmation**
- Prepopulated roster (all players checked by default)
- Coach unchecks absentees
- Attendance records created ONLY for present players

✅ **Walk-In Player Management**
- Search and add unregistered players to sessions
- Reason tracking (trial=free, makeup/advancement=normal price)
- Automatic attendance recording

✅ **Attendance-Driven Billing**
- NO attendance record = NO billing
- Monthly automated cron job
- Configurable pricing per session type
- Walk-in special pricing (trials free)

✅ **Security & Access Control**
- Role-based permissions (admin, head coach, coach, portal)
- Audit trails via chatter
- Prevent duplicate billing

### What Was NOT Built
❌ Guardian portal attendance views (documented for future implementation)
❌ Admin analytics and pivot reports (documented for future implementation)
❌ Automated invoice generation (billing items created but invoices manual)

---

## Quick Stats

| Metric | Count |
|--------|-------|
| New Models | 4 (attendance, billing_item, participant, billing_processor) |
| New Wizards | 2 (confirmation, walk-in) |
| New Views | 12 (list, form, search for each model + wizards) |
| New Fields (Session) | 4 (attendance_ids, attendance_count, attendance_status, participant_ids) |
| New Methods (Session) | 4 (get_registered_players, confirm_attendance, process_confirmation, add_walkin) |
| Security Access Rules | 20 (admin, head coach, coach, portal) |
| Cron Jobs | 1 (monthly billing generation) |
| Config Parameters | 4 (pricing for session types) |
| Lines of Code | ~1200 |

---

## Key Business Rules

### Attendance Confirmation
- **Window**: 15 min before to 30 min after session start
- **Default**: All players checked (☑️ = present)
- **Action**: Coach unchecks absentees (❌ = absent)
- **Result**: Attendance records created ONLY for checked players

### Billing Generation
- **Trigger**: Monthly cron (1st of month at 2 AM)
- **Scope**: Previous month's confirmed sessions
- **Rule**: One billing item per attendance record
- **Pricing**:
  - Group tennis: $25
  - Group physical: $20
  - Individual tennis: $60
  - Individual physical: $40
  - Walk-in trial: $0 (free)
  - Walk-in other: Normal pricing

### No Attendance = No Billing
| Scenario | Attendance? | Billed? |
|----------|------------|---------|
| Present (checked) | ✅ | ✅ |
| Absent (unchecked) | ❌ | ❌ |
| Pre-reported absence | ❌ | ❌ |
| No-show | ❌ | ❌ |

---

## File Structure

```
custom_addons/academy_schedule/
├── models/
│   ├── academy_attendance.py        # 4 models, ~600 lines
│   └── academy_session_occurrence.py # Extended with attendance fields
├── wizard/
│   └── attendance_wizards.py        # 2 wizards, ~380 lines
├── views/
│   ├── attendance_views.xml         # Backend UI
│   └── attendance_wizard_views.xml  # Wizard UI
├── data/
│   └── attendance_billing_cron.xml  # Cron + config
├── security/
│   └── ir.model.access.csv          # 20 new access rules
└── __manifest__.py                   # Updated with new data files
```

---

## Deployment Checklist

### Before Deployment
- [ ] Review pricing configuration (system parameters)
- [ ] Test on staging environment
- [ ] Train coaches on attendance confirmation workflow
- [ ] Train admins on billing review process

### Deployment
```bash
# Update module
python odoo-bin -c odoo.conf -u academy_schedule -d production_db --stop-after-init

# Restart Odoo
sudo systemctl restart odoo
```

### After Deployment
- [ ] Verify cron job active (Settings > Technical > Scheduled Actions)
- [ ] Test attendance confirmation (coach user)
- [ ] Test walk-in addition (coach user)
- [ ] Manually run billing once to verify: `env['academy.attendance.billing'].generate_billing_items()`
- [ ] Check billing items created correctly

---

## Testing Recommendations

### Unit Tests (Future)
Recommended test coverage:
- `test_attendance_confirmation_creates_records_only_for_present`
- `test_walk_in_player_addition_creates_participant_and_attendance`
- `test_billing_generation_only_for_confirmed_attendance`
- `test_absence_request_prevents_billing`
- `test_duplicate_attendance_prevention`
- `test_duplicate_billing_prevention`

### Manual Testing (Current)
See IMPLEMENTATION_HANDOVER.md > Testing and Validation section

---

## Support

### For Developers
- Read: [IMPLEMENTATION_HANDOVER.md](./IMPLEMENTATION_HANDOVER.md)
- Review: Source code comments in models/attendance.py
- Check: SQL schema diagrams in handover doc

### For End Users
- Read: [QUICK_REFERENCE.md](./QUICK_REFERENCE.md)
- Video training: (TODO: Create coach training video)
- Admin guide: (TODO: Create admin billing review guide)

### For Issues
1. Check troubleshooting section in QUICK_REFERENCE.md
2. Check detailed troubleshooting in IMPLEMENTATION_HANDOVER.md
3. Review cron logs: Settings > Technical > Scheduled Actions > Logs
4. Contact: dedepene

---

## Version History

| Version | Date | Status | Notes |
|---------|------|--------|-------|
| 1.0 | 2025-10-14 | Complete | Core functionality implemented |
| 1.1 | TBD | Planned | Guardian portal views |
| 1.2 | TBD | Planned | Admin analytics |
| 2.0 | TBD | Planned | Automated invoice generation |

---

## Related Documentation

- [Academy Requirements](../academy_requirements.md) - Original requirements
- [Academy User Stories](../academy_user_stories.md) - Detailed user stories (Section 3.2, 3.3, 3.4)
- [Academy Core User Experiences](../academy_core_user_experiences.md) - UX testing guide (Section 5)

---

**Module**: academy_schedule  
**Version**: 19.0.1.0.0  
**Author**: dedepene  
**Date**: October 14, 2025  
**License**: LGPL-3
