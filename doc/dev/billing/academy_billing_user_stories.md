# Academy Billing – User Stories (Pre-Paid & Reconciliation Model)

## 1. Document Context & Design Philosophy

This document outlines the user stories for the Tennis Academy's billing system, based on a **monthly pre-paid and reconciliation model**. This approach provides stable cash flow for the academy while offering fair credits to guardians for excused absences.

**Core Principles:**
1.  **Bill in Advance:** Guardians are invoiced at the *beginning* of the month for all *scheduled* sessions in that month.
2.  **Credit for Excused Absences:** Credits are issued only for absences that are both reported by a guardian and subsequently acknowledged by a coach.
3.  **Reconcile at Month-End:** A reconciliation process runs after the month is over to generate credits for the next billing cycle.
4.  **No-Shows Are Not Credited:** The pre-payment for unexcused absences (no-shows) is retained by the academy.
5.  **Unified Invoicing:** Ad-hoc charges (consumables, extras) are consolidated into the single monthly pre-paid invoice.

---

## 2. Actors & Roles

| Actor | Responsibility |
|---|---|
| **Site Admin** | Manages billing configuration, oversees automated processes, handles exceptions, and adds ad-hoc charges. |
| **Guardian** | Receives and pays invoices, views billing history, and reports absences. |
| **Coach** | Acknowledges reported absences, which makes them eligible for credit. |
| **System** | Executes scheduled jobs for invoicing and reconciliation, applies credits, and generates records. |

---

## 3. User Stories

### 3.1 Billing Template Management

**As a** Site Admin,  
**I want** to create and manage billing templates that define the rules for invoice generation,  
**So that** I can configure and standardize the billing process across the academy.

#### 3.1.1 Preconditions
- A Site Admin is logged into the system.

#### 3.1.2 Happy Path Flow
1.  The Site Admin navigates to **Academy -> Configuration -> Billing Templates**.
2.  The system displays a list of existing templates. A default "Monthly Pre-Paid" template is present.
3.  The admin opens the default template.
4.  The form contains the following fields:
    *   **Name:** "Monthly Pre-Paid" (editable).
    *   **Description:** A non-editable text field explaining, "This template invoices guardians on a specified day of the month for all scheduled sessions in that month. Credits for acknowledged absences are applied to the following month's invoice."
    *   **Invoice Generation Day:** An integer field, defaulting to `1`, allowing the admin to choose the day of the month the invoice is generated.
    *   **Payment Due Days:** An integer field, defaulting to `10`, representing the number of days after generation the invoice is due.
5.  The admin can adjust the generation day and due days.
6.  The `academy.session` model (which acts as the session template) has a mandatory `billing_template_id` field, which defaults to this pre-paid template.

#### 3.1.3 Postconditions
- A default `academy.billing.template` record exists.
- The rules for invoice timing and due dates are stored in the template.

#### 3.1.4 Data Entities & Fields
| Entity | Fields Impacted / Added |
|---|---|
| `academy.billing.template` | New model with `name`, `description`, `invoice_generation_day`, `payment_due_days`. |
| `academy.session` | A new mandatory `billing_template_id` (Many2one to `academy.billing.template`). |

#### 3.1.5 Acceptance Criteria
| ID | Criterion |
|---|---|
| BILL-TPL-1 | A "Billing Templates" menu exists under Configuration. |
| BILL-TPL-2 | A default, pre-configured "Monthly Pre-Paid" template is available upon installation. |
| BILL-TPL-3 | The template allows configuration of the invoice generation day and payment due days. |
| BILL-TPL-4 | All academy sessions must be linked to a billing template. |

---

### 3.2 Monthly Pre-Paid Invoice Generation

**As a** Site Admin,  
**I want** the system to automatically generate and issue invoices to guardians based on the rules in the session's billing template,  
**So that** the academy can secure payment for the upcoming month's scheduled activities in a timely and configurable manner.

#### 3.2.1 Preconditions
- An active season is configured with scheduled sessions (`academy.session`).
- All sessions are linked to an `academy.billing.template`.
- Active players are assigned to skill groups or individual sessions.
- Session pricing is configured in the system.
- Guardian accounts are linked to players and have valid contact information.
- A scheduled job (`cron_generate_monthly_prepaid_invoices`) is configured to run **daily**.

