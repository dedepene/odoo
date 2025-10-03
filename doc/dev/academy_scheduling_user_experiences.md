# Academy Scheduling – User Experiences & Manual Verification

## New/Updated Experiences
1. **Season Configuration (Site Admin / Head Coach)**  
   Create and activate a season defining the temporal bounds for all recurring group sessions.
2. **Weekly Group Schedule Template Wizard (Head Coach)**  
   Matrix-based creation/edit of recurring group session templates with court allocation and optional chained physical sessions.
3. **Occurrence Generation & Regeneration (System / Head Coach)**  
   Automatic expansion of templates to dated occurrences; selective future-only regeneration after edits.
4. **Court Conflict Detection (System)**  
   Real-time validation blocking overlapping allocations per court/time.
5. **Individual Session Booking (Coach)**  
   Ad-hoc one-to-one or small group session creation with conflict & double-booking checks.
6. **Absence Reporting (Guardian / Player)**  
   Simple structured absence flagging against future occurrences, visible aggregate to coaches.
7. **Season Suspension (Site Admin)**  
   Temporary bulk state change (suspended) for occurrences within a date window (e.g., dome installation).
8. **Calendar Visibility Scoping (Portal / Coaches)**  
   Role-based filtered calendar views enforcing privacy (player/guardian sees only own scope; coaches see assigned).
9. **Follow-up Physical Session Auto-Linking (System)**  
   Optional chained physical activity session generated immediately after a tennis session.
10. **Audit & Change Logging (System)**  
    Chatter summaries for generation, edits, suspensions, and regeneration deltas.

---

## A. Pre-requisites
- Core module `academy_core` installed (players, guardians, skill groups functional).
- Scheduling models installed: `academy.session.template`, `academy.session.occurrence`, `academy.court`, `academy.season`.
- At least one active skill group (e.g., Green Ball) and sample players assigned.
- Courts configured: Court 1, Court 3, Court 5.
- User roles created: Head Coach, Coach, Site Admin, Guardian, Player (portal).
- Outgoing email optional (for notification checks).

---

## B. Season Setup
1. Navigate to **Academy ▸ Configuration ▸ Seasons**.
2. Click Create: Name = "Fall 2025", Start = 2025-09-01, End = 2025-12-20, Active = True.
3. Save – record should enforce end > start.
4. Attempt second active season overlapping dates – expect validation error.
5. Deactivate season – templates/occurrence generation actions hidden.

Success Indicators:
- Overlap blocked.
- Active season displays action button: "Define Weekly Schedule".

---

## C. Weekly Schedule Template Wizard
1. From season form click **Define Weekly Schedule**.
2. Matrix loads (Mon–Sun columns). Initially empty.
3. Add Green Group: Days Mon/Wed/Fri, Time 17:00–19:00, Courts 1,3,5, Session Type = Tennis Skills, Follow-up Physical = Yes (19:00–20:00 auto-filled).
4. Add Red Group: Days Tue/Thu, Time 17:00–19:00, Courts 2,4 (example), Follow-up Physical = No.
5. Submit.

Validation Checks:
- If a selected court reused at overlapping time for same day, wizard blocks and highlights row.
- End time before start time raises inline error.

