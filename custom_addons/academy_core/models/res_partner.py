from odoo import fields, models


class ResPartner(models.Model):
    _inherit = ['res.partner']

    academy_is_guardian = fields.Boolean(string='Academy Guardian')
    academy_is_player = fields.Boolean(string='Academy Player')
    mobile = fields.Char(string='Mobile')
    academy_guardian_child_ids = fields.Many2many(
        'academy.player',
        'academy_player_guardian_rel',
        'guardian_id',
        'player_id',
        string='Academy Children',
        readonly=True,
    )
    academy_primary_player_ids = fields.One2many(
        'academy.player',
        'primary_guardian_id',
        string='Primary Player Relationships',
        readonly=True,
    )