#### 3.2.2 Happy Path Flow
1.  The daily scheduled job executes.
2.  The system checks the current day of the month (e.g., the 1st).
3.  It finds all `academy.billing.template` records where `invoice_generation_day` matches the current day.
4.  For each matching template, the system identifies all players scheduled for sessions linked to that template in the upcoming month.
5.  For each of those players, the system calculates the total base charge: `(Number of Scheduled Sessions) x (Session Price)`.
6.  The system searches for any open, unapplied credit notes (`account.move` of type `out_refund`) for the player's primary guardian.
7.  A new draft invoice (`account.move`) is created for the guardian. The invoice due date is calculated based on the `payment_due_days` from the template.
8.  The invoice includes:
    *   A line item for the total base charge (e.g., "November 2025 Tennis Program - 8 sessions").
    *   Line items for each open credit note, which reduce the total amount due.
9.  The system posts the invoice, making it active.
10. An email notification is sent to the guardian, informing them that their invoice is ready in the portal.

#### 3.2.3 Alternative / Error Paths
| Condition | Outcome |
|---|---|
| Player has no scheduled sessions | No invoice is generated for that player. |
| Session pricing is not configured | The process fails for that player; an error is logged for the Site Admin to review. |
| Guardian has no valid email | The invoice is generated, but the notification fails; an error is logged. |

#### 3.2.4 Postconditions
- A posted invoice exists for each guardian for the current month, with the correct due date.
- Any available credits from the previous month are now applied and marked as 'in_payment' or 'paid'.
- Guardians have received an email notification.

#### 3.2.5 Data Entities & Fields
| Entity | Fields Impacted / Added |
|---|---|
| `account.move` | Created with `move_type='out_invoice'`, linked to guardian partner. `invoice_date_due` is set based on the template. |
| `account.move.line` | Contains details of the base charge and applied credits. |
| `ir.cron` | `cron_generate_monthly_prepaid_invoices` is now scheduled to run daily. |

#### 3.2.6 Acceptance Criteria
| ID | Criterion |
|---|---|
| BILL-PRE-1 | Invoices are automatically generated on the day of the month specified in the billing template. |
| BILL-PRE-2 | The invoice amount correctly reflects the total number of scheduled sessions for that month. |
| BILL-PRE-3 | Existing credits on the guardian's account are automatically applied to the new invoice. |
| BILL-PRE-4 | The invoice due date is correctly calculated based on the template's `payment_due_days`. |
| BILL-PRE-5 | Guardians receive an email notification with a link to their new invoice. |

---

### 3.3 Ad-Hoc Charge Management

**As a** Site Admin,  
**I want** a simple interface to add miscellaneous charges (e.g., for pro-shop items, drinks, or stringing services) to a guardian's account,  
**So that** all academy-related expenses can be consolidated into a single monthly invoice.

#### 3.3.1 Preconditions
- A Site Admin is logged into the system.
- Guardian and player records exist.

#### 3.3.2 Happy Path Flow
1.  The Site Admin navigates to **Academy -> Billing -> Ad-Hoc Charges**.
2.  The admin clicks "Create".
3.  A form appears to create a new `academy.billing.item`.
4.  The admin fills in the details:
    *   **Guardian:** Selects the guardian to bill.
    *   **Player:** (Optional) Selects the specific child the charge is for.
    *   **Description:** Enters a clear description (e.g., "Pro Shop: 2x Overgrips").
    *   **Amount:** Enters the total amount of the charge.
    *   **Date:** Defaults to today.
5.  The admin saves the record. The record is created with a state of 'pending' and a type of 'extra' or 'consumable'.
6.  When the monthly pre-paid invoice is generated, this pending billing item is included as a separate line item.

#### 3.3.3 Postconditions
- An `academy.billing.item` record is created.
- This item will be included in the guardian's next generated invoice.

#### 3.3.4 Data Entities & Fields
| Entity | Fields Impacted / Added |
|---|---|
| `academy.billing.item` | A new record is created with `origin_type` set to 'extra' or 'consumable'. |

#### 3.3.5 Acceptance Criteria
| ID | Criterion |
|---|---|
| BILL-AH-1 | A Site Admin can create an ad-hoc charge for a guardian with a description and amount. |
| BILL-AH-2 | The created ad-hoc charge appears as a distinct line item on the guardian's next monthly invoice. |

---

