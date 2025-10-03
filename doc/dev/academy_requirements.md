Use this document to put together a roadmap and top-level design to modify this odoo deployment so it becomes a tennis academy management system. I need the users to get a feeling as if it was a custom built system and as many irrelevant entities and modules should be removed or hidden. Make sure to examine the custom_addons folders for some custom implementations that I have done so far. Assume you are preparing the document for someone who is not intimately familiar with odoo and the main apps. These are the requirements:

### Actors/Stakeholders

1. Players

  - these fall in various groups, loosely determined by age and skill. For group practice sessions grouping use the following groups "red", "orange", "green" , "hard" and "advanced". Each is named after the type of tennis balls they use for practice.
  - it's critical that players have a DOB in the system. Their age determines competition availabilites.
  - each player should have at least one parent/guardian associated. A parent can have one or more kids. One of the guardians should be indicated as a primary/emergency contact
  - each player should have a group skill level 
  
2. Parent/Guardian
  - each guardian should be able to take all actions on behalf of their kid(s) that are available to the kid's account
  - each guardian should be registered with a phone number and an email address
  
3. Coaches
  - coaches themselves should fall in different categories e.g. head, senior, associate, visiting/auxilary
  - a coach should have a one to many relationship with players - i.e. one coach is considered to be the lead coach for a number of kids
  
4. courts site admins
  - should be able to bill parents for consumables at the bar/cafe or pro shop - e.g. drinks, food, overgrips etc. The amount should be kept as a running total and also the outstanding amount included in the monthly invoice with the amount due.

### Activities and use cases

1. Scheduling
  - a head coach determines the weekly training schedule as the season starts. Each skill group (reds, greens etc.) are scheduled with time slots e.g. "greens" and "hards" every mon, wed, fri from 17:00 to 19:00 followed by an hour of physical activities training. Reds and Oranges have the Tue and Thursday sessions from 17:00 to 19:00. 
  - there are four types of practice sessions to be scheduled : tennis skills, individual skills physical activities / strenght training, and individual PA/strenght
  - a guardian should be able to notify the coaching staff when a kid is going to be absent from a sheduled practice session. This is not meant to be like in a chat or other real-time interaction. More like creating event on a shared calendar, or modifying an existing event. I need suggestions here.
  - a scheduled training session is to be associated with a tennis court - e.g. reds and oranges on Tuesday starting at 17 and ending at 19 book court numbers 1, 3 and 5
  - once the group sessions are schedules they repeat each week without alterations.
  - when/if there's a indoor dome going up or a tournament is taking place all schedules are to be suspended for the duration
  - each coach, not only the head coaches can schedule individual practice sessions with one or more than one players
  - the lead coach's schedule/calendar should be available to the associated kids and their guardians in addition to the other coaches. However the schedule should not be available to kids or guradinans who are not assigned to this coach
  
2. Attendance
  - each player should be able to check into a training session in a frictionless manner. Maybe use the odoo employee attendance module with a kiosk? If we go with this each player should be set up as an employee i assume.
  - each attendance should be added up for the monthly attendace figure and used as an invoice basis for players who are on a per-visit billing basis
  
3. Billing
  - each guardian should receive a monthly invoice with services rendered from the tennis academy which is to include: practice sessions, bar/cafe consumables, pro shop purchases, extras

4. Reports
  - a report should be available to show the attendance of each player for the month
  - a progress report should be available for each player showing their skill level and improvements over time. This is to be filled in by the lead coach and should be available to the player and their guardians. The coach should be able to specify the period the report covers and also add comments. The report should be versioned so that previous reports are available for review.

### Extras and suggestions

1. Highlight any potential issues or conflicts with what I have outlined above
2. Suggest easy to implement fuctionality that will add further value to all stakeholders

### Deliverable
Create a separate document next to this one outlining the configuration and development needed to achieve all of the requirements. Define two sections - one with tasks that are accomplished simply by styling and configuring the core odoo and installing free apps and modules. Never suggest paid modules and apps. The other section will be populated with the rest of the requirements that need custom modules created for them. Itemize, describe them and use some pseudo code to illustrate the concept but do not flesh out complete solutions for now. Assume your audience is not intimately familiar with odoo or crm systems in general but is technically savvy and capable to code in python as well as deploy the app.