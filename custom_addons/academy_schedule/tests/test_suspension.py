from datetime import datetime, time, timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests.common import TransactionCase


class TestAcademyScheduleSuspension(TransactionCase):
    def setUp(self):
        super().setUp()
        self.today = fields.Date.today()

        self.skill_group = self.env['academy.skill.group'].create({
            'name': 'Green Ball',
            'code': 'GREEN',
            'min_age': 8,
            'max_age': 12,
        })

        base_vals = {
            'name': 'Parent One',
            'email': 'parent@example.com',
            'phone': '555-0100',
        }
        # Some test environments or module load orders may not have the
        # `autopost_bills` field available on the ORM, but the DB column
        # may still be present and declared NOT NULL. Ensure the DB is
        # backfilled and has a server default so plain INSERTs (without
        # the ORM field) don't fail. This is a safe no-op when the
        # column doesn't exist.
        try:
            self.env.cr.execute("""
                UPDATE res_partner SET autopost_bills = 'ask' WHERE autopost_bills IS NULL;
            """)
            # set a server default so future raw INSERTs get a value
            try:
                self.env.cr.execute(
                    "ALTER TABLE res_partner ALTER COLUMN autopost_bills SET DEFAULT 'ask'"
                )
            except Exception:
                # If column doesn't exist or DB doesn't allow alter here,
                # ignore and continue; INSERT will include ORM default when available.
                pass
        except Exception:
            # Column likely doesn't exist yet - ignore and rely on ORM defaults
            pass
        # Include the ORM field when present
        if 'autopost_bills' in self.env['res.partner']._fields:
            base_vals['autopost_bills'] = 'ask'
        self.guardian = self.env['res.partner'].create(base_vals)

        player_dob = self.today - relativedelta(years=10)
        self.player = self.env['academy.player'].create({
            'name': 'Player One',
            'dob': player_dob,
            'skill_group_id': self.skill_group.id,
            'guardian_ids': [(6, 0, self.guardian.ids)],
            'primary_guardian_id': self.guardian.id,
        })

        self.court = self.env['academy.court'].create({
            'name': 'Court 1',
        })

        self.season = self.env['academy.season'].create({
            'name': 'Test Season',
            'start_date': self.today - timedelta(days=7),
            'end_date': self.today + timedelta(days=30),
            'active': True,
        })
        # Some environments include pre-existing active seasons (demo or
        # fixtures) that overlap with our test season. The model enforces
        # non-overlapping active seasons which causes tests to fail when the
        # demo season is present. Deactivate any overlapping active seasons
        # (except the one we just created) before activating ours.
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
            # If the season model or fields aren't available yet for any
            # reason, ignore and let action_activate raise the original
            # error — other guards in tests will catch it.
            pass

        self.season.action_activate()

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _make_datetime(date_value, hour=17, minute=0):
        return datetime.combine(date_value, time(hour, minute))

    def _create_group_occurrence(self, date_value):
        """Create a group session occurrence for the configured season."""
        return self.env['academy.session.occurrence'].create({
            'season_id': self.season.id,
            'date': date_value,
            'start_datetime': self._make_datetime(date_value, 17, 0),
            'end_datetime': self._make_datetime(date_value, 19, 0),
            'session_type': 'tennis_group',
            'skill_group_id': self.skill_group.id,
            'court_ids': [(6, 0, self.court.ids)],
        })

    def _create_individual_occurrence(self, date_value):
        return self.env['academy.session.occurrence'].create({
            'season_id': self.season.id,
            'date': date_value,
            'start_datetime': self._make_datetime(date_value, 15, 0),
            'end_datetime': self._make_datetime(date_value, 16, 0),
            'session_type': 'tennis_individual',
            'court_ids': [(6, 0, self.court.ids)],
            'player_ids': [(6, 0, self.player.ids)],
            'is_individual': True,
        })

    # ------------------------------------------------------------------
    # Tests
    # ------------------------------------------------------------------
    def test_existing_group_occurrences_suspended(self):
        future_date = self.today + timedelta(days=5)
        occurrence = self._create_group_occurrence(future_date)

        wizard = self.env['academy.suspension.wizard'].create({
            'season_id': self.season.id,
            'start_date': future_date - timedelta(days=1),
            'end_date': future_date + timedelta(days=1),
            'reason': 'Indoor dome installation',
            'apply_to_group': True,
            'apply_to_individual': False,
            'cancel_existing': True,
        })
        wizard.action_suspend()

        occurrence.invalidate_recordset()
        suspension = self.season.suspension_ids
        self.assertTrue(suspension)
        self.assertEqual(occurrence.state, 'suspended')
        self.assertEqual(occurrence.suspension_id, suspension)
        self.assertEqual(occurrence.state_before_suspension, 'planned')

        # Newly generated occurrences in the window inherit suspension state
        another_date = future_date + timedelta(days=1)
        new_occurrence = self._create_group_occurrence(another_date)
        self.assertEqual(new_occurrence.state, 'suspended')
        self.assertEqual(new_occurrence.suspension_id, suspension)

    def test_individual_sessions_respect_suspension(self):
        future_date = self.today + timedelta(days=3)
        suspension = self.env['academy.season.suspension'].create({
            'season_id': self.season.id,
            'start_date': future_date - timedelta(days=1),
            'end_date': future_date + timedelta(days=1),
            'reason': 'Tournament blackout',
            'apply_to_group': False,
            'apply_to_individual': True,
        })
        suspension.apply_window(include_existing=False)

        individual_occurrence = self._create_individual_occurrence(future_date)
        self.assertEqual(individual_occurrence.state, 'suspended')
        self.assertEqual(individual_occurrence.suspension_id, suspension)
        self.assertEqual(individual_occurrence.state_before_suspension, 'planned')

    def test_lift_suspension_reactivates_future_only(self):
        future_date = self.today + timedelta(days=4)
        later_date = self.today + timedelta(days=10)

        suspension = self.env['academy.season.suspension'].create({
            'season_id': self.season.id,
            'start_date': self.today,
            'end_date': self.today + timedelta(days=14),
            'reason': 'Maintenance window',
            'apply_to_group': True,
            'apply_to_individual': False,
        })
        suspension.apply_window(include_existing=False)

        future_occurrence = self._create_group_occurrence(future_date)
        later_occurrence = self._create_group_occurrence(later_date)

        self.assertEqual(future_occurrence.state, 'suspended')
        self.assertEqual(later_occurrence.state, 'suspended')

        # Simulate the first occurrence moving to the past (still suspended)
        past_date = self.today - timedelta(days=1)
        future_occurrence.write({
            'date': past_date,
            'start_datetime': self._make_datetime(past_date, 17, 0),
            'end_datetime': self._make_datetime(past_date, 19, 0),
        })
        self.assertEqual(future_occurrence.state, 'suspended')

        suspension._lift_suspension()

        later_occurrence.invalidate_recordset()
        future_occurrence.invalidate_recordset()

        self.assertEqual(later_occurrence.state, 'planned')
        self.assertFalse(later_occurrence.suspension_id)
        self.assertEqual(future_occurrence.state, 'suspended')
        self.assertTrue(future_occurrence.suspension_id)