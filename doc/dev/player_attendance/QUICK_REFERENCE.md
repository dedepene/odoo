# Attendance System - Quick Reference Guide

## Quick Start for Coaches

### Confirming Attendance (Daily Task)
1. Navigate to: **Academy > Scheduling > Today's Sessions**
2. Open the current session
3. Click **"Confirm Attendance"** button
4. Review the roster:
   - ✅ All players are checked (present) by default
   - **Uncheck players who are absent**
   - Pre-reported absences shown separately (do nothing with these)
5. Click **"Confirm Attendance"**
6. Done! Attendance recorded.

**Important**: Only players with checkmarks (☑️) will be billed.

### Adding Walk-In Players
1. During attendance confirmation, click **"Add Walk-In Player"**
2. Search for the player by name
3. Select the reason:
   - **Trial** = Free session
   - **Makeup** = Normal price
   - **Advancement** = Normal price (skill level promotion)
   - **Other** = Normal price
4. Click **"Add & Mark Present"**
5. Player added to roster automatically

---

## Quick Reference for Admins

### Reviewing Billing Items
**Location**: Academy > Attendance > Billing Items

**Filters**:
- **Pending** = Needs review
- **Walk-In** = Special pricing review
- **This Month** = Current month only

**Actions**:
- **Approve** = Ready for invoicing
- **Cancel** = Don't bill (with reason)

### Running Billing Manually
```python
# In Odoo shell or scheduled actions
env['academy.attendance.billing'].generate_billing_items(
    date_from='2025-10-01', 
    date_to='2025-10-31'
)
```

### Adjusting Pricing
**Location**: Settings > Technical > Parameters > System Parameters

| Parameter | Default | Description |
|-----------|---------|-------------|
| academy.billing.group_tennis_price | 25.00 | Group tennis session |
| academy.billing.group_physical_price | 20.00 | Group physical session |
| academy.billing.individual_tennis_price | 60.00 | Individual tennis |
| academy.billing.individual_physical_price | 40.00 | Individual physical |

---

## Attendance Confirmation Window

⚠️ **CURRENTLY DISABLED FOR TESTING** - The time window restriction is commented out to allow testing at any time. In production, this should be re-enabled.

| When | Action Allowed? |
|------|----------------|
| 15+ min before session | ❌ Too early (when enabled) |
| 15 min before to 30 min after | ✅ Can confirm |
| 30+ min after session | ❌ Too late (when enabled) |

**To Re-Enable**: Uncomment lines 393-401 in `custom_addons/academy_schedule/models/academy_session_occurrence.py`

---

## Billing Rules (Critical)

| Scenario | Attendance Record? | Billed? |
|----------|-------------------|---------|
| Player present (checked ☑️) | ✅ Yes | ✅ Yes |
| Player absent (unchecked ❌) | ❌ No | ❌ No |
| Pre-reported absence | ❌ No | ❌ No |
| No-show (not marked) | ❌ No | ❌ No |
| Walk-in (trial) | ✅ Yes | $0 (free) |
| Walk-in (makeup/advancement) | ✅ Yes | ✅ Normal price |

**Golden Rule**: No attendance record = No billing

---

## Walk-In Reasons

| Reason | Price | When to Use |
|--------|-------|-------------|
| Trial | $0 (free) | New player trying out |
| Makeup | Normal | Missed previous session |
| Advancement | Normal | Moving up skill level |
| Other | Normal | Other legitimate reason |

---

## Troubleshooting

### "Attendance already confirmed"
**Problem**: Trying to re-confirm a session.
**Solution**: Contact admin to reset. Cannot change once confirmed.

### "Player already in roster"
**Problem**: Trying to add walk-in who's already registered.
**Solution**: Player is in the skill group, no need to add.

### "Cannot delete attendance"
**Problem**: Attendance record already billed.
**Solution**: Cancel billing item first, then delete attendance.

### Missing billing items
**Problem**: Sessions confirmed but no billing items.
**Solution**: 
1. Check session attendance_status = 'confirmed'
2. Manually run billing: `generate_billing_items()`
3. Check for errors in cron log

---

## Monthly Billing Checklist

### Before Month End
- [ ] All sessions confirmed
- [ ] Walk-ins reviewed and priced
- [ ] Absence requests verified

### On 1st of Month (Automatic)
- [ ] Billing cron runs at 2 AM
- [ ] Billing items created for previous month
- [ ] Check email for error notifications

### After Billing Run
- [ ] Review pending billing items
- [ ] Approve walk-in pricing
- [ ] Cancel any errors
- [ ] Generate invoices (separate process)

---

## Keyboard Shortcuts (Wizards)

| Key | Action |
|-----|--------|
| Q | Confirm / OK |
| Z | Cancel |

---

## Support Contacts

- **Developer**: dedepene
- **Documentation**: `/doc/dev/player_attendance/IMPLEMENTATION_HANDOVER.md`
- **Version**: 19.0.1.0.0

---

## File Locations

| Component | Path |
|-----------|------|
| Models | `custom_addons/academy_schedule/models/academy_attendance.py` |
| Wizards | `custom_addons/academy_schedule/wizard/attendance_wizards.py` |
| Views | `custom_addons/academy_schedule/views/attendance_views.xml` |
| Security | `custom_addons/academy_schedule/security/ir.model.access.csv` |
| Cron | `custom_addons/academy_schedule/data/attendance_billing_cron.xml` |

---

**Last Updated**: October 14, 2025