Outcome:
- Templates created (count matches (#groups * #distinct weekday sets + follow-ups)).
- Chatter on season summarizing: per group counts, follow-up sessions created.

---

## D. Occurrence Generation
1. On wizard completion system auto-generates occurrences for each matching weekday between start/end.
2. Open **Academy ▸ Scheduling ▸ Occurrences** list – filter by season, verify count = weeks_in_range * sessions_per_week (plus follow-ups).
3. Inspect one occurrence: Courts replicated; start/end datetimes correct (timezone aware display).

Edge Validation:
- Extend season end date forward 2 weeks – run **Generate Missing Occurrences** action; only new dates appended.

---

## E. Editing Templates & Regeneration
1. Modify Green Group template: shift start to 16:30.
2. Choose Regeneration Mode dialog: (a) Future occurrences only – select.
3. Verify past occurrences retain original times; future ones reflect update.
4. Chatter delta log lists modified template id and affected occurrence count.

Error Test:
- Attempt to change to time overlapping with another template sharing a court – expect block.

---

## F. Individual Session Booking
1. As Coach (non-head) open **New Individual Session**.
2. Select Player A, Date = upcoming Wednesday 15:00–16:00, Court 1.
3. Save – occurrence created with is_individual flag; visible to Player A’s guardian.
4. Create second session same time, same player, different court – if double-book prevention enabled, expect block (or warning if configured soft mode).
5. Try scheduling in the past – blocked.

---

## G. Absence Reporting
1. Portal login as Guardian of Player A.
2. Open calendar list of upcoming group occurrence; click **Report Absence**.
3. Choose Reason = "Illness", note = "Fever"; submit.
4. Coach view of occurrence shows Absence Badge (1) and lists Player A in absence panel.
5. Attempt second absence for same player/session – blocked.
6. Withdraw absence before session start – state updates, badge decrements.

---

## H. Season Suspension
1. Site Admin selects season action **Suspend Sessions**.
2. Enter Range: 2025-10-10 → 2025-10-20, Apply To = Group Only.
3. System marks group occurrences within window as Suspended (state column badge) – individual sessions untouched.
4. Remove suspension (delete suspension window) – future-dated suspended occurrences revert to Planned; past ones remain historical.

Edge Check:
- Overlapping second suspension window merges logically; no duplicate transitions.

---

## I. Calendar Visibility & Privacy
1. Login as unrelated Guardian (no children in Green group) – attempt direct URL to a Green occurrence id – access error.
2. Login as Player A – sees own group & individual session; other groups absent.
3. Login as Head Coach – sees all occurrences color-coded by group.
4. Lead Coach Availability: Player view masks other player names (e.g., "Group Session (Green)" generic label).

---

## J. Follow-up Physical Sessions
1. Confirm follow-up session immediately follows tennis session end time.
2. Cancellation of base session optionally cascades (prompt) to follow-up; test both cascade and retain scenarios.
3. Billing (future) should differentiate type – placeholder note.

---

## K. Success Criteria
| ID | Criterion |
|----|----------|
| SX1 | Generating schedule yields correct occurrence count (mathematically validated) |
| SX2 | Court conflicts prevented both at template wizard and individual booking |
| SX3 | Regeneration respects future-only mode |
| SX4 | Absence duplicates blocked and visible to coaches |
| SX5 | Suspension toggles states within window without deleting records |
| SX6 | Visibility rules prevent cross-group leakage |
| SX7 | Follow-up sessions auto-created with correct temporal chaining |
| SX8 | Audit chatter present for generation, edit, suspension, regeneration |

---

## L. Non-Functional Notes
- Performance: Batch create occurrences per template using list-of-dicts to minimize ORM chatter.
- Timezone Strategy: Store UTC datetimes; preserve local wall time by storing original start_time/end_time on template.
- Auditing: Standardized chatter tag prefix [SCHED] for easy filtering.
- Extensibility: Session Type selection field extendable via `selection_add` in custom modules.
- Security: Record rules anchor to player.skill_group_id; coach portfolio expansion via m2m relation future.
- Clean-up: Archive (never unlink) past occurrences to keep attendance/billing trace.

---

## M. Open Questions
| Topic | Question |
|-------|----------|
| Holiday Exclusions | Integrate regional calendar or manual per-date skip list? |
| Player Capacity | Enforce max players per court per session? |
| Auto Coach Assignment | Should group sessions auto-populate lead coach based on group ownership? |
| Double-Booking Policy | Hard block vs warning config parameter? |
| Absence Notifications | Escalate via email to coach or digest-based? |

---

## N. Future Enhancements Backlog
- Holiday calendar integration + automatic skip/regenerate.
- Capacity & waitlist management per occurrence.
- Weather-based adaptive rescheduling for outdoor courts.
- Smart suggestion engine for make-up sessions when absences exceed threshold.
- Inline occupancy heatmap view for planning.
- KPI dashboard: Utilization %, Absence Rate, Court Load distribution.

---

## O. Traceability Mapping
| Requirement Area | Experience Section |
|------------------|-------------------|
| Weekly Scheduling | C, D |
| Court Allocation | C, F |
| Absence Reporting | G |
| Suspension | H |
| Visibility | I |
| Individual Sessions | F |
| Follow-up Physical | J |
| Auditing | K, L |

---

## P. Manual Test Data Reset (Optional)
1. Delete (or archive) occurrences for season via action: "Archive Season Occurrences".
2. Adjust templates; regenerate to reproduce edge cases.
3. Use a dedicated test season to avoid production contamination.

---

Document intended to align with style and depth of `academy_core_user_experiences.md` while focusing purely on scheduling lifecycle.
