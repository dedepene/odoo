"""Session occurrence model for actual scheduled sessions."""
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime


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
    
    # Attendance tracking (will be linked from academy_attendance module)
    # attendance_ids = fields.One2many('academy.attendance', 'occurrence_id', 
    #                                  string='Attendance')
    
    notes = fields.Text(string='Notes')
    active = fields.Boolean(string='Active', default=True)

    @api.depends('skill_group_id', 'date', 'session_type', 'is_individual')
    def _compute_name(self):
        """Generate display name."""
        for occurrence in self:
            if occurrence.is_individual:
                player_names = ', '.join(occurrence.player_ids.mapped('name')[:3])
                occurrence.name = f"Individual: {player_names} - {occurrence.date}"
            elif occurrence.skill_group_id:
                occurrence.name = (f"{occurrence.skill_group_id.name} - "
                                 f"{occurrence.date} "
                                 f"{occurrence.start_datetime.strftime('%H:%M')}")
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
            occurrence.write({'state': 'planned'})
            occurrence.message_post(body='Session reactivated')
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
