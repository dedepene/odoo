from __future__ import annotations

from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class AcademyBillingItem(models.Model):
    """General billing item supporting attendance and ad-hoc charges."""

    _name = 'academy.billing.item'
    _description = 'Academy Billing Item'
    _order = 'charge_date desc, player_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reference', compute='_compute_name', store=True)

    origin_type = fields.Selection([
        ('attendance', 'Attendance'),
        ('extra', 'Ad-Hoc Extra'),
        ('consumable', 'Consumable Purchase'),
    ], string='Origin', default='attendance', required=True, tracking=True, index=True)  # type: ignore[arg-type]

    guardian_id = fields.Many2one(
        'res.partner',
        string='Guardian',
        required=True,
        tracking=True,
        index=True,
        help='Contact that will be invoiced for this charge.'
    )
    player_id = fields.Many2one(
        'academy.player',
        string='Player',
        tracking=True,
        index=True,
        help='Player related to the charge (optional for ad-hoc items).'
    )
    session_id = fields.Many2one(
        'academy.session.occurrence',
        string='Session',
        ondelete='set null',
        tracking=True,
        index=True
    )
    attendance_id = fields.Many2one(
        'academy.attendance',
        string='Attendance',
        ondelete='set null',
        help='Attendance record that generated this billing item.',
        index=True
    )

    session_date = fields.Date(
        string='Session Date',
        compute='_compute_session_date',
        store=True,
        help='Automatically mirrors the session date for attendance charges.'
    )
    charge_date = fields.Date(
        string='Charge Date',
        required=True,
        tracking=True,
        default=lambda self: fields.Date.context_today(self)
    )
    session_type = fields.Selection(
        string='Session Type',
        related='session_id.session_type',
        store=True,
        readonly=True
    )

    description = fields.Char(string='Description')

    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        tracking=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )

    is_walkin = fields.Boolean(
        string='Walk-In',
        related='attendance_id.is_walkin',
        store=True,
        readonly=True,
        help='Flagged for admin review - may need special pricing.'
    )
    walkin_reason = fields.Selection(
        string='Walk-In Reason',
        related='attendance_id.walkin_reason',
        store=True,
        readonly=True
    )

    state = fields.Selection([
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('invoiced', 'Invoiced'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='pending', required=True, tracking=True, index=True)  # type: ignore[arg-type]

    invoice_line_id = fields.Many2one(
        'account.move.line',
        string='Invoice Line',
        readonly=True,
        copy=False
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        related='invoice_line_id.move_id',
        store=True,
        readonly=True
    )

    created_by_cron = fields.Boolean(
        string='Auto-Generated',
        default=False,
        help='Created automatically from attendance billing cron.'
    )
    notes = fields.Text(string='Notes')

    is_billed = fields.Boolean(
        string='Billed',
        compute='_compute_is_billed',
        store=True
    )

    _sql_constraints = [
        (
            'unique_attendance_billing',
            'UNIQUE(attendance_id)',
            'A billing item already exists for this attendance record.'
        ),
        (
            'amount_positive',
            'CHECK(amount >= 0)',
            'Amount must be positive or zero.'
        ),
    ]

    @api.depends('session_id')
    def _compute_session_date(self):
        for record in self:
            record.session_date = record.session_id.date if record.session_id else False  # type: ignore[attr-defined]

    @api.depends('origin_type', 'guardian_id', 'player_id', 'session_date', 'description', 'amount')
    def _compute_name(self):
        for record in self:
            if not record.guardian_id:
                record.name = 'New Billing Item'
                continue

            if record.origin_type == 'attendance':
                player_name = record.player_id.name if record.player_id else 'Player'  # type: ignore[attr-defined]
                date_str = record.session_date.strftime('%Y-%m-%d') if record.session_date else 'N/A'
                walkin_flag = ' 🚶' if record.is_walkin else ''
                record.name = (
                    f"{player_name} - {date_str} - ${record.amount:.2f}{walkin_flag}"
                )
            else:
                label = 'Ad-Hoc'
                if record.origin_type == 'extra':
                    label = 'Extra'
                elif record.origin_type == 'consumable':
                    label = 'Consumable'
                date_str = record.charge_date.strftime('%Y-%m-%d') if record.charge_date else 'N/A'
                description = record.description or 'Charge'
                record.name = f"{label}: {description} ({date_str})"

    @api.depends('invoice_line_id')
    def _compute_is_billed(self):
        for record in self:
            record.is_billed = bool(record.invoice_line_id)

    @api.constrains('origin_type', 'guardian_id', 'player_id', 'attendance_id', 'session_id', 'description')
    def _check_required_fields(self):
        for record in self:
            if record.origin_type == 'attendance':
                missing = []
                if not record.player_id:
                    missing.append('player')
                if not record.attendance_id:
                    missing.append('attendance')
                if not record.session_id:
                    missing.append('session')
                if missing:
                    raise ValidationError(
                        'Attendance billing items require linked %s.' % ', '.join(missing)
                    )
            else:
                if not record.description:
                    raise ValidationError('Ad-hoc billing items require a description.')

    def action_approve(self):
        for record in self:
            if record.state == 'pending':
                record.write({'state': 'approved'})
                record.message_post(body='Billing item approved for invoicing')  # type: ignore[attr-defined]
        return True

    def action_cancel(self):
        for record in self:
            if record.state in ['pending', 'approved']:
                if record.invoice_line_id:
                    raise UserError('Cannot cancel an invoiced item. Reverse the invoice instead.')
                record.write({'state': 'cancelled'})
                record.message_post(body='Billing item cancelled')  # type: ignore[attr-defined]
        return True

    def unlink(self):
        for record in self:
            if record.invoice_line_id:
                raise UserError(
                    'Cannot delete billing item %s because it has been invoiced.' % record.display_name
                )
        return super().unlink()

    def mark_ready(self):
        """Helper to mark items approved."""
        for record in self:
            if record.state == 'pending':
                record.action_approve()
        return True
