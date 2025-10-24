# Multi-Skill Group Sessions - Solution Design

**Issue ID**: SCHED-MULTI-001  
**Status**: Proposed Solution  
**Created**: October 24, 2025  
**Priority**: High  
**Module**: `academy_schedule`, `academy_billing`

---

## 1. Problem Statement

### Current Limitation
The current implementation enforces a **one-to-one relationship** between sessions and skill groups:
- `academy.session.template.skill_group_id` (Many2one)
- `academy.session.occurrence.skill_group_id` (Many2one)
- Player eligibility check: `player.skill_group_id == session.skill_group_id`

### Real-World Requirement
**Physical Activities sessions** must accommodate players from **multiple skill groups** simultaneously (e.g., Green Ball, Orange Ball, and Hard Ball players training together).

This is different from Tennis Skills sessions, which are skill-level specific and require homogeneous groups.

### Impact
Without this capability:
- ❌ Cannot schedule cross-skill-level physical training
- ❌ Coaches must run duplicate sessions for each skill group
- ❌ Inefficient court and coach utilization
- ❌ Walk-in workarounds required (bypassing system integrity)

---

## 2. User Understanding Validation

### ✅ Assertion 1: Billing Calculation (CORRECT)

**User's Understanding**:
> Monthly invoices are calculated by summing up the practice session occurrences where to each session is applied the session type rate, acknowledged absences from the previous month are deducted from the invoice 'amount due'.

