from datetime import date

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.exceptions import ValidationError
from odoo.tests import TransactionCase, tagged
from odoo.tools.sql import column_exists


@tagged('academy_core')
class TestAcademyPlayerConstraints(TransactionCase):
    def setUp(self):
        super().setUp()
        self._ensure_autopost_bills_default()
        self.skill_group = self.env['academy.skill.group'].create({
            'name': 'Green Ball',
            'code': 'GREEN',
            'min_age': 8,
            'max_age': 10,
        })
        self.guardian = self.env['res.partner'].create(self._guardian_vals(
            name='Pat Guardian',
            email='pat.guardian@example.com',
            phone='+15550001',
        ))

    def _player_vals(self):
        dob = date.today() - relativedelta(years=9)
        return {
            'name': 'Ada Player',
            'dob': fields.Date.to_string(dob),
            'skill_group_id': self.skill_group.id,
            'guardian_ids': [(6, 0, [self.guardian.id])],
            'primary_guardian_id': self.guardian.id,
        }

    def _guardian_vals(self, **overrides):
        base_vals = {
            'name': overrides.get('name', 'Guardian'),
            'email': overrides.get('email', 'guardian@example.com'),
        }
        if phone := overrides.get('phone'):
            base_vals['phone'] = phone
        if 'autopost_bills' in self.env['res.partner']._fields:
            base_vals.setdefault('autopost_bills', 'never')
        return base_vals

    def _ensure_autopost_bills_default(self):
        if column_exists(self.env.cr, 'res_partner', 'autopost_bills'):
            self.env.cr.execute(
                "ALTER TABLE res_partner ALTER COLUMN autopost_bills SET DEFAULT %s",
                ('never',),
            )
            self.env.cr.execute(
                "UPDATE res_partner SET autopost_bills = %s WHERE autopost_bills IS NULL",
                ('never',),
            )

    def test_player_requires_guardian(self):
        vals = self._player_vals()
        vals.pop('guardian_ids')
        self.assertRaises(ValidationError, self.env['academy.player'].create, vals)

    def test_primary_guardian_must_be_in_guardians(self):
        other_guardian = self.env['res.partner'].create(self._guardian_vals(
            name='Taylor Guardian',
            email='taylor.guardian@example.com',
            phone='+15550002',
        ))
        vals = self._player_vals()
        vals['primary_guardian_id'] = other_guardian.id
        self.assertRaises(ValidationError, self.env['academy.player'].create, vals)

    def test_guardian_must_have_contact_details(self):
        incomplete_guardian = self.env['res.partner'].create(self._guardian_vals(
            name='No Phone Guardian',
            email='no.phone@example.com',
        ))
        vals = self._player_vals()
        vals['guardian_ids'] = [(6, 0, [incomplete_guardian.id])]
        vals['primary_guardian_id'] = incomplete_guardian.id
        self.assertRaises(ValidationError, self.env['academy.player'].create, vals)

    def test_age_range_constraint(self):
        vals = self._player_vals()
        vals['dob'] = fields.Date.to_string(date.today() - relativedelta(years=12))
        self.assertRaises(ValidationError, self.env['academy.player'].create, vals)

    def test_valid_player_creation(self):
        player = self.env['academy.player'].create(self._player_vals())
        data = player.read(['reference', 'primary_guardian_id', 'guardian_ids', 'age_years'])[0]
        self.assertTrue(data['reference'])
        self.assertEqual(data['primary_guardian_id'][0], self.guardian.id)
        self.assertTrue(data['guardian_ids'])
        self.assertAlmostEqual(data['age_years'], 9, delta=0.2)
