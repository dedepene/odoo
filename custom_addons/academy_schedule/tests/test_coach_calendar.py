from datetime import datetime, time, timedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestAcademyCoachCalendar(TransactionCase):
    def setUp(self):
        super().setUp()
        self.today = fields.Date.today()
        self.skill_group = self.env['academy.skill.group'].create({
            'name': 'Yellow Ball',
            'code': 'YEL',
            'min_age': 10,
            'max_age': 14,
        })
        self.court = self.env['academy.court'].create({'name': 'Court A'})
        self.season = self.env['academy.season'].create({
            'name': 'Calendar Season',
            'start_date': self.today,
            'end_date': self.today + timedelta(days=90),
            'active': True,
        })
        try:
            overlapping = self.env['academy.season'].search([
                ('id', '!=', self.season.id),
                ('active', '=', True),
                ('start_date', '<=', self.season.end_date),
                ('end_date', '>=', self.season.start_date),
            ])
            if overlapping:
                overlapping.write({'active': False, 'state': 'draft'})
        except Exception:
            pass
        self.season.action_activate()

        company = self.env.ref('base.main_company')
        group_user = self.env.ref('base.group_user')
        base_user_vals = {
            'company_id': company.id,
            'company_ids': [(6, 0, [company.id])],
            'group_ids': [(6, 0, [group_user.id])],
            'password': 'coach',
        }
        self.primary_coach = self.env['res.users'].create({
            **base_user_vals,
            'name': 'Coach Primary',
            'login': 'coach.primary@example.com',
            'email': 'coach.primary@example.com',
        })
        self.secondary_coach = self.env['res.users'].create({
            **base_user_vals,
            'name': 'Coach Secondary',
            'login': 'coach.secondary@example.com',
            'email': 'coach.secondary@example.com',
        })

    @staticmethod
    def _make_datetime(date_value, hour, minute=0):
        return datetime.combine(date_value, time(hour, minute))

    def _create_occurrence(self, **extra):
        values = {
            'season_id': self.season.id,
            'date': self.today,
            'start_datetime': self._make_datetime(self.today, 9),
            'end_datetime': self._make_datetime(self.today, 10),
            'session_type': 'tennis_group',
            'skill_group_id': self.skill_group.id,
            'court_ids': [(6, 0, self.court.ids)],
            'coach_id': self.primary_coach.id,
        }
        values.update(extra)
        return self.env['academy.session.occurrence'].create(values)

    def test_calendar_event_created_and_updated(self):
        occurrence = self._create_occurrence()
        event = occurrence.calendar_event_id

        self.assertTrue(event)
        self.assertEqual(event.user_id, self.primary_coach)
        self.assertEqual(event.res_model, 'academy.session.occurrence')
        self.assertEqual(event.res_id, occurrence.id)
        self.assertEqual(event.partner_ids, self.primary_coach.partner_id)

        new_start = occurrence.start_datetime + timedelta(hours=1)
        new_end = occurrence.end_datetime + timedelta(hours=1)
        occurrence.write({'start_datetime': new_start, 'end_datetime': new_end})
        event.invalidate_recordset()
        self.assertEqual(event.start, new_start)
        self.assertEqual(event.stop, new_end)

        occurrence.write({'coach_id': self.secondary_coach.id})
        event.invalidate_recordset()
        self.assertEqual(event.user_id, self.secondary_coach)
        self.assertEqual(event.partner_ids, self.secondary_coach.partner_id)

    def test_calendar_event_removed_when_coach_cleared(self):
        occurrence = self._create_occurrence()
        event = occurrence.calendar_event_id
        self.assertTrue(event)

        occurrence.write({'coach_id': False})
        self.assertFalse(occurrence.calendar_event_id)
        self.assertFalse(event.exists())

    def test_calendar_event_marked_inactive_on_cancellation(self):
        occurrence = self._create_occurrence()
        occurrence.action_cancel()
        event = occurrence.calendar_event_id
        event.invalidate_recordset()
        self.assertFalse(event.active)
