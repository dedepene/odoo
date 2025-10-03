from odoo import api, fields, models
from odoo.fields import Command
from odoo.osv import expression
from odoo.tools.safe_eval import safe_eval


class _EvalModel:
    """Callable proxy returning recordsets when invoked with IDs."""

    def __init__(self, recordset):
        self._recordset = recordset

    def __call__(self, *ids):
        flat_ids = []
        for value in ids:
            if isinstance(value, (list, tuple, set)):
                flat_ids.extend(value)
            elif value is not None:
                flat_ids.append(value)
        return self._recordset.browse(flat_ids)

    def __getattr__(self, attr):
        return getattr(self._recordset, attr)


class _EvalNamespace:
    """Lazy namespace to resolve ``res.model`` access during safe_eval."""

    def __init__(self, env, prefix: str = ""):
        self._env = env
        self._prefix = prefix

    def __getattr__(self, item: str):
        model = item if not self._prefix else f"{self._prefix}.{item}"
        return _EvalModel(self._env[model])


COACH_CATEGORY_SELECTION = [
    ('head', 'Head Coach'),
    ('senior', 'Senior Coach'),
    ('associate', 'Associate Coach'),
    ('visiting', 'Visiting Coach'),
]


class ResUsers(models.Model):
    _inherit = ['res.users']

    academy_is_coach = fields.Boolean(
        string='Academy Coach',
        compute='_compute_academy_is_coach',
        inverse='_inverse_academy_is_coach',
        search='_search_academy_is_coach',
        readonly=False,
    )
    academy_coach_category = fields.Selection(
        selection=COACH_CATEGORY_SELECTION,  # type: ignore[arg-type]
        string='Coach Category',
    )

    @api.depends('group_ids')
    def _compute_academy_is_coach(self):
        """Automatically set academy_is_coach based on security groups."""
        coach_group = self.env.ref('academy_core.group_academy_coach', raise_if_not_found=False)
        head_coach_group = self.env.ref('academy_core.group_academy_head_coach', raise_if_not_found=False)
        
        for user in self:
            # User is a coach if they're in either the coach or head coach group
            groups = user.group_ids  # type: ignore[attr-defined]
            user.academy_is_coach = bool(
                (coach_group and coach_group in groups) or
                (head_coach_group and head_coach_group in groups)
            )

    def _inverse_academy_is_coach(self):
        """Keep security groups aligned with the boolean flag."""
        coach_group = self.env.ref('academy_core.group_academy_coach', raise_if_not_found=False)
        head_coach_group = self.env.ref('academy_core.group_academy_head_coach', raise_if_not_found=False)

        if not coach_group:
            return

        for user in self:
            commands = []
            groups = user.group_ids  # type: ignore[attr-defined]
            if user.academy_is_coach:
                if coach_group not in groups:
                    commands.append(Command.link(coach_group.id))  # type: ignore[arg-type]
            else:
                if coach_group in groups:
                    commands.append(Command.unlink(coach_group.id))  # type: ignore[arg-type]
                if head_coach_group and head_coach_group in groups:
                    commands.append(Command.unlink(head_coach_group.id))  # type: ignore[arg-type]

            if commands:
                user.write({'group_ids': commands})

    def _search_academy_is_coach(self, operator, value):
        coach_group = self.env.ref('academy_core.group_academy_coach', raise_if_not_found=False)
        head_coach_group = self.env.ref('academy_core.group_academy_head_coach', raise_if_not_found=False)
        group_ids = [group.id for group in (coach_group, head_coach_group) if group]

        supported_operators = ('=', '!=', 'in', 'not in')
        if operator not in supported_operators:
            raise ValueError('Unsupported operator for academy_is_coach search: %s' % operator)

        positive_domain = [('group_ids', 'in', group_ids)] if group_ids else None
        negative_domain = [('group_ids', 'not in', group_ids)] if group_ids else None

        if operator in ('=', '!='):
            desired = bool(value)
            positive_lookup = (operator == '=' and desired) or (operator == '!=' and not desired)
        else:
            values = value
            if not isinstance(values, (list, tuple, set)):
                values = [values]

            bool_values = [bool(val) for val in values]
            has_true = any(bool_values)
            has_false = any(not val for val in bool_values)

            if operator == 'in':
                if not values:
                    return expression.FALSE_DOMAIN
                if has_true and has_false:
                    return expression.TRUE_DOMAIN
                positive_lookup = has_true
            else:  # operator == 'not in'
                if not values:
                    return expression.TRUE_DOMAIN
                if has_true and has_false:
                    return expression.FALSE_DOMAIN
                positive_lookup = not has_true

        if positive_lookup:
            if positive_domain is None:
                return expression.FALSE_DOMAIN
            return positive_domain

        if negative_domain is None:
            return expression.TRUE_DOMAIN
        return negative_domain

    def init(self):
        super().init()
        self._ensure_academy_coach_action_defaults()

    def _ensure_academy_coach_action_defaults(self):
        action = self.env.ref('academy_core.action_academy_coach', raise_if_not_found=False)
        if not action:
            return

        base_group = self.env.ref('base.group_user', raise_if_not_found=False)
        coach_group = self.env.ref('academy_core.group_academy_coach', raise_if_not_found=False)
        desired_groups = [group.id for group in (base_group, coach_group) if group]
        if not desired_groups:
            return

        eval_namespace = {
            'ref': self.env.ref,
            'res': _EvalNamespace(self.env, 'res'),
        }
        context = safe_eval(action.context or '{}', eval_namespace)  # type: ignore[attr-defined]
        existing_command = context.get('default_group_ids') or context.get('default_groups_id')
        needs_update = True
        if isinstance(existing_command, list) and existing_command:
            op, _, current_ids = existing_command[0]
            normalized_ids = []
            has_non_integer_ids = False
            for group in current_ids or []:
                if hasattr(group, 'id'):
                    normalized_ids.append(group.id)
                    has_non_integer_ids = True
                else:
                    normalized_ids.append(group)
                    if not isinstance(group, int):
                        has_non_integer_ids = True
            if op == 6 and set(desired_groups).issubset(set(normalized_ids)) and not has_non_integer_ids:
                needs_update = False

        if needs_update:
            commands = [(6, 0, desired_groups)]
            context['default_group_ids'] = commands
            context['default_groups_id'] = commands
            action.write({'context': repr(context)})  # type: ignore[attr-defined]

