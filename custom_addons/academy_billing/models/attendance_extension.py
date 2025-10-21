from __future__ import annotations

from odoo import api, fields, models


class AcademyAttendanceBillingExtension(models.Model):
    """Extend attendance records with billing linkage."""

    _inherit = 'academy.attendance'  # type: ignore[assignment]

    billing_item_id = fields.Many2one(
        'academy.billing.item',
        string='Billing Item',
        readonly=True,
        copy=False,
        help='Link to billing item created for this attendance'
    )
    is_billed = fields.Boolean(
        string='Billed',
        compute='_compute_is_billed',
        store=True,
        help='True if billing item has been created'
    )

    @api.depends('billing_item_id')
    def _compute_is_billed(self):
        for record in self:
            record.is_billed = bool(record.billing_item_id)
