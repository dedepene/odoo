occurrences = env['academy.session.occurrence'].search([
    ('coach_id', '!=', False),
    ('start_datetime', '!=', False),
    ('end_datetime', '!=', False),
])
print(f"Resyncing {len(occurrences)} occurrences")
occurrences._sync_calendar_events()
env.cr.commit()  # type: ignore[name-defined]
print('Done')
