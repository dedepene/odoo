"""Session occurrence model for actual scheduled sessions."""
from datetime import datetime, timedelta
import pytz
from typing import TYPE_CHECKING

from odoo import api, fields, models
from odoo.exceptions import ValidationError, UserError


if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from .academy_season import AcademySeason, AcademySeasonSuspension


class AcademySessionOccurrence(models.Model):
    """Individual session occurrence (generated from template or ad-hoc)."""
    
    _name = 'academy.session.occurrence'
    _description = 'Session Occurrence'
    _order = 'start_datetime desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Session Name', compute='_compute_name', store=True)
    
    # Template link (if generated from template)
    template_id = fields.Many2one('academy.session.template', string='Template',
                                 ondelete='set null')
    season_id = fields.Many2one('academy.season', string='Season', required=True,
                               ondelete='cascade')
    
    # Session details
    date = fields.Date(string='Date', required=True, tracking=True)
    start_datetime = fields.Datetime(string='Start', required=True, tracking=True)
    end_datetime = fields.Datetime(string='End', required=True, tracking=True)
    duration = fields.Float(string='Duration (hours)', compute='_compute_duration',
                          store=True)
    
    session_type = fields.Selection([
        ('tennis_group', 'Tennis Skills (Group)'),
        ('physical_group', 'Physical Activities (Group)'),
        ('tennis_individual', 'Tennis Skills (Individual)'),
        ('physical_individual', 'Physical Activities (Individual)'),
    ], string='Session Type', required=True, tracking=True)
    
    # Participants
    skill_group_id = fields.Many2one('academy.skill.group', string='Skill Group',
                                    help='For group sessions')
    player_ids = fields.Many2many('academy.player', string='Players',
                                 help='For individual sessions or specific attendees')
    
    # Resources
    court_ids = fields.Many2many('academy.court', string='Courts', required=True)
    coach_id = fields.Many2one('res.users', string='Coach')
    
    # State management
    state = fields.Selection([
        ('planned', 'Planned'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ], string='Status', default='planned', tracking=True)
    state_before_suspension = fields.Selection([
        ('planned', 'Planned'),
        ('suspended', 'Suspended'),
        ('cancelled', 'Cancelled'),
        ('completed', 'Completed'),
    ], string='State Before Suspension', copy=False, readonly=True)
    suspension_id = fields.Many2one(
        'academy.season.suspension',
        string='Suspension Window',
        copy=False,
        index=True,
        readonly=True,
    )
    suspension_reason = fields.Char(
        string='Suspension Reason',
        related='suspension_id.reason',
        readonly=True,
        store=False,
    )
    
    # Session characteristics
    is_individual = fields.Boolean(string='Individual Session', default=False,
                                  help='True for ad-hoc individual sessions')
    is_followup = fields.Boolean(string='Is Follow-up', default=False,
                                help='True if this is a chained physical session')
    parent_occurrence_id = fields.Many2one('academy.session.occurrence',
                                          string='Parent Session',
                                          help='Link to base session if follow-up')
    
    # Absence tracking
    absence_ids = fields.One2many('academy.session.absence', 'occurrence_id',
                                 string='Absences')
    absence_count = fields.Integer(string='Absences', compute='_compute_absence_count')
    
    # Attendance tracking
    attendance_ids = fields.One2many('academy.attendance', 'session_id',
                                     string='Attendance')
    attendance_count = fields.Integer(string='Attendance Count', 
                                     compute='_compute_attendance_count',
                                     store=True)
    attendance_status = fields.Selection([
        ('pending', 'Pending Confirmation'),
        ('confirmed', 'Confirmed'),
        ('completed', 'Completed'),
    ], string='Attendance Status', default='pending', tracking=True)
    
    # Session participants (including walk-ins)
    participant_ids = fields.One2many('academy.session.participant', 'session_id',
                                     string='Participants')
    
    notes = fields.Text(string='Notes')
    active = fields.Boolean(string='Active', default=True)

    @api.model_create_multi
    def create(self, vals_list):
        records = super().create(vals_list)
        records._sync_suspension_state()
        return records

    def write(self, vals):
        res = super().write(vals)
        if not self.env.context.get('skip_suspension_sync') and (
            {'date', 'season_id', 'is_individual'} & set(vals.keys())
            or not vals.keys() & {'state', 'suspension_id', 'state_before_suspension'}
        ):
            self._sync_suspension_state()
        return res

    # ------------------------------------------------------------------
    # Suspension helpers
    # ------------------------------------------------------------------
    def _sync_suspension_state(self, future_only=True):
        """Ensure occurrences align with any active suspension window."""
        today = fields.Date.today()
        for occurrence in self:
            suspension = occurrence._find_applicable_suspension()
            if suspension:
                occurrence._suspend_with(suspension)
            elif (
                occurrence.state == 'suspended'
                and occurrence.suspension_id
                and occurrence.date
                and (not future_only or occurrence.date >= today)
            ):
                occurrence._lift_suspension(future_only=future_only)

    def _find_applicable_suspension(self):
        """Return the active suspension window covering this occurrence, if any."""
        self.ensure_one()
        season: 'AcademySeason' = self.season_id  # type: ignore[assignment]
        if not season or not self.date:
            return self.env['academy.season.suspension']

        suspensions = season.suspension_ids.filtered(
            lambda s: s.active
            and s.start_date <= self.date <= s.end_date
            and (
                (self.is_individual and s.apply_to_individual)
                or (not self.is_individual and s.apply_to_group)
            )
        )
        if not suspensions:
            return self.env['academy.season.suspension']
        return suspensions.sorted(lambda s: (s.start_date, s.id), reverse=True)[0]

    def _suspend_with(self, suspension):
        """Apply the given suspension window to the occurrences."""
        for occurrence in self:
            if occurrence.state in ('cancelled', 'completed'):
                continue
            if occurrence.suspension_id == suspension and occurrence.state == 'suspended':
                continue

            previous_state = (
                occurrence.state_before_suspension
                or (occurrence.state if occurrence.state != 'suspended' else 'planned')
            )

            super(AcademySessionOccurrence, occurrence.with_context(skip_suspension_sync=True)).write({
                'state_before_suspension': previous_state,
                'state': 'suspended',
                'suspension_id': suspension.id,
            })
            occurrence.message_post(body=f'Session suspended: {suspension.reason}')  # type: ignore[attr-defined]

    def _lift_suspension(self, future_only=True):
        """Restore the occurrence to its state prior to suspension."""
        today = fields.Date.today()
        for occurrence in self:
            if future_only and occurrence.date and occurrence.date < today:
                continue
            previous_state = occurrence.state_before_suspension or 'planned'
            super(AcademySessionOccurrence, occurrence.with_context(skip_suspension_sync=True)).write({
                'state': previous_state,
                'state_before_suspension': False,
                'suspension_id': False,
            })
            occurrence.message_post(body='Session reactivated - suspension lifted')  # type: ignore[attr-defined]

    @api.depends('skill_group_id', 'date', 'session_type', 'is_individual')
    def _compute_name(self):
        """Generate display name."""
        for occurrence in self:
            if occurrence.is_individual:
                player_names = ', '.join(occurrence.player_ids.mapped('name')[:3])
                occurrence.name = f"Individual: {player_names} - {occurrence.date}"
            elif occurrence.skill_group_id:
                # Format start time in user's/context timezone (stored datetimes are UTC)
                try:
                    # Use environment tzinfo (occurrence.env.tz) so we match Odoo's display tz
                    context_tz = occurrence.env.tz or pytz.utc
                    # stored datetime is naive UTC; localize to UTC then convert
                    start_dt_local = pytz.utc.localize(occurrence.start_datetime).astimezone(context_tz)
                    time_str = start_dt_local.strftime('%H:%M')
                except Exception:
                    # fallback to naive formatting
                    time_str = occurrence.start_datetime.strftime('%H:%M')

                occurrence.name = (f"{occurrence.skill_group_id.name} - "
                                 f"{occurrence.date} "
                                 f"{time_str}")
            else:
                occurrence.name = f"Session {occurrence.date}"

    @api.depends('start_datetime', 'end_datetime')
    def _compute_duration(self):
        """Calculate duration in hours."""
        for occurrence in self:
            if occurrence.start_datetime and occurrence.end_datetime:
                delta = occurrence.end_datetime - occurrence.start_datetime
                occurrence.duration = delta.total_seconds() / 3600
            else:
                occurrence.duration = 0

    @api.depends('absence_ids')
    def _compute_absence_count(self):
        """Count active absences."""
        for occurrence in self:
            occurrence.absence_count = len(occurrence.absence_ids.filtered(
                lambda a: a.state in ('reported', 'acknowledged')
            ))

    @api.depends('attendance_ids')
    def _compute_attendance_count(self):
        """Count attendance records (confirmed present players)."""
        for occurrence in self:
            occurrence.attendance_count = len(occurrence.attendance_ids)

    @api.constrains('start_datetime', 'end_datetime')
    def _check_datetimes(self):
        """Validate datetime fields."""
        for occurrence in self:
            if occurrence.start_datetime >= occurrence.end_datetime:
                raise ValidationError('End time must be after start time!')

    @api.constrains('court_ids', 'start_datetime', 'end_datetime')
    def _check_court_conflicts(self):
        """Prevent overlapping court allocations."""
        for occurrence in self:
            if not occurrence.court_ids or occurrence.state in ('cancelled', 'suspended'):
                continue
            
            # Find occurrences with overlapping time and courts
            conflicting = self.search([
                ('id', '!=', occurrence.id),
                ('state', 'not in', ['cancelled', 'suspended']),
                ('court_ids', 'in', occurrence.court_ids.ids),
                ('start_datetime', '<', occurrence.end_datetime),
                ('end_datetime', '>', occurrence.start_datetime),
            ])
            
            if conflicting:
                court_names = ', '.join(occurrence.court_ids.mapped('name'))
                raise ValidationError(
                    f'Court conflict! Courts {court_names} are already booked for: '
                    f'{conflicting[0].name}'
                )

    @api.constrains('player_ids', 'start_datetime', 'end_datetime', 'is_individual')
    def _check_player_double_booking(self):
        """Prevent double-booking players (optional, can be configured)."""
        # Get config parameter for double booking check
        check_double_booking = self.env['ir.config_parameter'].sudo().get_param(
            'academy_schedule.check_player_double_booking', 'True'
        )
        
        if check_double_booking != 'True':
            return
        
        for occurrence in self:
            if not occurrence.player_ids or occurrence.state in ('cancelled', 'suspended'):
                continue
            
            # Check for overlapping sessions with same players
            for player in occurrence.player_ids:
                conflicting = self.search([
                    ('id', '!=', occurrence.id),
                    ('state', 'not in', ['cancelled', 'suspended']),
                    '|',
                    ('player_ids', 'in', player.ids),
                    ('skill_group_id', '=', player.skill_group_id.id),
                    ('start_datetime', '<', occurrence.end_datetime),
                    ('end_datetime', '>', occurrence.start_datetime),
                ])
                
                if conflicting:
                    raise ValidationError(
                        f'Player {player.name} is already booked for: '
                        f'{conflicting[0].name}'
                    )

    def action_cancel(self):
        """Cancel the session."""
        for occurrence in self:
            occurrence.write({'state': 'cancelled'})
            occurrence.message_post(body='Session cancelled')
        return True

    def action_reactivate(self):
        """Reactivate a cancelled/suspended session."""
        for occurrence in self:
            occurrence.write({
                'state': 'planned',
                'state_before_suspension': False,
                'suspension_id': False,
            })
            occurrence.message_post(body='Session reactivated')
        self._sync_suspension_state()
        return True

    def action_complete(self):
        """Mark session as completed."""
        for occurrence in self:
            occurrence.write({'state': 'completed'})
            occurrence.message_post(body='Session completed')
        return True

    def action_report_absence(self):
        """Open absence reporting wizard."""
        self.ensure_one()
        return {
            'name': 'Report Absence',
            'type': 'ir.actions.act_window',
            'res_model': 'academy.session.absence',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_occurrence_id': self.id,
            },
        }

    def action_view_absences(self):
        """View absences for this session."""
        self.ensure_one()
        return {
            'name': f'Absences: {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'academy.session.absence',
            'view_mode': 'tree,form',
            'domain': [('occurrence_id', '=', self.id)],
            'context': {'default_occurrence_id': self.id},
        }

    # ------------------------------------------------------------------
    # Attendance Management
    # ------------------------------------------------------------------
    
    def _get_registered_players(self):
        """
        Get all players registered for this session.
        For group sessions: all players in the skill group.
        For individual sessions: explicitly assigned players.
        """
        self.ensure_one()
        if self.session_type in ['tennis_group', 'physical_group']:
            # Group session: all players in skill group
            import logging
            _logger = logging.getLogger(__name__)
            _logger.info(f"Getting registered players for session {self.id}: skill_group_id={self.skill_group_id.id if self.skill_group_id else None}, skill_group_name={self.skill_group_id.name if self.skill_group_id else None}")
            
            players = self.env['academy.player'].search([
                ('skill_group_id', '=', self.skill_group_id.id),
                ('active', '=', True)
            ])
            _logger.info(f"Found {len(players)} players: {[(p.reference, p.name, p.skill_group_id.name) for p in players]}")
            return players
        else:
            # Individual session: explicit participants
            return self.player_ids

    def action_confirm_attendance(self):
        """
        Open attendance confirmation wizard.
        Coach will review prepopulated roster and mark absentees.
        """
        self.ensure_one()
        
        # TODO: Re-enable time window validation after testing
        # Validate confirmation window (15 min before to 30 min after session start)
        # COMMENTED OUT FOR TESTING - Allows confirmation at any time
        # now = fields.Datetime.now()
        # window_start = self.start_datetime - timedelta(minutes=15)
        # window_end = self.start_datetime + timedelta(minutes=30)
        # 
        # if not (window_start <= now <= window_end):
        #     raise UserError(
        #         'Attendance can only be confirmed between 15 minutes before '
        #         'and 30 minutes after session start.'
        #     )
        
        if self.attendance_status == 'confirmed':
            raise UserError('Attendance already confirmed. Contact admin to adjust.')
        
        # Get registered players
        registered_players = self._get_registered_players()
        
        # Get pre-reported absences
        absence_requests = self.env['academy.session.absence'].search([
            ('occurrence_id', '=', self.id),
            ('state', 'in', ['reported', 'acknowledged'])
        ])
        
        # Open wizard with all registered players marked present by default
        wizard = self.env['academy.attendance.confirmation.wizard'].create({
            'session_id': self.id,
            'registered_player_ids': [(6, 0, registered_players.ids)],
            'present_player_ids': [(6, 0, registered_players.ids)],  # All checked by default
            'absence_request_ids': [(6, 0, absence_requests.ids)],
        })
        
        return {
            'name': 'Confirm Attendance',
            'type': 'ir.actions.act_window',
            'res_model': 'academy.attendance.confirmation.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

    def process_attendance_confirmation(self, present_player_ids):
        """
        Process attendance confirmation from wizard.
        Creates attendance records ONLY for players marked present.
        
        Args:
            present_player_ids: List of player IDs who are present
        """
        self.ensure_one()
        
        # Validate
        if self.attendance_status == 'confirmed':
            raise UserError('Attendance already confirmed.')
        
        registered_players = self._get_registered_players()
        present_players = self.env['academy.player'].browse(present_player_ids)
        
        # Validate present_player_ids are subset of registered (plus walk-ins)
        walk_ins = self.participant_ids.filtered(lambda p: p.is_walkin).mapped('player_id')
        all_eligible = registered_players | walk_ins
        
        if not set(present_player_ids).issubset(set(all_eligible.ids)):
            raise ValidationError('Some players are not registered for this session.')
        
        # Create attendance records ONLY for present players
        attendance_vals = []
        for player in present_players:
            # Check if walk-in
            walk_in_participant = self.participant_ids.filtered(
                lambda p: p.player_id == player and p.is_walkin
            )
            
            attendance_vals.append({
                'session_id': self.id,
                'player_id': player.id,
                'state': 'present',
                'marked_by_id': self.env.user.id,
                'confirmation_time': fields.Datetime.now(),
                'is_walkin': bool(walk_in_participant),
                'walkin_reason': walk_in_participant.walkin_reason if walk_in_participant else False,
            })
        
        if attendance_vals:
            self.env['academy.attendance'].create(attendance_vals)
        
        # Update session status
        self.write({'attendance_status': 'confirmed'})
        
        # Calculate counts for audit
        present_count = len(present_player_ids)
        total_count = len(registered_players)
        absent_count = total_count - present_count
        
        # Account for pre-reported absences
        absence_requests = self.env['academy.session.absence'].search([
            ('occurrence_id', '=', self.id),
            ('state', 'in', ['reported', 'acknowledged'])
        ])
        pre_reported = len(absence_requests)
        unreported_absent = absent_count - pre_reported
        
        # Post audit trail
        self.message_post(
            body=f"Attendance confirmed by {self.env.user.name}. "
                 f"{present_count} of {total_count} players present. "
                 f"Unreported absences: {unreported_absent}. "
                 f"Pre-reported absences: {pre_reported}."
        )
        
        return {
            'present_count': present_count,
            'unreported_absent': max(0, unreported_absent),
            'pre_reported': pre_reported,
            'total_count': total_count
        }

    def action_add_walkin_player(self):
        """
        Open walk-in player addition wizard.
        Allows coach to add unregistered players to session.
        """
        self.ensure_one()
        
        wizard = self.env['academy.attendance.walkin.wizard'].create({
            'session_id': self.id,
        })
        
        return {
            'name': 'Add Walk-In Player',
            'type': 'ir.actions.act_window',
            'res_model': 'academy.attendance.walkin.wizard',
            'res_id': wizard.id,
            'view_mode': 'form',
            'target': 'new',
            'context': self.env.context,
        }

