# Helper script executed through `odoo-bin shell` stdin to inspect calendar sync.
from pprint import pprint

coach = env['res.users'].search([('name', '=', 'Andre Agassi')], limit=1)
if not coach:
    print('Coach not found')
else:
    print(f"Coach: {coach.id} - {coach.display_name} (partner={coach.partner_id.id})")
    domain = [
        ('coach_id', '=', coach.id),
        ('date', '>=', '2025-12-01'),
        ('date', '<=', '2025-12-10'),
    ]
    occurrences = env['academy.session.occurrence'].search(domain, order='start_datetime asc')
    print(f"Occurrences found: {len(occurrences)}")
    for occ in occurrences:
        event = occ.calendar_event_id
        print('-' * 60)
        print(f"Occurrence {occ.id}: {occ.name}")
        print(f"  state={occ.state} coach={occ.coach_id.id}" )
        print(f"  start={occ.start_datetime} end={occ.end_datetime}")
        print(f"  calendar_event_id={event.id if event else None}")
        if event:
            print(f"    event user={event.user_id.id} partners={event.partner_ids.ids}")
            print(f"    event active={event.active} show_as={event.show_as}")
            linked = env['calendar.event'].sudo().search([
                ('res_model', '=', 'academy.session.occurrence'),
                ('res_id', '=', occ.id),
            ])
            print(f"    linked events count={len(linked)} -> {linked.ids}")

    print('=' * 60)
    linkeds = env['calendar.event'].sudo().search([
        ('res_model', '=', 'academy.session.occurrence'),
        ('user_id', '=', coach.id),
        ('start', '>=', '2025-12-01 00:00:00'),
        ('start', '<=', '2025-12-10 23:59:59'),
    ])
    print(f"Calendar events tied to coach in window: {len(linkeds)} -> {linkeds.ids}")