### 3.4 Absence Acknowledgment for Credit

**As a** Coach,  
**I want** to be able to "Acknowledge" a guardian-reported absence,  
**So that** the system can confirm the absence is excused and trigger a credit for the guardian.

#### 3.4.1 Preconditions
- A guardian has already reported an absence via the portal, creating an `academy.session.absence` record.
- The coach has permissions to view and manage absences for their sessions.

#### 3.4.2 Happy Path Flow
1.  The coach views the details of a session, either before or after it occurs.
2.  The session view clearly lists any players with "Reported Absences".
3.  Next to each reported absence, there is an "Acknowledge" button.
4.  The coach verifies the absence is legitimate (e.g., the player was not present).
5.  The coach clicks "Acknowledge".
6.  The system updates the state of the `academy.session.absence` record to 'acknowledged'.
7.  The "Acknowledge" button is replaced with a status indicator, e.g., "Acknowledged on [Date]".
8.  This action is the trigger for the end-of-month reconciliation process to generate a credit.

#### 3.4.3 Alternative / Error Paths
| Condition | Outcome |
|---|---|
| Absence is already acknowledged | The "Acknowledge" button is hidden or disabled. |
| Coach tries to acknowledge an absence for a session they don't lead | The action is not visible (pending security rules). |

#### 3.4.4 Postconditions
- The `academy.session.absence` record's state is set to 'acknowledged'.
- The absence is now eligible to be converted into a credit note during the next reconciliation run.

#### 3.4.5 Data Entities & Fields
| Entity | Fields Impacted / Added |
|---|---|
| `academy.session.absence` | The `state` field is updated from 'reported' to 'acknowledged'. An `acknowledged_by_id` (Many2one to `res.users`) and `acknowledgment_date` (Datetime) should be added. |

#### 3.4.6 Acceptance Criteria
| ID | Criterion |
|---|---|
| BILL-ACK-1 | A coach can see a list of guardian-reported absences for a session. |
| BILL-ACK-2 | An "Acknowledge" action is available for each unacknowledged reported absence. |
| BILL-ACK-3 | Clicking "Acknowledge" changes the absence state and logs which coach performed the action and when. |
| BILL-ACK-4 | An acknowledged absence is the sole trigger for a session credit. |

---

### 3.5 End-of-Month Reconciliation and Credit Generation

**As a** Site Admin,  
**I want** the system to automatically reconcile player accounts at the end of each month,  
**So that** credits for acknowledged absences are generated accurately and made available for the next billing cycle.

#### 3.5.1 Preconditions
- The month has concluded.
- A scheduled job (`cron_reconcile_monthly_absences`) is configured to run on the 1st of the month for the month that just ended.
- Coaches have acknowledged absences throughout the month.

#### 3.5.2 Happy Path Flow
1.  On the 1st of the month (e.g., December 1st), the reconciliation job runs for the previous month (November).
2.  The system queries for all `academy.session.absence` records with a state of 'acknowledged' within that month.
3.  For each acknowledged absence, the system creates a new **credit note** (`account.move` with `move_type='out_refund'`).
4.  The credit note's value is equal to the price of the missed session.
5.  The credit note is linked to the guardian's account and is in an 'open' state, ready to be applied to a future invoice.
6.  The `academy.session.absence` record is marked as 'credited' to prevent duplicate credit generation.

#### 3.5.3 Postconditions
- An open credit note exists for every acknowledged absence in the past month.
- These credits are available to be automatically applied during the next pre-paid invoice generation run.
- Reconciled absence records are marked to prevent reprocessing.

#### 3.5.4 Data Entities & Fields
| Entity | Fields Impacted / Added |
|---|---|
| `account.move` | New records created with `move_type='out_refund'`. |
| `academy.session.absence` | The `state` field is updated from 'acknowledged' to 'credited'. |
| `ir.cron` | `cron_reconcile_monthly_absences` scheduled for the 1st of the month. |

#### 3.5.5 Acceptance Criteria
| ID | Criterion |
|---|---|
| BILL-REC-1 | A scheduled job runs at the end of the month to process acknowledged absences. |
| BILL-REC-2 | A credit note is created for each and every acknowledged absence from the previous month. |
| BILL-REC-3 | No credit is generated for unacknowledged absences or no-shows. |
| BILL-REC-4 | Once an absence is credited, it cannot be credited again. |