**Actual Implementation**:
- ✅ Session type rates are defined in `custom_addons/academy_billing/data/attendance_billing_cron.xml`
- ✅ Acknowledged absences generate credit notes via reconciliation (applied to subsequent invoices)
- ✅ **PRE-PAID MODEL**: Invoices are generated on the 1st of each month based on **scheduled session occurrences**
  - Cron job `cron_generate_monthly_prepaid_invoices()` runs daily (checks if it's the invoice_generation_day)
  - For each player, system counts scheduled occurrences: `_get_registered_players()` × session count
  - Each occurrence gets priced via `_get_session_pricing()` based on session_type
  - Invoice line: "November 2025 Player Name - Tennis Skills (Group) x 8" @ $25/session = $200
  - Any open credit notes (from previous acknowledged absences) are auto-applied to reduce amount due

**Why This Matters**:
The academy bills **in advance for scheduled sessions**, providing stable cash flow. Absences are credited retroactively after coach acknowledgment, reducing the following month's invoice.

---

### ✅ Assertion 2: Player Assignment (CORRECT)

**User's Understanding**:
> All players belonging to a skill group (e.g., green balls) associated with a session template get assigned to the session instance when it's actually scheduled inside a season. These assignments then are tallied and used by the billing module to create line items for the player's invoice.

**Validation**:
- ✅ `academy.session.template` has `skill_group_id`
- ✅ `generate_occurrences()` copies `skill_group_id` to each occurrence
- ✅ `_get_registered_players()` searches for all players where `player.skill_group_id == occurrence.skill_group_id`
- ✅ Attendance confirmation wizard prepopulates registered players
- ✅ Attendance records create billing items via `generate_billing_items()`

**Billing Flow**:
```
Template (skill_group=Green) 
  ↓ generate_occurrences()
Occurrence (skill_group=Green) 
  ↓ 1st of month: cron_generate_monthly_prepaid_invoices()
  ↓ _get_registered_players()
Players (skill_group=Green) × occurrence_count
  ↓ _get_session_pricing() per occurrence
Invoice Lines (pre-paid for scheduled sessions)
  ↓ apply open credit notes
Final Invoice (with credits applied)
```

---

## 3. Proposed Solution

### Architecture: Many2many Skill Groups for Sessions

#### Core Principle
Maintain **backward compatibility** while enabling **multi-skill-group sessions** through an **opt-in mechanism**.

---

### 3.1 Data Model Changes

#### A. Session Template Model (`academy.session.template`)

```python
# EXISTING (keep for backward compatibility)
skill_group_id = fields.Many2one('academy.skill.group', string='Primary Skill Group')

# NEW FIELDS
skill_group_ids = fields.Many2many(
    'academy.skill.group',
    'academy_session_template_skill_group_rel',
    'template_id',
    'skill_group_id',
    string='Skill Groups',
    help='Select multiple skill groups for cross-level sessions (e.g., Physical Activities)'
)
multi_skill_mode = fields.Boolean(
    string='Multi-Skill Group Session',
    default=False,
    help='Enable to allow multiple skill groups. Disables primary skill group field.'
)
primary_skill_group_id = fields.Many2one(
    'academy.skill.group',
    compute='_compute_primary_skill_group',
    store=True,
    string='Primary Skill Group (Computed)',
    help='Automatically set: single skill_group_id or first in skill_group_ids'
)
```

#### B. Session Occurrence Model (`academy.session.occurrence`)

```python
# EXISTING (keep for reporting/filtering)
skill_group_id = fields.Many2one('academy.skill.group', string='Primary Skill Group')

# NEW FIELDS
skill_group_ids = fields.Many2many(
    'academy.skill.group',
    'academy_session_occurrence_skill_group_rel',
    'occurrence_id',
    'skill_group_id',
    string='Skill Groups',
    help='Skill groups eligible for this session'
)
multi_skill_mode = fields.Boolean(
    string='Multi-Skill Mode',
    default=False
)
```

---

### 3.2 Business Logic Updates

#### A. Occurrence Generation (`academy.session.template`)

```python
def _prepare_occurrence_vals(self, date):
    """Prepare values for creating an occurrence."""
    vals = {
        # ... existing fields ...
        'multi_skill_mode': self.multi_skill_mode,
    }
    
    # Populate skill groups based on mode
    if self.multi_skill_mode:
        vals['skill_group_ids'] = [(6, 0, self.skill_group_ids.ids)]
        vals['skill_group_id'] = self.skill_group_ids[0].id if self.skill_group_ids else False
    else:
        vals['skill_group_id'] = self.skill_group_id.id
        vals['skill_group_ids'] = [(6, 0, [self.skill_group_id.id])] if self.skill_group_id else False
    
    return vals
```

#### B. Registered Players (`academy.session.occurrence`)

```python
def _get_registered_players(self):
    """
    Get all players registered for this session.
    For group sessions: all players in ANY of the linked skill groups.
    For individual sessions: explicitly assigned players.
    """
    self.ensure_one()
    
    if self.session_type in ['tennis_group', 'physical_group']:
        # Multi-skill support: search across all linked skill groups
        skill_group_ids = self.skill_group_ids.ids if self.multi_skill_mode else [self.skill_group_id.id]
        
        if not skill_group_ids:
            return self.env['academy.player']
        
        players = self.env['academy.player'].search([
            ('skill_group_id', 'in', skill_group_ids),
            ('active', '=', True)
        ])
        
        _logger.info(
            f"Session {self.id} ({self.session_type}): Found {len(players)} players "
            f"from {len(skill_group_ids)} skill groups"
        )
        return players
    else:
        # Individual session: explicit participants
        return self.player_ids
```

#### C. Attendance Validation (`academy.attendance`)

```python
@api.constrains('session_id', 'player_id')
def _check_player_eligible(self):
    """
    Validate player is eligible for the session.
    For group sessions: player should be in ANY of the session's skill groups OR be a walk-in.
    For individual sessions: player should be in participant list OR be a walk-in.
    """
    for record in self:
        if record.is_walkin:
            continue
        
        session = record.session_id
        player = record.player_id

        if session.session_type in ['tennis_group', 'physical_group']:
            # Check if player's skill group is in session's allowed skill groups
            session_skill_groups = session.skill_group_ids if session.multi_skill_mode else session.skill_group_id
            
            if session.multi_skill_mode:
                if player.skill_group_id not in session_skill_groups:
                    raise ValidationError(
                        f"Player {player.name} (skill group: {player.skill_group_id.name}) "
                        f"is not eligible for this session. "
                        f"Allowed groups: {', '.join(session_skill_groups.mapped('name'))}"
                    )
            else:
                if player.skill_group_id != session.skill_group_id:
                    raise ValidationError(
                        f"Player {player.name} is not in the skill group "
                        f"'{session.skill_group_id.name}' for this session. "
                        f"Use 'Add Walk-In Player' instead."
                    )
        # ... individual session validation unchanged ...
```

---

### 3.3 User Interface Updates

#### A. Weekly Schedule Wizard

**Current**: Single skill group dropdown  
**New**: 
- Checkbox: "Multi-Skill Group Session"
- When checked: Replace dropdown with Many2many widget
- Only show for physical activities session types

```xml
<field name="multi_skill_mode"/>
<field name="skill_group_id" attrs="{'invisible': [('multi_skill_mode', '=', True)]}"/>
<field name="skill_group_ids" widget="many2many_tags" 
       attrs="{'invisible': [('multi_skill_mode', '=', False)],
               'required': [('multi_skill_mode', '=', True)]}"/>
```

#### B. Session Occurrence Form View

```xml
<field name="multi_skill_mode" invisible="1"/>
<field name="skill_group_id" attrs="{'invisible': [('multi_skill_mode', '=', True)]}"/>
<field name="skill_group_ids" widget="many2many_tags"
       attrs="{'invisible': [('multi_skill_mode', '=', False)]}"/>
```

#### C. Attendance Confirmation Wizard

**Enhancement**: Group players by skill group in roster view for easier verification

```xml
<field name="registered_player_ids">
    <tree>
        <field name="skill_group_id"/>
        <field name="name"/>
        <field name="primary_guardian_id"/>
    </tree>
</field>
```

---

### 3.4 Billing Impact Analysis

#### ✅ No Changes Required

The billing system remains **fully functional** because:
1. Billing is based on **scheduled session occurrences**, not skill groups
2. `_get_registered_players()` returns players eligible for each occurrence
3. `_get_session_pricing()` uses `occurrence.session_type`, not skill groups
4. The cron iterates through occurrences and counts sessions per player

**Validation**:
```python
# academy_billing/models/billing_template.py (UNCHANGED)
def _generate_prepaid_invoices_for_month(self, target_date):
    occurrences = occurrence_model.search([...])  # Find scheduled occurrences
    
    for occurrence in occurrences:
        players = occurrence._get_registered_players()  # ✅ Will return multi-skill players
        for player in players:
            # Count sessions and calculate price per occurrence
            line_data['count'] += 1
            line_data['amount'] += self._get_session_pricing(occurrence)  # ✅ Uses session_type
```

**Key Insight**: Since billing aggregates by `(player_id, session_type)`, multi-skill sessions work automatically:
- Green Ball player in Physical session → counted
- Orange Ball player in same Physical session → counted  
- Both billed at "Physical Activities (Group)" rate ($20)

**Invoice Line Item Display**:
- **Before (single-skill)**: "November 2025 Emma Smith - Tennis Skills (Group) x 8" @ $25 = $200
- **After (multi-skill)**: "November 2025 Emma Smith - Physical Activities (Group) x 8" @ $20 = $160
- **After (multi-skill)**: "November 2025 Oliver Jones - Physical Activities (Group) x 8" @ $20 = $160
  - (Even though Emma is Green Ball and Oliver is Orange Ball, both attend same sessions)

---

## 4. Migration Strategy

### Phase 1: Backward Compatible Changes (Week 1)
1. Add new fields to models (with defaults preserving existing behavior)
2. Update `_get_registered_players()` to support both modes
3. Update attendance validation to check skill_group_ids
4. Deploy to development environment

### Phase 2: UI Updates (Week 2)
1. Update weekly schedule wizard
2. Update session occurrence views
3. Test existing single-skill sessions (no regression)
4. Test new multi-skill sessions

### Phase 3: Data Migration (Week 3)
1. Write migration script to populate `skill_group_ids` from `skill_group_id` for all existing records
2. Run migration on staging database
3. Validate all existing sessions still work

### Phase 4: Production Rollout (Week 4)
1. Deploy to production during maintenance window
2. Run migration script
3. Train coaches on new multi-skill session creation
4. Monitor first multi-skill session cycle

---

## 5. Testing Requirements

### Unit Tests

```python
class TestMultiSkillGroupSessions(TransactionCase):
    
    def test_multi_skill_occurrence_generation(self):
        """Verify occurrences inherit multiple skill groups from template."""
        # Create template with multiple skill groups
        # Generate occurrences
        # Assert occurrence.skill_group_ids contains all groups
    
    def test_multi_skill_registered_players(self):
        """Verify _get_registered_players returns players from all skill groups."""
        # Create occurrence with green + orange skill groups
        # Create 2 players in green, 3 in orange
        # Assert _get_registered_players returns 5 players
    
    def test_attendance_validation_multi_skill(self):
        """Verify attendance validation allows players from any linked skill group."""
        # Create multi-skill session
        # Create attendance for player from each group: should pass
        # Create attendance for player NOT in any group: should fail
    
    def test_billing_multi_skill_session(self):
        """Verify billing works correctly for multi-skill sessions."""
        # Confirm attendance for players from different skill groups
        # Run billing generation
        # Assert correct billing items created with physical_group price
```

### Manual Testing Scenarios

| Scenario | Steps | Expected Result |
|----------|-------|-----------------|
| **Create Multi-Skill Template** | 1. Open Weekly Schedule Wizard<br>2. Check "Multi-Skill Mode"<br>3. Select Green + Orange groups<br>4. Set session type = Physical Activities<br>5. Save | Template created with 2 skill groups |
| **Generate Occurrences** | 1. Click "Generate Occurrences"<br>2. Open any occurrence | Occurrence shows both skill groups |
| **Confirm Attendance** | 1. Open occurrence<br>2. Click "Confirm Attendance"<br>3. Verify roster | Roster contains players from BOTH groups |
| **Mark Present (Mixed Groups)** | 1. Mark 2 Green players present<br>2. Mark 3 Orange players present<br>3. Save | 5 attendance records created |
| **Generate Billing** | 1. Run cron job<br>2. Check billing items | 5 billing items @ $20 each (physical rate) |
| **Backward Compatibility** | 1. Create single-skill template (existing pattern)<br>2. Generate occurrence<br>3. Confirm attendance<br>4. Bill | Everything works as before |

---

## 6. Edge Cases & Considerations

### A. Court Capacity
**Issue**: Multi-skill sessions may have more players than single-skill sessions  
**Solution**: Add optional `max_players` field to template/occurrence with validation

### B. Absence Reporting
**Current**: Absences link to occurrence + player  
**Impact**: ✅ No changes needed (absence is player-specific, not skill-group-specific)

### C. Portal View
**Current**: Players see sessions for their skill group  
**Update**: Portal calendar filter logic must check `skill_group_id in occurrence.skill_group_ids`

```python
# academy_schedule/controllers/portal.py
def portal_my_sessions(self, **kwargs):
    player = request.env.user.academy_player_id
    
    domain = [
        '|',
        ('skill_group_id', '=', player.skill_group_id.id),  # Legacy single-skill
        ('skill_group_ids', 'in', [player.skill_group_id.id]),  # Multi-skill
    ]
    
    sessions = request.env['academy.session.occurrence'].sudo().search(domain)
    # ...
```

### D. Coach Assignment
**Issue**: Multi-skill sessions may require multiple coaches  
**Future Enhancement**: Add `coach_ids` (Many2many) to occurrence (out of scope for v1)

---

## 7. Documentation Updates Required

### User-Facing
- Update coach training materials (how to create multi-skill sessions)
- Add FAQ: "When to use multi-skill mode?"
- Portal help text: Explain mixed-group sessions

### Technical
- Update `academy_schedule_handover.md` with new field descriptions
- Update ER diagram showing Many2many relationships
- Add this solution document to dev documentation

---

## 8. Acceptance Criteria

### Definition of Done
- [ ] Multi-skill templates can be created via wizard
- [ ] Occurrences correctly inherit multiple skill groups
- [ ] `_get_registered_players()` returns players from all linked groups
- [ ] Attendance validation allows any player from linked groups
- [ ] Billing generates correct items regardless of skill group mix
- [ ] Existing single-skill sessions continue to work (no regression)
- [ ] Unit tests pass with 90%+ coverage
- [ ] Manual test scenarios pass
- [ ] Portal view shows multi-skill sessions correctly
- [ ] Documentation updated
- [ ] Migration script tested on staging

---

## 9. Alternatives Considered

### ❌ Alternative 1: Make Player.skill_group_id Many2many
**Pros**: More flexible player skill tracking  
**Cons**: 
- Breaks fundamental academy model (player has ONE primary skill level)
- Requires massive data migration
- Complicates billing (which skill level to charge?)
- Breaks age-based skill group constraints

### ❌ Alternative 2: Create "Combined" Skill Groups
**Example**: "Green+Orange Physical"  
**Pros**: No model changes  
**Cons**:
- Combinatorial explosion (Green+Orange, Green+Hard, Orange+Hard, All)
- Data duplication
- Maintenance nightmare
- Doesn't scale to ad-hoc combinations

### ✅ Chosen: Session-Level Many2many (This Proposal)
**Pros**:
- Minimal model changes
- Backward compatible
- Opt-in (doesn't affect existing patterns)
- Scales to any combination
- Clear semantics (session allows multiple groups, player still has one)
**Cons**:
- Requires careful validation logic updates
- Need migration script

---

## 10. Implementation Checklist

### Phase 1: Models
- [ ] Add `skill_group_ids`, `multi_skill_mode` to `academy.session.template`
- [ ] Add `skill_group_ids`, `multi_skill_mode` to `academy.session.occurrence`
- [ ] Add computed `primary_skill_group_id` for backward compatibility
- [ ] Update `_prepare_occurrence_vals()` in template model
- [ ] Update `_get_registered_players()` in occurrence model
- [ ] Update `_check_player_eligible()` in attendance model

### Phase 2: Views
- [ ] Update weekly schedule wizard XML
- [ ] Update session template form view
- [ ] Update session occurrence form view
- [ ] Update attendance wizard tree grouping

### Phase 3: Logic
- [ ] Update portal calendar filter logic
- [ ] Update security rules (if skill-group-based record rules exist)
- [ ] Update reporting queries (if skill-group-based)

### Phase 4: Testing
- [ ] Write unit tests (4 tests minimum)
- [ ] Run manual test scenarios
- [ ] Test migration script on copy of production data

### Phase 5: Documentation
- [ ] Update coach user guide
- [ ] Update technical handover doc
- [ ] Create this solution doc (✅ DONE)
- [ ] Update ER diagram

### Phase 6: Deployment
- [ ] Code review
- [ ] Staging deployment
- [ ] User acceptance testing
- [ ] Production deployment
- [ ] Post-deployment monitoring

---

## 11. Questions for Product Owner

1. **Default Behavior**: Should new physical sessions default to multi-skill mode?
2. **Conversion**: Should we provide a wizard to convert existing single-skill physical sessions to multi-skill?
3. **Capacity**: Should we enforce max players on multi-skill sessions?
4. **Pricing**: Should multi-skill sessions have different pricing? (Current proposal: use session_type price)
5. **Naming**: How should multi-skill sessions be named in portal/calendar? (Current: "Physical Activities - Multi-Level")

---

## 12. Success Metrics

### Pre-Implementation (Baseline)
- Physical session duplicates per week: X
- Walk-in overrides per month: Y
- Coach complaints about scheduling: Z

### Post-Implementation (Target)
- Physical session duplicates: 0
- Walk-in overrides for skill-group issues: 0
- Coach satisfaction survey: 4.5/5
- Billing accuracy: 100% (no regression)

---

## 13. Rollback Plan

If critical issues arise post-deployment:

1. **Immediate**: Disable multi-skill mode wizard UI (hide checkbox)
2. **Database**: Set all `occurrence.multi_skill_mode = False`
3. **Revert**: Restore to single-skill behavior without code rollback
4. **Fix**: Address issues in hotfix branch
5. **Redeploy**: After thorough testing

**Note**: Rollback preserves data integrity because single-skill behavior is the fallback.

---

## Appendix A: SQL Migration Script

```sql
-- Populate skill_group_ids from skill_group_id for backward compatibility
-- Run AFTER adding new fields, BEFORE deploying new business logic

-- Session Templates
UPDATE academy_session_template
SET skill_group_ids = ARRAY[skill_group_id]
WHERE skill_group_id IS NOT NULL
  AND skill_group_ids IS NULL;

-- Session Occurrences  
UPDATE academy_session_occurrence
SET skill_group_ids = ARRAY[skill_group_id]
WHERE skill_group_id IS NOT NULL
  AND skill_group_ids IS NULL;

-- Validation: Count records with mismatched data
SELECT COUNT(*) 
FROM academy_session_occurrence
WHERE skill_group_id IS NOT NULL
  AND (
    skill_group_ids IS NULL 
    OR skill_group_id != ANY(skill_group_ids)
  );
-- Expected: 0
```

---

**Document Status**: ✅ Ready for Review  
**Next Steps**: Schedule design review meeting with Tech Lead, Product Owner, and Head Coach
