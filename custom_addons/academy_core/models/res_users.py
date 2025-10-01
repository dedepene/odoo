from odoo import fields, models


COACH_CATEGORY_SELECTION = [
    ('head', 'Head Coach'),
    ('senior', 'Senior Coach'),
    ('associate', 'Associate Coach'),
    ('visiting', 'Visiting Coach'),
]


class ResUsers(models.Model):
    _inherit = ['res.users']

    academy_is_coach = fields.Boolean(string='Academy Coach')
    academy_coach_category = fields.Selection(
        selection=COACH_CATEGORY_SELECTION,  # type: ignore[arg-type]
        string='Coach Category',
    )
