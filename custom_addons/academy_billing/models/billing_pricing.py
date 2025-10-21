from __future__ import annotations

from typing import Dict

from odoo import fields, models


class AcademyBillingPricingMixin(models.AbstractModel):
    """Helper methods centralising price lookups for academy billing."""

    _name = 'academy.billing.pricing.mixin'
    _description = 'Academy Billing Pricing Helper'

    _CONFIG_KEY_BY_SESSION_TYPE: Dict[str, str] = {
        'tennis_group': 'academy.billing.group_tennis_price',
        'physical_group': 'academy.billing.group_physical_price',
        'tennis_individual': 'academy.billing.individual_tennis_price',
        'physical_individual': 'academy.billing.individual_physical_price',
    }

    _SESSION_TYPE_LABELS: Dict[str, str] = {
        'tennis_group': 'Tennis Skills (Group)',
        'physical_group': 'Physical Activities (Group)',
        'tennis_individual': 'Tennis Skills (Individual)',
        'physical_individual': 'Physical Activities (Individual)',
    }

    def _get_session_pricing(self, session) -> float:
        """Return configured price for the provided session occurrence/template."""
        session_type = session.session_type if session else False
        if not session_type:
            return 0.0

        config_key = self._CONFIG_KEY_BY_SESSION_TYPE.get(session_type)
        config = self.env['ir.config_parameter'].sudo()
        if config_key:
            value = config.get_param(config_key)  # type: ignore[attr-defined]
            if value:
                try:
                    return float(value)
                except (TypeError, ValueError):
                    return 0.0
        return 0.0

    def _get_walkin_pricing(self, attendance) -> float:
        """Adjust price for walk-in scenarios."""
        if not attendance:
            return 0.0
        if attendance.walkin_reason == 'trial':
            return 0.0
        return self._get_session_pricing(attendance.session_id)

    def _get_session_type_label(self, session_type: str) -> str:
        """Return a human readable label for the provided session type."""
        return self._SESSION_TYPE_LABELS.get(session_type, session_type or 'Session')

    def _format_month_label(self, period_start: fields.Date) -> str:
        """Return formatted month label e.g. 'November 2025'."""
        if not period_start:
            return ''
        converted = fields.Date.to_date(period_start)
        if not converted:
            return ''
        return converted.strftime('%B %Y')
