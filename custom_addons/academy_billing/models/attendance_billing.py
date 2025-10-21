from __future__ import annotations

import logging
from datetime import timedelta

from odoo import api, fields, models

_logger = logging.getLogger(__name__)


class AcademyAttendanceBilling(models.Model):
    """Billing processor for attendance records."""

    _name = 'academy.attendance.billing'
    _description = 'Attendance Billing Processor'
    _inherit = ['academy.billing.pricing.mixin']

    @api.model
    def generate_billing_items(self, date_from=None, date_to=None):
        """Generate billing items for confirmed attendance records."""
        if not date_from:
            date_from = fields.Date.today().replace(day=1)
        if not date_to:
            date_to = fields.Date.today()

        domain = [
            ('session_date', '>=', date_from),
            ('session_date', '<=', date_to),
            ('billing_item_id', '=', False),
            ('session_id.attendance_status', '=', 'confirmed'),
        ]
        attendances = self.env['academy.attendance'].search(domain)

        billing_items_created = []
        errors = []

        for attendance in attendances:
            try:
                if attendance.is_walkin:  # type: ignore[attr-defined]
                    amount = self._get_walkin_pricing(attendance)  # type: ignore[attr-defined]
                else:
                    amount = self._get_session_pricing(attendance.session_id)  # type: ignore[attr-defined]

                guardian = attendance.player_id.primary_guardian_id  # type: ignore[attr-defined]
                if not guardian:
                    errors.append({
                        'attendance_id': str(attendance.id),
                        'player': attendance.player_id.name,  # type: ignore[attr-defined]
                        'error': 'No primary guardian set',
                    })
                    continue

                billing_item = self.env['academy.billing.item'].create({
                    'player_id': attendance.player_id.id,  # type: ignore[attr-defined]
                    'session_id': attendance.session_id.id,  # type: ignore[attr-defined]
                    'attendance_id': attendance.id,
                    'amount': amount,
                    'guardian_id': guardian.id,
                    'origin_type': 'attendance',
                    'charge_date': attendance.session_date,  # type: ignore[attr-defined]
                    'description': attendance.session_id.name,  # type: ignore[attr-defined]
                    'state': 'pending',
                    'created_by_cron': True,
                    'notes': f"Auto-generated from attendance confirmation on {fields.Date.today()}",
                })

                attendance.write({'billing_item_id': billing_item.id})
                billing_items_created.append(billing_item.id)

            except Exception as exc:  # pylint: disable=broad-except
                errors.append({
                    'attendance_id': str(attendance.id),
                    'player': attendance.player_id.name,  # type: ignore[attr-defined]
                    'error': str(exc),
                })

        summary = {
            'date_from': date_from,
            'date_to': date_to,
            'billing_items_created': len(billing_items_created),
            'attendances_processed': len(attendances),
            'errors': len(errors),
            'error_details': errors,
        }

        _logger.info(
            "Attendance billing: Created %s billing items from %s attendance records. Errors: %s",
            summary['billing_items_created'],
            summary['attendances_processed'],
            summary['errors'],
        )

        return summary

    @api.model
    def cron_generate_monthly_billing(self):
        """Cron job to generate billing items for the previous month."""
        today = fields.Date.today()
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)

        summary = self.generate_billing_items(
            date_from=last_month_start,
            date_to=last_month_end,
        )

        if summary['errors'] > 0:
            admin_group = self.env.ref('academy_core.group_academy_manager', raise_if_not_found=False)
            if admin_group:
                for admin in admin_group.users:  # type: ignore[attr-defined]
                    self.env['mail.mail'].create({
                        'subject': f"Attendance Billing Errors - {last_month_start.strftime('%B %Y')}",
                        'body_html': """
                            <p>The monthly billing cron encountered {errors} errors:</p>
                            <ul>
                                {items}
                            </ul>
                            <p>Please review the attendance records and billing items.</p>
                        """.format(
                            errors=summary['errors'],
                            items=''.join(
                                f"<li>{detail['player']}: {detail['error']}</li>"
                                for detail in summary['error_details'][:10]
                            ),
                        ),
                        'email_to': admin.email,
                    })

        return summary
