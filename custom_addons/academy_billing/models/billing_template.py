from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from calendar import monthrange
from typing import Dict, List, Tuple

from dateutil.relativedelta import relativedelta

from odoo import _, api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools.float_utils import float_compare


class AcademyBillingTemplate(models.Model):
    """Billing template driving pre-paid invoicing rules."""

    _name = 'academy.billing.template'
    _description = 'Academy Billing Template'
    _inherit = ['mail.thread', 'mail.activity.mixin', 'academy.billing.pricing.mixin']

    name = fields.Char(required=True, tracking=True)
    description = fields.Text(tracking=True)
    invoice_generation_day = fields.Integer(default=1, tracking=True)
    payment_due_days = fields.Integer(default=10, tracking=True)
    is_default = fields.Boolean(default=False, tracking=True)
    active = fields.Boolean(default=True, tracking=True)

    session_template_ids = fields.One2many(
        'academy.session.template',
        'billing_template_id',
        string='Session Templates',
    )

    _sql_constraints = [
        ('invoice_day_positive', 'CHECK(invoice_generation_day BETWEEN 1 AND 28)',
         'Invoice generation day must be between 1 and 28.'),
        ('payment_due_positive', 'CHECK(payment_due_days >= 0)',
         'Payment due days must be zero or positive.'),
    ]

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._ensure_default_template()
        return records

    def write(self, vals):
        res = super().write(vals)
        if 'is_default' in vals:
            self._ensure_default_template()
        return res

    def _ensure_default_template(self):
        """Ensure exactly one template is flagged as default."""
        for template in self:
            if template.is_default:
                others = self.search([
                    ('id', '!=', template.id),
                    ('is_default', '=', True),
                ])
                if others:
                    others.write({'is_default': False})
        if not self.search([('is_default', '=', True)]):
            first = self.search([], limit=1)
            if first:
                first.is_default = True

    @api.model
    def _get_default_template_id(self) -> int | None:
        template = self.search([('is_default', '=', True)], limit=1)
        if not template:
            template = self.search([], limit=1)
        return template.id if template else None

    def _get_month_bounds(self, target_date: date) -> Tuple[date, date]:
        """Return the first and last day of the month for target date."""
        if isinstance(target_date, datetime):
            target_date = target_date.date()
        start_day = target_date.replace(day=1)
        last_day = monthrange(start_day.year, start_day.month)[1]
        end_day = start_day.replace(day=last_day)
        return start_day, end_day

    def _prepare_invoice_vals(self, guardian, invoice_lines, invoice_date, due_date, origin, currency):
        return {
            'move_type': 'out_invoice',
            'partner_id': guardian.id,
            'invoice_date': invoice_date,
            'invoice_date_due': due_date,
            'invoice_origin': origin,
            'invoice_line_ids': invoice_lines,
            'currency_id': currency.id,
        }

    def action_view_session_templates(self):
        self.ensure_one()
        return {
            'name': _('Session Templates'),
            'type': 'ir.actions.act_window',
            'res_model': 'academy.session.template',
            'view_mode': 'list,form',
            'domain': [('billing_template_id', '=', self.id)],
            'context': {'default_billing_template_id': self.id},
        }

    @api.model
    def cron_generate_monthly_prepaid_invoices(self):
        """Scheduled job generating pre-paid invoices."""
        context_date = self.env.context.get('force_date')
        if context_date:
            if isinstance(context_date, str):
                target_date = fields.Date.from_string(context_date)
            else:
                target_date = context_date
        else:
            target_date = fields.Date.context_today(self)
        if isinstance(target_date, datetime):
            target_date = target_date.date()
        if isinstance(target_date, str):
            target_date = fields.Date.from_string(target_date)

        day = target_date.day
        templates = self.search([
            ('invoice_generation_day', '=', day),
            ('active', '=', True),
        ])
        summary = []
        for template in templates:
            summary.append(template._generate_prepaid_invoices_for_month(target_date))
        return summary

    def _generate_prepaid_invoices_for_month(self, target_date):
        self.ensure_one()
        period_start, period_end = self._get_month_bounds(target_date)
        month_label = period_start.strftime('%B %Y')
        occurrence_model = self.env['academy.session.occurrence']
        billing_item_model = self.env['academy.billing.item']

        domain = [
            ('template_id', 'in', self.session_template_ids.ids),
            ('date', '>=', period_start),
            ('date', '<=', period_end),
            ('state', '!=', 'cancelled'),
        ]
        occurrences = occurrence_model.search(domain)

        guardian_bundles: Dict[int, Dict[str, object]] = {}
        missing_guardians: List[str] = []

        for occurrence in occurrences:
            players = occurrence._get_registered_players()
            for player in players:
                guardian = player.primary_guardian_id
                if not guardian:
                    missing_guardians.append(player.display_name or player.name)
                    continue
                bundle = guardian_bundles.setdefault(guardian.id, {
                    'guardian': guardian,
                    'session_lines': defaultdict(lambda: {'count': 0, 'amount': 0.0, 'player': False, 'session_type': False}),
                    'extra_items': billing_item_model.browse(),
                })
                key = (player.id, occurrence.session_type)
                line_data = bundle['session_lines'][key]
                line_data['count'] += 1
                line_data['player'] = player
                line_data['session_type'] = occurrence.session_type
                line_data['amount'] += self._get_session_pricing(occurrence)

        pending_items = billing_item_model.search([
            ('state', '=', 'pending'),
            ('guardian_id', '!=', False),
            ('origin_type', 'in', ['extra', 'consumable']),
        ])
        for item in pending_items:
            guardian = item.guardian_id
            bundle = guardian_bundles.setdefault(guardian.id, {
                'guardian': guardian,
                'session_lines': defaultdict(lambda: {'count': 0, 'amount': 0.0, 'player': False, 'session_type': False}),
                'extra_items': billing_item_model.browse(),
            })
            bundle['extra_items'] |= item

        if not guardian_bundles:
            return {
                'template_id': self.id,
                'period_start': period_start,
                'period_end': period_end,
                'invoices_created': 0,
                'errors': missing_guardians,
            }

        session_product = self.env.ref('academy_billing.product_template_prepaid_session', raise_if_not_found=False)
        if session_product:
            session_product = session_product.product_variant_id
        extra_product = self.env.ref('academy_billing.product_template_ad_hoc_charge', raise_if_not_found=False)
        if extra_product:
            extra_product = extra_product.product_variant_id
        currency = self.env.company.currency_id

        invoice_ids = []
        for bundle in guardian_bundles.values():
            guardian = bundle['guardian']
            session_lines = bundle['session_lines']
            extra_items = bundle['extra_items']

            invoice_origin = f"{self.name} - {month_label}"
            existing = self.env['account.move'].search([
                ('move_type', '=', 'out_invoice'),
                ('partner_id', '=', guardian.id),
                ('invoice_origin', '=', invoice_origin),
                ('state', '!=', 'cancel'),
            ], limit=1)
            if existing:
                continue

            invoice_line_commands = []
            for (player_id, session_type), info in session_lines.items():
                if not info['count'] or float_compare(info['amount'], 0.0, precision_rounding=currency.rounding) <= 0:
                    continue
                player = info['player']
                player_name = player.name if player else _('Player')
                session_label = self._get_session_type_label(session_type)
                description = _(f"{month_label} {player_name} - {session_label} x {info['count']}")
                line_vals = {
                    'name': description,
                    'quantity': 1,
                    'price_unit': info['amount'],
                    'currency_id': currency.id,
                }
                if session_product:
                    line_vals['product_id'] = session_product.id
                invoice_line_commands.append((0, 0, line_vals))

            extra_items_to_update = []
            for item in extra_items:
                if float_compare(item.amount, 0.0, precision_rounding=currency.rounding) <= 0:
                    continue
                line_vals = {
                    'name': item.description or item.name,
                    'quantity': 1,
                    'price_unit': item.amount,
                    'currency_id': currency.id,
                }
                if extra_product:
                    line_vals['product_id'] = extra_product.id
                invoice_line_commands.append((0, 0, line_vals))
                extra_items_to_update.append(item)

            if not invoice_line_commands:
                continue

            invoice_date = period_start
            due_date = invoice_date + relativedelta(days=self.payment_due_days)
            invoice_vals = self._prepare_invoice_vals(
                guardian,
                invoice_line_commands,
                invoice_date,
                due_date,
                invoice_origin,
                currency,
            )
            invoice = self.env['account.move'].with_context(default_move_type='out_invoice').create(invoice_vals)
            invoice.action_post()
            invoice_ids.append(invoice.id)

            # Automatically apply existing credit notes (e.g., from previous month's acknowledged absences)
            # This ensures guardians see invoices with credits already deducted.
            # Note: For this to work, cron_reconcile_monthly_absences() must run BEFORE
            # cron_generate_monthly_prepaid_invoices() so credit notes exist when invoices are created.
            credit_moves = self.env['account.move'].search([
                ('move_type', '=', 'out_refund'),
                ('partner_id', '=', guardian.id),
                ('state', '=', 'posted'),
                ('payment_state', 'in', ['not_paid', 'partial']),
            ])
            for credit in credit_moves:
                outstanding_lines = credit.line_ids.filtered(
                    lambda line: line.account_id == credit.partner_id.property_account_receivable_id
                    and not line.reconciled and line.credit > 0
                )
                for outstanding in outstanding_lines:
                    try:
                        invoice.js_assign_outstanding_line(outstanding.id)
                    except Exception:
                        continue

            # Link extra items to invoice lines
            if extra_items_to_update:
                if extra_product:
                    candidate_lines = invoice.invoice_line_ids.filtered(lambda l: l.product_id.id == extra_product.id and not l.display_type)
                else:
                    candidate_lines = invoice.invoice_line_ids.filtered(lambda l: not l.display_type)
                candidate_lines = candidate_lines.sorted(lambda l: l.id)
                for item, line in zip(extra_items_to_update, candidate_lines):
                    item.write({
                        'state': 'invoiced',
                        'invoice_line_id': line.id,
                        'guardian_id': guardian.id,
                    })

            mail_template = self.env.ref('account.email_template_edi_invoice', raise_if_not_found=False)
            if mail_template:
                try:
                    mail_template.send_mail(invoice.id, force_send=True)
                except Exception:
                    invoice.message_post(body=_('Invoice ready in portal for guardian %s') % guardian.display_name)
            else:
                invoice.message_post(body=_('Invoice ready in portal for guardian %s') % guardian.display_name)

        if missing_guardians:
            message = _(
                'Missing primary guardian for players: %s'
            ) % ', '.join(missing_guardians)
            self.message_post(body=message)

        return {
            'template_id': self.id,
            'period_start': period_start,
            'period_end': period_end,
            'invoices_created': len(invoice_ids),
            'invoice_ids': invoice_ids,
            'errors': missing_guardians,
        }

    @api.model
    def cron_reconcile_monthly_absences(self):
        """Generate credit notes for acknowledged absences."""
        context_date = self.env.context.get('force_date')
        if context_date:
            if isinstance(context_date, str):
                run_date = fields.Date.from_string(context_date)
            else:
                run_date = context_date
        else:
            run_date = fields.Date.context_today(self)
        if isinstance(run_date, datetime):
            run_date = run_date.date()
        if isinstance(run_date, str):
            run_date = fields.Date.from_string(run_date)

        current_first = run_date.replace(day=1)
        previous_month_end = current_first - relativedelta(days=1)
        previous_month_start = previous_month_end.replace(day=1)

        absence_model = self.env['academy.session.absence']
        absences = absence_model.search([
            ('state', '=', 'acknowledged'),
            ('occurrence_id.date', '>=', previous_month_start),
            ('occurrence_id.date', '<=', previous_month_end),
        ])

        session_product = self.env.ref('academy_billing.product_template_prepaid_session', raise_if_not_found=False)
        if session_product:
            session_product = session_product.product_variant_id
        currency = self.env.company.currency_id
        created_credit_ids = []

        helper = self.search([], limit=1)
        helper = helper or self

        for absence in absences:
            player = absence.player_id
            guardian = player.primary_guardian_id
            if not guardian:
                continue
            amount = helper._get_session_pricing(absence.occurrence_id)
            if float_compare(amount, 0.0, precision_rounding=currency.rounding) <= 0:
                continue
            credit_vals = {
                'move_type': 'out_refund',
                'partner_id': guardian.id,
                'invoice_date': previous_month_end,
                'invoice_line_ids': [(0, 0, {
                    'name': _('Credit for acknowledged absence: %s on %s') % (player.name, absence.occurrence_id.date),
                    'quantity': 1,
                    'price_unit': amount,
                    'currency_id': currency.id,
                    'product_id': session_product.id if session_product else False,
                })],
                'currency_id': currency.id,
            }
            credit_move = self.env['account.move'].create(credit_vals)
            credit_move.action_post()
            created_credit_ids.append(credit_move.id)
            absence.mark_as_credited(credit_move, amount)

        return {
            'credit_count': len(created_credit_ids),
            'credit_ids': created_credit_ids,
            'period_start': previous_month_start,
            'period_end': previous_month_end,
        }
