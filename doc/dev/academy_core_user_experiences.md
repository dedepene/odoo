# Academy Core – User Experiences & Manual Verification

## New/Updated Experiences
1. **Academy Player Management (Site Admins & Head Coaches)**
   - Dedicated “Academy ▸ Players” workspace with tailored list/form views.
   - Automatic player code assignment (`PLR####`) and age calculation once DOB is entered.
   - Guardian linkage UI with validation prompts for missing contact data.
   - Single-click elevation to portal user when a player is ready for self-service access.

2. **Skill Group Configuration (Site Admins & Head Coaches)**
   - “Academy ▸ Configuration ▸ Skill Groups” enables defining age-banded cohorts.
   - Enforced uniqueness of group code/name prevents conflicting set-ups.
   - Age range enforcement toggles allow exceptions (e.g., advanced players promoted early).

3. **Player Elevation Workflow (Site Admins)**
   - Modal wizard collects login/email details and optionally reuses guardian portal rights.
   - Immediate portal user creation with optional welcome email dispatch.
   - Player form shows linked portal user badge to confirm status.

## Manual Verification Checklist
Follow the steps per persona to confirm the implementation.

### A. Pre-requisites
- Ensure the `academy_core` module is installed and the database has outgoing email configured (needed only to test welcome messages).

### B. Skill Group Setup
1. Navigate to **Academy ▸ Configuration ▸ Skill Groups**.
2. Create a “Green Ball” group with min age 8, max age 10, enforcement enabled.
3. Attempt to create a second group with the same code – expect a uniqueness error.
4. Edit the group to set min age greater than max age – saving should raise a validation error.

### C. Guardian Data Integrity
1. Open **Contacts** and create a new partner “Taylor Parent” with email + phone.
2. Remove the phone value and try to save – should succeed (contact form doesn’t enforce it), but note the player constraint will catch it later.

### D. Player Creation & Constraints
1. Go to **Academy ▸ Players** and create a new player:
   - Name: “Jordan Player”.
   - DOB: nine years ago.
   - Skill Group: Green Ball.
   - Guardians: add “Taylor Parent”.
   - Primary Guardian: “Taylor Parent”.
   - Provide basic contact info if desired.
2. Save – record should create with a `PLR####` reference and computed age.
3. Edit the same player, remove all guardians, and click save – expect a blocking error about missing guardians.
4. Re-add guardian, but set primary guardian to a *different* contact – expect validation error.
5. Edit the guardian partner and clear both phone & mobile. Try saving the player again – expect error requiring contact details.

### E. Age Alignment Enforcement
1. Duplicate the “Jordan Player” form and change DOB to twelve years ago.
2. Try to save – expect an error indicating the player is older than the group allows.
3. Uncheck “Enforce Age Range” on the skill group and retry – save should now succeed (for exception handling).

### F. Elevation Wizard Flow
1. Ensure the guardian partner has a valid email.
2. Open the player record and click **Elevate to Portal**.
3. In the wizard, accept the default login/email, keep the welcome email enabled, and confirm.
4. After success:
   - The player form should display the portal user badge.
   - Inspect **Settings ▸ Users & Companies ▸ Users** to confirm the new user has the academy player portal group (and guardian group if selected).
5. Attempt to elevate again – the button should be hidden/inactive because a user already exists.

## Success Criteria
- Skill groups enforce data integrity (steps B3–B4).
- Player form blocks missing guardians, mismatched primary guardian, and incomplete guardian contact details (steps D3–D5).
- Age enforcement aligns with group configuration (steps E1–E3).
- Elevation wizard creates portal users with correct group memberships and prevents duplicates (steps F1–F5).

Document and share any deviations—these mark regressions against the core deliverables.
