"""Individual session booking wizard for coaches."""
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, time, timedelta


class IndividualSessionWizard(models.TransientModel):
    """Wizard for booking individual sessions with players."""
    
    _name = 'academy.individual.session.wizard'
    _description = 'Individual Session Booking Wizard'

    player_ids = fields.Many2many('academy.player', string='Players', required=True,
                                 help='Select one or more players for this session')
    date = fields.Date(string='Date', required=True, default=fields.Date.today)
    start_time = fields.Float(string='Start Time', required=True, default=17.0)
    end_time = fields.Float(string='End Time', required=True, default=18.0)
    
    session_type = fields.Selection([
        ('tennis_individual', 'Tennis Skills (Individual)'),
        ('physical_individual', 'Physical Activities (Individual)'),
    ], string='Session Type', default='tennis_individual', required=True)
    
    court_ids = fields.Many2many('academy.court', string='Courts', required=True)
    coach_id = fields.Many2one('res.users', string='Coach', 
                              default=lambda self: self.env.user,
                              required=True)
    notes = fields.Text(string='Notes')
    
    check_conflicts = fields.Boolean(string='Check for Conflicts', default=True)
    check_double_booking = fields.Boolean(string='Prevent Player Double-Booking',
                                         default=True)

    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        """Validate time fields."""
        for wizard in self:
            if wizard.start_time >= wizard.end_time:
                raise ValidationError('End time must be after start time!')
            if wizard.start_time < 0 or wizard.start_time >= 24:
                raise ValidationError('Start time must be between 0 and 24!')
            if wizard.end_time < 0 or wizard.end_time > 24:
                raise ValidationError('End time must be between 0 and 24!')

    @api.constrains('date')
    def _check_future_date(self):
        """Prevent booking in the past."""
        for wizard in self:
            if wizard.date < fields.Date.today():
                raise ValidationError('Cannot book sessions in the past!')

    def action_book(self):
        """Create the individual session occurrence."""
        self.ensure_one()
        
        # Validate conflicts if enabled
        if self.check_conflicts:
            self._check_court_conflicts()
        
        if self.check_double_booking:
            self._check_player_conflicts()
        
        # Create session occurrence
        occurrence_vals = self._prepare_occurrence_vals()
        occurrence = self.env['academy.session.occurrence'].create(occurrence_vals)
        
        # Notify participants (optional - would need notification system)
        # self._send_notifications(occurrence)
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'academy.session.occurrence',
            'res_id': occurrence.id,
            'view_mode': 'form',
            'target': 'current',
        }

    def _prepare_occurrence_vals(self):
        """Prepare values for occurrence creation."""
        # Convert float time to datetime
        start_h = int(self.start_time)
        start_m = int((self.start_time % 1) * 60)
        end_h = int(self.end_time)
        end_m = int((self.end_time % 1) * 60)
        
        start_datetime = datetime.combine(self.date, time(start_h, start_m))
        end_datetime = datetime.combine(self.date, time(end_h, end_m))
        
        # Get season for this date (if exists)
        season = self.env['academy.season'].search([
            ('start_date', '<=', self.date),
            ('end_date', '>=', self.date),
            ('active', '=', True),
        ], limit=1)
        
        if not season:
            raise ValidationError('No active season found for the selected date!')
        
        return {
            'season_id': season.id,
            'date': self.date,
            'start_datetime': start_datetime,
            'end_datetime': end_datetime,
            'session_type': self.session_type,
            'court_ids': [(6, 0, self.court_ids.ids)],
            'coach_id': self.coach_id.id,
            'player_ids': [(6, 0, self.player_ids.ids)],
            'is_individual': True,
            'state': 'planned',
            'notes': self.notes or '',
        }

    def _check_court_conflicts(self):
        """Check for court booking conflicts."""
        self.ensure_one()
        
        # Build datetime for search
        start_h = int(self.start_time)
        start_m = int((self.start_time % 1) * 60)
        end_h = int(self.end_time)
        end_m = int((self.end_time % 1) * 60)
        
        start_datetime = datetime.combine(self.date, time(start_h, start_m))
        end_datetime = datetime.combine(self.date, time(end_h, end_m))
        
        # Search for conflicting occurrences
        conflicting = self.env['academy.session.occurrence'].search([
            ('state', 'not in', ['cancelled', 'suspended']),
            ('court_ids', 'in', self.court_ids.ids),
            ('start_datetime', '<', end_datetime),
            ('end_datetime', '>', start_datetime),
        ])
        
        if conflicting:
            court_names = ', '.join(self.court_ids.mapped('name'))
            raise ValidationError(
                f'Court conflict detected!\n'
                f'Courts {court_names} are already booked:\n'
                f'{conflicting[0].name}'
            )

    def _check_player_conflicts(self):
        """Check if players are already booked."""
        self.ensure_one()
        
        # Build datetime for search
        start_h = int(self.start_time)
        start_m = int((self.start_time % 1) * 60)
        end_h = int(self.end_time)
        end_m = int((self.end_time % 1) * 60)
        
        start_datetime = datetime.combine(self.date, time(start_h, start_m))
        end_datetime = datetime.combine(self.date, time(end_h, end_m))
        
        for player in self.player_ids:
            # Check both individual sessions and group sessions
            conflicting = self.env['academy.session.occurrence'].search([
                ('state', 'not in', ['cancelled', 'suspended']),
                '|',
                ('player_ids', 'in', player.ids),
                ('skill_group_id', '=', player.skill_group_id.id),
                ('start_datetime', '<', end_datetime),
                ('end_datetime', '>', start_datetime),
            ])
            
            if conflicting:
                raise ValidationError(
                    f'Player {player.name} is already booked:\n'
                    f'{conflicting[0].name}'
                )
