from __future__ import annotations

from odoo import fields, models


class AcademySessionTemplate(models.Model):
    _inherit = ['academy.session.template']

    billing_template_id = fields.Many2one(
        'academy.billing.template',
        string='Billing Template',
        required=True,
        tracking=True,
        default=lambda self: self.env['academy.billing.template']._get_default_template_id(),
    )
