# Academy Traceability Matrix

This document maps high-level user experiences to the detailed user stories in `academy_user_stories.md` and `academy_scheduling_user_experiences.md`. Use this for planning, ticketing, and QA traceability.

## Legend
- Experience: High-level workflow from the User Experiences documents.
- Story ID: The section or story name in `academy_user_stories.md` that implements the capability.
- ACs: Acceptance Criteria IDs from the story (if present) or from the UX doc success criteria.

---

## 1. Player Elevation & Access
- Experience: Player Elevation Workflow (`academy_core_user_experiences.md`)
- Story: "Player Elevation Wizard (Managed Player ➜ Authenticated User)" (User Stories doc, Section 1.1)
- ACs: AC1, AC2, AC3, AC4, AC5, AC6, AC7, AC8

---

## 2. Scheduling & Calendar Management
(See `academy_scheduling_user_experiences.md`)

### 2.1 Season Configuration
- Experience: Season Setup (Seasons list & actions)
- Story: "Weekly Group Schedule Definition (Head Coach)" (User Stories doc, Story 2.1)
- ACs: SCH1 (occurrence count), SCH3 (future-only regeneration)

### 2.2 Weekly Group Schedule Template Wizard
- Experience: Weekly Schedule Template Wizard (matrix-based)
- Story: "Weekly Group Schedule Definition (Head Coach)" (User Stories doc, Story 2.1)
- ACs: SCH1, SCH2 (court conflict detection), SCH4 (follow-up creation), SCH5 (chatter log)

### 2.3 Occurrence Generation & Regeneration
- Experience: Generate/Regenerate Occurrences for season
- Story: "Weekly Group Schedule Definition (Head Coach)" and generation pseudo-code (User Stories doc)
- ACs: SCH1, SCH3

### 2.4 Individual Session Booking
- Experience: Coach-created individual sessions (ad-hoc)
- Story: "Individual Session Booking (Coach ➜ Player(s))" (User Stories doc, Story 2.2)
- ACs: IND1, IND2, IND3

### 2.5 Absence Reporting
- Experience: Guardian/Player absence reporting via portal
- Story: "Absence Notification (Guardian ➜ Attendance Planning)" (User Stories doc, Story 2.3)
- ACs: ABS1, ABS2, ABS3

### 2.6 Seasonal Suspension (Dome)
- Experience: Suspend sessions for date range
- Story: "Dome / Seasonal Suspension" (User Stories doc, Story 2.4)
- ACs: SUSP1, SUSP2, SUSP3

### 2.7 Calendar Visibility & Privacy
- Experience: Scoped calendar views for guardians, players, coaches
- Story: "Calendar Visibility & Access Control" (User Stories doc, Story 2.5)
- ACs: VIS1, VIS2, VIS3

### 2.8 Follow-up Physical Session Linking
- Experience: Auto-generated follow-up PA sessions chained to tennis session
- Story: Part of "Weekly Group Schedule Definition" (User Stories doc, Story 2.1)
- ACs: SCH4, SX7 (from scheduling UX doc)

### 2.9 Court Conflict Detection
- Experience: Prevent overlapping court bookings at template or occurrence creation time
- Story: Covered in Stories 2.1 and 2.2
- ACs: SCH2, IND1, SX2

---

## 3. Attendance & Billing (trace pointers)
- Experience: Frictionless check-in, attendance aggregation for billing (from requirements)
- Story: Not yet fully expanded into separate user stories in `academy_user_stories.md` (future work)
- Next action: Draft attendance-specific stories mapping attendance -> billing lines -> invoicing.

---

## 4. Reporting & Progress (trace pointers)
- Experience: Progress report creation/versioning by lead coach
- Story: Not yet present in `academy_user_stories.md` (future work)
- Next action: Author Progress Report user story with ACs and data fields.

---

## 5. Cross-cutting Concerns
- Experience: Audit & Chatter logging across scheduling operations
- Story: Logging/audit behaviors are documented in scheduling stories and UX docs
- ACs: SCH5, SX8

---

## Notes & Next Steps
- Recommendation: Add explicit story IDs (or issue numbers) when tickets are created and update this matrix for traceability.
- Suggestion: Add a simple CSV export of this matrix for project management tools.


End of traceability matrix.
