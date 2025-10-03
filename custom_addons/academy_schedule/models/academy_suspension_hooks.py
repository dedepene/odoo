"""Additional hooks and safeguards for season suspensions."""

from odoo import api, models


class AcademySeasonSuspension(models.Model):
    _inherit = ['academy.season.suspension']

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)

        apply_existing = self.env.context.get('suspension_apply_existing')
        if apply_existing is None:
            apply_existing = True

        warn_on_empty = self.env.context.get('suspension_warn_empty', True)

        for suspension in records.filtered('active'):
            if apply_existing:
                match_count = suspension._count_matching_occurrences()
                suspension.apply_window(include_existing=True)  # type: ignore[attr-defined]
                if warn_on_empty and not match_count:
                    suspension._log_empty_match_warning()  # type: ignore[attr-defined]
            else:
                suspension._ensure_season_state()  # type: ignore[attr-defined]

        return records

    def _count_matching_occurrences(self):
        """Return the number of planned occurrences affected by this window."""
        self.ensure_one()
        Occurrence = self.env['academy.session.occurrence']
        domain = list(self._build_occurrence_domain(future_only=True))  # type: ignore[attr-defined]
        domain.append(('state', '=', 'planned'))
        return Occurrence.search_count(domain)

    def _log_empty_match_warning(self):
        """Notify the season when a suspension captures no occurrences."""
        for suspension in self:
            season = suspension.season_id  # type: ignore[attr-defined]
            if not season:
                continue
            body = (
                f"Suspension window from {suspension.start_date} to {suspension.end_date} "  # type: ignore[attr-defined]
                "did not match any planned sessions. "
                "Verify the season assignment for those sessions or generate occurrences first."
            )
            season.message_post(body=body, subtype_xmlid='mail.mt_note')  # type: ignore[attr-defined]

