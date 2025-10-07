from odoo import http, fields
from odoo.http import request


class AcademyPortal(http.Controller):
    @http.route(['/my/practice'], type='http', auth='user', website=True)
    def portal_my_practice(self, **kwargs):
        """Show guardian's children and their upcoming occurrences.

        Renders a simple listing grouped by child. Uses future occurrences (date >= today).
        """
        partner = request.env.user.partner_id
        # canonical guardian-child relation
        players = partner.academy_guardian_child_ids.sudo() or partner.academy_primary_player_ids.sudo()
        players = players.sorted(key=lambda p: p.name)

        Occ = request.env['academy.session.occurrence'].sudo()
        today = fields.Date.today()
        occurrences_by_player = {}
        for p in players:
            # occurrences either for the player's skill group (group sessions) or individual sessions where player is assigned
            # domain: date >= today AND (skill_group = player.skill_group OR player is in player_ids)
            domain = ['&', ('date', '>=', today), '|', ('skill_group_id', '=', p.skill_group_id.id), ('player_ids', 'in', p.id)]
            occs = Occ.search(domain, order='date, start_datetime')
            occurrences_by_player[p.id] = occs

        values = {
            'partner': partner,
            'players': players,
            'occurrences_by_player': occurrences_by_player,
        }
        return request.render('academy_core.portal_my_practice', values)

    @http.route(['/my/practice/report_absence'], type='http', auth='user', methods=['POST'], website=True)
    def portal_report_absence(self, occurrence_id=None, player_id=None, reason_note=None, **kwargs):
        """Create a simple absence record for a guardian's child and redirect back to practice page."""
        partner = request.env.user.partner_id
        if not occurrence_id or not player_id:
            return request.redirect('/my/practice')

        player = request.env['academy.player'].sudo().browse(int(player_id))
        # ensure guardian relation
        if partner.id not in player.guardian_ids.ids and partner.id != (player.primary_guardian_id.id if player.primary_guardian_id else None):
            return request.redirect('/my/practice')

        Occ = request.env['academy.session.occurrence'].sudo().browse(int(occurrence_id))
        # disallow past occurrences
        try:
            occ_date = fields.Date.to_date(Occ.date)
        except Exception:
            occ_date = None
        if occ_date and occ_date < fields.Date.today():
            return request.redirect('/my/practice')

        Abs = request.env['academy.session.absence'].sudo()
        absence_vals = {
            'occurrence_id': Occ.id,
            'player_id': player.id,
            'reason_code': 'reported',
            'reason_note': reason_note or '',
        }
        try:
            Abs.create(absence_vals)
        except Exception:
            # swallow errors to keep portal UX simple
            pass

        return request.redirect('/my/practice')
