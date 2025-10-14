from odoo import http, fields
from odoo.http import request
from odoo.addons.portal.controllers.portal import CustomerPortal, pager as portal_pager


class AcademyPortal(CustomerPortal):
    """Guardian portal controller with enhanced features."""

    def _get_absences_for_sessions(self, player_id, occurrence_ids):
        """Get existing absences for given player and occurrences.
        
        Returns dict mapping occurrence_id to absence record (or False).
        Only returns active absences (reported or acknowledged).
        """
        if not occurrence_ids:
            return {}
        
        Abs = request.env['academy.session.absence'].sudo()
        absences = Abs.search([
            ('player_id', '=', player_id),
            ('occurrence_id', 'in', occurrence_ids),
            ('state', 'in', ['reported', 'acknowledged'])
        ])
        
        # Create mapping: occurrence_id -> absence record
        absence_map = {abs.occurrence_id.id: abs for abs in absences}
        return absence_map

    def _prepare_home_portal_values(self, counters):
        """Override to add academy-specific counts to portal home."""
        values = super()._prepare_home_portal_values(counters)
        partner = request.env.user.partner_id
        
        # Get guardian's children
        players = partner.academy_guardian_child_ids.sudo() or partner.academy_primary_player_ids.sudo()
        
        if 'session_count' in counters:
            # Count upcoming sessions
            Occ = request.env['academy.session.occurrence'].sudo()
            today = fields.Date.today()
            session_count = 0
            for p in players:
                domain = ['&', ('date', '>=', today), ('state', '=', 'planned'), 
                         '|', ('skill_group_id', '=', p.skill_group_id.id), 
                         ('player_ids', 'in', p.id)]
                session_count += Occ.search_count(domain)
            values['session_count'] = session_count
        
        if 'child_count' in counters:
            values['child_count'] = len(players)
        
        return values

    @http.route(['/my', '/my/home'], type='http', auth='user', website=True)
    def home(self, **kwargs):
        """Guardian portal home - Dashboard view."""
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        
        # Get guardian's children
        players = partner.academy_guardian_child_ids.sudo() or partner.academy_primary_player_ids.sudo()
        players = players.sorted(key=lambda p: p.name)
        
        # Get next 5 upcoming sessions across all children
        Occ = request.env['academy.session.occurrence'].sudo()
        today = fields.Date.today()
        upcoming_sessions = []
        for p in players:
            domain = ['&', ('date', '>=', today), ('state', '=', 'planned'),
                     '|', ('skill_group_id', '=', p.skill_group_id.id), 
                     ('player_ids', 'in', p.id)]
            occs = Occ.search(domain, order='date, start_datetime', limit=5)
            for occ in occs:
                upcoming_sessions.append({'player': p, 'occurrence': occ})
        
        # Sort by date and limit to 5
        upcoming_sessions = sorted(upcoming_sessions, 
                                  key=lambda x: x['occurrence'].start_datetime)[:5]
        
        # Get absences for these sessions
        absences_by_occurrence = {}
        for session in upcoming_sessions:
            player_id = session['player'].id
            occ_id = session['occurrence'].id
            absence_map = self._get_absences_for_sessions(player_id, [occ_id])
            if occ_id in absence_map:
                absences_by_occurrence[occ_id] = absence_map[occ_id]
        
        values.update({
            'players': players,
            'upcoming_sessions': upcoming_sessions,
            'absences_by_occurrence': absences_by_occurrence,
            'page_name': 'home',
        })
        return request.render('academy_core.portal_guardian_home', values)

    @http.route(['/my/kids'], type='http', auth='user', website=True)
    def portal_my_kids(self, **kwargs):
        """List all children linked to guardian."""
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        
        # Get guardian's children with detailed info
        players = partner.academy_guardian_child_ids.sudo() or partner.academy_primary_player_ids.sudo()
        players = players.sorted(key=lambda p: p.name)
        
        values.update({
            'players': players,
            'page_name': 'kids',
        })
        return request.render('academy_core.portal_my_kids', values)

    @http.route(['/my/kids/<int:player_id>'], type='http', auth='user', website=True)
    def portal_kid_detail(self, player_id, **kwargs):
        """Show detailed information about a specific child."""
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        
        # Validate guardian can access this player
        player = request.env['academy.player'].sudo().browse(player_id)
        if not player.exists():
            return request.redirect('/my/kids')
        
        # Check guardian relationship
        if partner.id not in player.guardian_ids.ids and partner.id != (player.primary_guardian_id.id if player.primary_guardian_id else None):
            return request.redirect('/my/kids')
        
        # Get upcoming and recent past sessions
        Occ = request.env['academy.session.occurrence'].sudo()
        today = fields.Date.today()
        
        # Upcoming sessions
        upcoming_domain = ['&', ('date', '>=', today), ('state', '=', 'planned'),
                          '|', ('skill_group_id', '=', player.skill_group_id.id), 
                          ('player_ids', 'in', player.id)]
        upcoming_sessions = Occ.search(upcoming_domain, order='date, start_datetime', limit=10)
        
        # Past sessions (last 10)
        past_domain = ['&', ('date', '<', today),
                      '|', ('skill_group_id', '=', player.skill_group_id.id), 
                      ('player_ids', 'in', player.id)]
        past_sessions = Occ.search(past_domain, order='date desc, start_datetime desc', limit=10)
        
        # Get absences for upcoming sessions
        occurrence_ids = upcoming_sessions.ids
        absences_map = self._get_absences_for_sessions(player.id, occurrence_ids)
        
        values.update({
            'player': player,
            'upcoming_sessions': upcoming_sessions,
            'past_sessions': past_sessions,
            'absences_map': absences_map,
            'page_name': 'kids',
        })
        return request.render('academy_core.portal_kid_detail', values)

    @http.route(['/my/sessions'], type='http', auth='user', website=True)
    def portal_my_sessions(self, **kwargs):
        """Show all upcoming and past sessions for all children."""
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        
        # Get guardian's children
        players = partner.academy_guardian_child_ids.sudo() or partner.academy_primary_player_ids.sudo()
        players = players.sorted(key=lambda p: p.name)
        
        Occ = request.env['academy.session.occurrence'].sudo()
        today = fields.Date.today()
        
        # Build sessions by player
        upcoming_by_player = {}
        past_by_player = {}
        absences_by_player = {}
        
        for p in players:
            # Upcoming sessions
            upcoming_domain = ['&', ('date', '>=', today), ('state', '=', 'planned'),
                              '|', ('skill_group_id', '=', p.skill_group_id.id), 
                              ('player_ids', 'in', p.id)]
            upcoming_sessions = Occ.search(upcoming_domain, order='date, start_datetime')
            upcoming_by_player[p.id] = upcoming_sessions
            
            # Get absences for this player's upcoming sessions
            absences_by_player[p.id] = self._get_absences_for_sessions(p.id, upcoming_sessions.ids)
            
            # Past sessions
            past_domain = ['&', ('date', '<', today),
                          '|', ('skill_group_id', '=', p.skill_group_id.id), 
                          ('player_ids', 'in', p.id)]
            past_by_player[p.id] = Occ.search(past_domain, order='date desc, start_datetime desc', limit=20)
        
        values.update({
            'players': players,
            'upcoming_by_player': upcoming_by_player,
            'past_by_player': past_by_player,
            'absences_by_player': absences_by_player,
            'page_name': 'sessions',
        })
        return request.render('academy_core.portal_my_sessions', values)

    @http.route(['/my/billing'], type='http', auth='user', website=True)
    def portal_my_billing(self, **kwargs):
        """Show billing information for guardian."""
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        
        # Get invoices for the guardian (partner)
        Invoice = request.env['account.move'].sudo()
        invoices = Invoice.search([
            ('partner_id', '=', partner.id),
            ('move_type', 'in', ['out_invoice', 'out_refund']),
            ('state', '!=', 'cancel')
        ], order='invoice_date desc, id desc')
        
        # Split into current (unpaid) and paid
        current_invoices = invoices.filtered(lambda inv: inv.payment_state in ['not_paid', 'partial'])
        paid_invoices = invoices.filtered(lambda inv: inv.payment_state in ['paid', 'in_payment'])
        
        values.update({
            'current_invoices': current_invoices,
            'paid_invoices': paid_invoices,
            'page_name': 'billing',
        })
        return request.render('academy_core.portal_my_billing', values)

    @http.route(['/my/profile'], type='http', auth='user', website=True)
    def portal_my_profile(self, **kwargs):
        """Show and allow editing of guardian profile."""
        values = self._prepare_portal_layout_values()
        partner = request.env.user.partner_id
        
        # Get guardian's children for reference
        players = partner.academy_guardian_child_ids.sudo() or partner.academy_primary_player_ids.sudo()
        
        values.update({
            'partner': partner,
            'players': players,
            'page_name': 'profile',
        })
        return request.render('academy_core.portal_my_profile', values)

    @http.route(['/my/profile/update'], type='http', auth='user', methods=['POST'], website=True)
    def portal_profile_update(self, **kwargs):
        """Update guardian profile information."""
        partner = request.env.user.partner_id.sudo()
        
        # Update allowed fields
        update_vals = {}
        if kwargs.get('name'):
            update_vals['name'] = kwargs['name']
        if kwargs.get('email'):
            update_vals['email'] = kwargs['email']
        if kwargs.get('phone'):
            update_vals['phone'] = kwargs['phone']
        if kwargs.get('mobile'):
            update_vals['mobile'] = kwargs['mobile']
        if kwargs.get('street'):
            update_vals['street'] = kwargs['street']
        if kwargs.get('street2'):
            update_vals['street2'] = kwargs['street2']
        if kwargs.get('city'):
            update_vals['city'] = kwargs['city']
        if kwargs.get('zip'):
            update_vals['zip'] = kwargs['zip']
        
        if update_vals:
            partner.write(update_vals)
        
        return request.redirect('/my/profile?success=1')

    @http.route(['/my/sessions/report_absence'], type='http', auth='user', methods=['POST'], website=True, csrf=True)
    def portal_report_absence(self, occurrence_id=None, player_id=None, reason_code=None, reason_note=None, **kwargs):
        """Create absence record for a guardian's child."""
        partner = request.env.user.partner_id
        if not occurrence_id or not player_id:
            return request.redirect('/my/sessions')

        player = request.env['academy.player'].sudo().browse(int(player_id))
        # Ensure guardian relation
        if partner.id not in player.guardian_ids.ids and partner.id != (player.primary_guardian_id.id if player.primary_guardian_id else None):
            return request.redirect('/my/sessions')

        Occ = request.env['academy.session.occurrence'].sudo().browse(int(occurrence_id))
        # Disallow past occurrences
        try:
            occ_date = fields.Date.to_date(Occ.date)
        except Exception:
            occ_date = None
        if occ_date and occ_date < fields.Date.today():
            return request.redirect('/my/sessions')

        # Create absence with proper reason code
        Abs = request.env['academy.session.absence'].sudo()
        absence_vals = {
            'occurrence_id': Occ.id,
            'player_id': player.id,
            'reason_code': reason_code or 'other',
            'reason_note': reason_note or '',
        }
        try:
            Abs.create(absence_vals)
        except Exception as e:
            # Log error but keep UX simple
            pass

        # Redirect back with success message
        redirect_url = kwargs.get('redirect', '/my/sessions')
        return request.redirect(redirect_url + '?absence_reported=1')

    @http.route(['/my/sessions/cancel_absence'], type='http', auth='user', methods=['POST'], website=True, csrf=True)
    def portal_cancel_absence(self, absence_id=None, **kwargs):
        """Cancel (delete) an absence record."""
        partner = request.env.user.partner_id
        if not absence_id:
            return request.redirect('/my/sessions')

        # Get the absence and validate guardian can cancel it
        Abs = request.env['academy.session.absence'].sudo()
        absence = Abs.browse(int(absence_id))
        
        if not absence.exists():
            return request.redirect('/my/sessions')
        
        # Validate guardian relationship with the player
        player = absence.player_id
        if partner.id not in player.guardian_ids.ids and partner.id != (player.primary_guardian_id.id if player.primary_guardian_id else None):
            return request.redirect('/my/sessions')
        
        # Only allow canceling if absence is in reported or acknowledged state
        if absence.state in ['reported', 'acknowledged']:
            try:
                absence.unlink()  # Delete the absence record
            except Exception as e:
                # Log error but keep UX simple
                pass
        
        # Redirect back with success message
        redirect_url = kwargs.get('redirect', '/my/sessions')
        return request.redirect(redirect_url + '?absence_cancelled=1')
