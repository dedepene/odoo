from odoo.fields import Command
from odoo.tests import TransactionCase, tagged
from odoo.tools.sql import column_exists


@tagged('academy_core')
class TestAcademyCoachRoles(TransactionCase):
    def setUp(self):
        super().setUp()
        self.base_user_group = self.env.ref('base.group_user')
        self.coach_group = self.env.ref('academy_core.group_academy_coach')
        self.head_coach_group = self.env.ref('academy_core.group_academy_head_coach')
        self._ensure_autopost_bills_default()

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

    def _partner_vals(self, *, name: str, email: str):
        vals = {
            'name': name,
            'email': email,
        }
        if 'autopost_bills' in self.env['res.partner']._fields:
            vals.setdefault('autopost_bills', 'never')
        return vals

    def _create_internal_user(self, login_prefix: str):
        name = f'{login_prefix.title()} Coach'
        email = f'{login_prefix}@example.com'
        partner = self.env['res.partner'].create(self._partner_vals(name=name, email=email))
        return self.env['res.users'].with_context(no_reset_password=True).create({
            'name': name,
            'login': email,
            'email': email,
            'partner_id': partner.id,
            'group_ids': [Command.link(self.base_user_group.id)],  # type: ignore[arg-type]
        })

    def test_flag_assigns_group_on_create(self):
        partner = self.env['res.partner'].create(self._partner_vals(
            name='New Coach',
            email='coach_create@example.com',
        ))
        user = self.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'New Coach',
            'login': 'coach_create@example.com',
            'email': 'coach_create@example.com',
            'academy_is_coach': True,
            'partner_id': partner.id,
            'group_ids': [Command.link(self.base_user_group.id)],  # type: ignore[arg-type]
        })

        self.assertTrue(user.academy_is_coach)  # type: ignore[attr-defined]
        self.assertIn(self.coach_group, user.group_ids)  # type: ignore[attr-defined]

    def test_group_assignment_sets_flag(self):
        user = self._create_internal_user('coach_assign')
        user.write({'group_ids': [Command.link(self.coach_group.id)]})  # type: ignore[arg-type]

        self.assertTrue(user.academy_is_coach)  # type: ignore[attr-defined]

    def test_unset_flag_removes_groups(self):
        user = self._create_internal_user('coach_remove')
        user.write({
            'group_ids': [
                Command.link(self.coach_group.id),  # type: ignore[arg-type]
                Command.link(self.head_coach_group.id),  # type: ignore[arg-type]
            ]
        })
        self.assertTrue(user.academy_is_coach)  # type: ignore[attr-defined]

        user.write({'academy_is_coach': False})

        self.assertFalse(user.academy_is_coach)  # type: ignore[attr-defined]
        self.assertNotIn(self.coach_group, user.group_ids)  # type: ignore[attr-defined]
        self.assertNotIn(self.head_coach_group, user.group_ids)  # type: ignore[attr-defined]

    def test_search_supports_list_operators(self):
        coach = self._create_internal_user('coach_search')
        coach.write({'academy_is_coach': True})
        non_coach = self._create_internal_user('coach_search_other')

        users = self.env['res.users'].with_context(active_test=False)
        relevant_ids = [coach.id, non_coach.id]

        coaches = users.search([
            ('id', 'in', relevant_ids),
            ('academy_is_coach', 'in', [True]),
        ])
        self.assertIn(coach, coaches)
        self.assertNotIn(non_coach, coaches)

        non_coaches = users.search([
            ('id', 'in', relevant_ids),
            ('academy_is_coach', 'in', [False]),
        ])
        self.assertIn(non_coach, non_coaches)
        self.assertNotIn(coach, non_coaches)

        coaches_via_not_in = users.search([
            ('id', 'in', relevant_ids),
            ('academy_is_coach', 'not in', [False]),
        ])
        self.assertIn(coach, coaches_via_not_in)
        self.assertNotIn(non_coach, coaches_via_not_in)

        non_coaches_via_not_in = users.search([
            ('id', 'in', relevant_ids),
            ('academy_is_coach', 'not in', [True]),
        ])
        self.assertIn(non_coach, non_coaches_via_not_in)
        self.assertNotIn(coach, non_coaches_via_not_in)
