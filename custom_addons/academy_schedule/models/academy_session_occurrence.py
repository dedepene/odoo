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
    _order = 'start_datetime asc'
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
    
    # Multi-skill group support
    multi_skill_mode = fields.Boolean(
        string='Multi-Skill Mode',
        default=False,
        tracking=True,
        help='Session allows players from multiple skill groups'
    )
    
    # Participants
    skill_group_id = fields.Many2one(
        'academy.skill.group', 
        string='Primary Skill Group',
        tracking=True,
        help='Primary skill group (for reporting/filtering)'
    )
    skill_group_ids = fields.Many2many(
        'academy.skill.group',
        'academy_session_occurrence_skill_group_rel',
        'occurrence_id',
        'skill_group_id',
        string='Skill Groups',
        tracking=True,
        help='Skill groups eligible for this session'
    )
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
        For group sessions: all players in ANY of the linked skill groups (supports multi-skill mode).
        For individual sessions: explicitly assigned players.
        """
        self.ensure_one()
        if self.session_type in ['tennis_group', 'physical_group']:
            # Group session: all players in skill group(s)
            import logging
            _logger = logging.getLogger(__name__)
            
            # Multi-skill support: search across all linked skill groups
            if self.multi_skill_mode and self.skill_group_ids:
                skill_group_ids = self.skill_group_ids.ids
            elif self.skill_group_id:
                skill_group_ids = [self.skill_group_id.id]
            else:
                _logger.warning(f"Session {self.id} has no skill groups defined!")
                return self.env['academy.player']
            
            _logger.info(
                f"Getting registered players for session {self.id} ({self.session_type}): "
                f"multi_skill_mode={self.multi_skill_mode}, skill_groups={skill_group_ids}"
            )
            
            players = self.env['academy.player'].search([
                ('skill_group_id', 'in', skill_group_ids),
                ('active', '=', True)
            ])
            
            _logger.info(
                f"Found {len(players)} players from {len(skill_group_ids)} skill group(s)"
            )
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

    def process_attendance_confirmation(self, present_player_ids, walkin_info=None):
        """
        Process attendance confirmation from wizard.
        Creates attendance records ONLY for players marked present.
        
        Args:
            present_player_ids: List of player IDs who are present
            walkin_info: Optional dict keyed by player_id with metadata (e.g. reason)
        """
        self.ensure_one()
        walkin_info = walkin_info or {}
        walkin_player_ids = set(int(pid) for pid in walkin_info.keys())
        
        # Validate
        if self.attendance_status == 'confirmed':
            raise UserError('Attendance already confirmed.')
        
        registered_players = self._get_registered_players()
        present_players = self.env['academy.player'].browse(present_player_ids)

        participant_model = self.env['academy.session.participant']
        participant_records = self.participant_ids
        participants_by_player = {}
        for participant in participant_records:
            participant_player = participant.player_id  # type: ignore[attr-defined]
            if participant_player:
                participants_by_player[participant_player.id] = participant

        registered_player_ids = set(registered_players.ids)

        # Ensure participant rows exist for incoming walk-ins before validation, so they
        # count as eligible attendees during the same confirmation cycle.
        for walkin_player_id in walkin_player_ids:
            if walkin_player_id in participants_by_player:
                continue
            participant = participant_model.create({
                'session_id': self.id,
                'player_id': walkin_player_id,
                'is_walkin': True,
                'walkin_reason': walkin_info.get(walkin_player_id, {}).get('reason'),
                'added_by_id': self.env.user.id,
            })
            participants_by_player[walkin_player_id] = participant
            participant_records |= participant
        
        # Create attendance records ONLY for present players
        attendance_vals = []
        for player in present_players:
            walk_in_participant = participants_by_player.get(player.id)
            walkin_payload = walkin_info.get(player.id, {}) if walkin_info else {}
            desired_reason = walkin_payload.get('reason')

            if player.id not in registered_player_ids and not walk_in_participant:
                # Treat as walk-in even if payload missing (fallback to 'other').
                if not desired_reason:
                    desired_reason = 'other'
                walk_in_participant = participant_model.create({
                    'session_id': self.id,
                    'player_id': player.id,
                    'is_walkin': True,
                    'walkin_reason': desired_reason,
                    'added_by_id': self.env.user.id,
                })
                participants_by_player[player.id] = walk_in_participant
                participant_records |= walk_in_participant

            is_walkin = bool(
                walk_in_participant and walk_in_participant.is_walkin  # type: ignore[attr-defined]
            ) or player.id in walkin_player_ids or player.id not in registered_player_ids

            if desired_reason:
                walkin_reason = desired_reason
            elif is_walkin and walk_in_participant:
                walkin_reason = walk_in_participant.walkin_reason  # type: ignore[attr-defined]
            else:
                walkin_reason = False

            attendance_vals.append({
                'session_id': self.id,
                'player_id': player.id,
                'state': 'present',
                'marked_by_id': self.env.user.id,
                'confirmation_time': fields.Datetime.now(),
                'is_walkin': is_walkin,
                'walkin_reason': walkin_reason if is_walkin else False,
            })
        
        if attendance_vals:
            self.env['academy.attendance'].create(attendance_vals)
        
        # Update session status
        self.write({'attendance_status': 'confirmed'})
        
        # Calculate counts for audit
        registered_player_ids = set(registered_players.ids)
        present_count = len(present_player_ids)
        registered_present_count = len([pid for pid in present_player_ids if pid in registered_player_ids])
        walkin_present_count = present_count - registered_present_count
        registered_total = len(registered_players)
        effective_total = registered_total + walkin_present_count
        absent_count = max(0, registered_total - registered_present_count)
        
        # Account for pre-reported absences
        absence_requests = self.env['academy.session.absence'].search([
            ('occurrence_id', '=', self.id),
            ('state', 'in', ['reported', 'acknowledged'])
        ])
        pre_reported = len(absence_requests)
        unreported_absent = max(0, absent_count - pre_reported)
        
        # Post audit trail
        self.message_post(  # type: ignore[attr-defined]
            body=f"Attendance confirmed by {self.env.user.name}. "
                 f"Registered present: {registered_present_count}/{registered_total}. "
                 f"Walk-ins: {walkin_present_count}. "
                 f"Unreported absences: {unreported_absent}. "
                 f"Pre-reported absences: {pre_reported}."
        )
        
        return {
            'present_count': present_count,
            'registered_present_count': registered_present_count,
            'walkin_present_count': walkin_present_count,
            'unreported_absent': max(0, unreported_absent),
            'pre_reported': pre_reported,
            'total_count': registered_total,
            'registered_total_count': registered_total,
            'effective_total_count': effective_total
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

