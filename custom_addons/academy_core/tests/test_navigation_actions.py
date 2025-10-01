from odoo.tests import TransactionCase, tagged
from odoo.tools.safe_eval import safe_eval


@tagged('academy_core')
class TestAcademyNavigation(TransactionCase):
    def _eval_domain(self, domain_str: str):
        return safe_eval(domain_str or '[]')

    def _eval_context(self, context_str: str):
        return safe_eval(context_str or '{}', {'ref': lambda xmlid: self.env.ref(xmlid).id})

    def test_guardian_action_configuration(self):
        action = self.env.ref('academy_core.action_academy_guardian')
        domain = self._eval_domain(action.domain)  # type: ignore[attr-defined]
        self.assertIn(('academy_is_guardian', '=', True), domain)

        context = self._eval_context(action.context)  # type: ignore[attr-defined]
        self.assertTrue(context.get('default_academy_is_guardian'))
        self.assertEqual(context.get('default_is_company'), False)
        self.assertEqual(context.get('default_company_type'), 'person')
        self.assertEqual(context.get('search_default_active'), 1)

        menu = self.env.ref('academy_core.menu_academy_guardians')
        menu_action = menu.action  # type: ignore[attr-defined]
        self.assertIsNotNone(menu_action)
        self.assertEqual(menu_action.id, action.id)  # type: ignore[attr-defined]
        site_admin_group = self.env.ref('academy_core.group_academy_site_admin')
        self.assertEqual(menu.group_ids, site_admin_group)  # type: ignore[attr-defined]

    def test_coach_action_configuration(self):
        action = self.env.ref('academy_core.action_academy_coach')
        domain = self._eval_domain(action.domain)  # type: ignore[attr-defined]
        self.assertIn(('academy_is_coach', '=', True), domain)

        context = self._eval_context(action.context)  # type: ignore[attr-defined]
        self.assertTrue(context.get('default_academy_is_coach'))
        self.assertEqual(context.get('default_share'), False)
        self.assertEqual(context.get('search_default_active'), 1)

        command = context.get('default_groups_id')
        self.assertIsInstance(command, list)
        self.assertTrue(command)
        self.assertEqual(command[0][0], 6)
        self.assertEqual(command[0][1], 0)
        group_ids = set(command[0][2])
        base_user_group = self.env.ref('base.group_user').id
        coach_group = self.env.ref('academy_core.group_academy_coach').id
        self.assertIn(base_user_group, group_ids)
        self.assertIn(coach_group, group_ids)

        menu = self.env.ref('academy_core.menu_academy_coaches')
        menu_action = menu.action  # type: ignore[attr-defined]
        self.assertIsNotNone(menu_action)
        self.assertEqual(menu_action.id, action.id)  # type: ignore[attr-defined]
        site_admin_group = self.env.ref('academy_core.group_academy_site_admin')
        self.assertEqual(menu.group_ids, site_admin_group)  # type: ignore[attr-defined]
