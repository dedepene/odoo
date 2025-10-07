"""Session template model for weekly recurring session patterns."""
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import datetime, timedelta, time
import pytz


class AcademySessionTemplate(models.Model):
    """Weekly recurring session template for group practice."""
    
    _name = 'academy.session.template'
    _description = 'Session Template'
    _order = 'day_of_week, start_time'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Template Name', compute='_compute_name', store=True)
    season_id = fields.Many2one('academy.season', string='Season', required=True,
                               ondelete='cascade', tracking=True)
    skill_group_id = fields.Many2one('academy.skill.group', string='Skill Group',
                                    required=True, tracking=True)
    day_of_week = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], string='Day of Week', required=True, tracking=True)
    
    start_time = fields.Float(string='Start Time', required=True, tracking=True,
                             help='Time in HH:MM format (e.g., 17.0 for 5:00 PM)')
    end_time = fields.Float(string='End Time', required=True, tracking=True,
                           help='Time in HH:MM format (e.g., 19.0 for 7:00 PM)')
    duration = fields.Float(string='Duration (hours)', compute='_compute_duration', 
                          store=True)
    
    session_type = fields.Selection([
        ('tennis_group', 'Tennis Skills (Group)'),
        ('physical_group', 'Physical Activities (Group)'),
        ('tennis_individual', 'Tennis Skills (Individual)'),
        ('physical_individual', 'Physical Activities (Individual)'),
    ], string='Session Type', default='tennis_group', required=True, tracking=True)
    
    court_ids = fields.Many2many('academy.court', string='Courts', required=True,
                                help='Courts allocated for this session')
    coach_id = fields.Many2one('res.users', string='Assigned Coach')
    
    # Follow-up session configuration
    has_followup = fields.Boolean(string='Has Follow-up Session', default=False,
                                 help='Automatically create a chained physical session')
    followup_duration = fields.Float(string='Follow-up Duration (hours)', default=1.0)
    followup_session_type = fields.Selection([
        ('physical_group', 'Physical Activities (Group)'),
        ('physical_individual', 'Physical Activities (Individual)'),
    ], string='Follow-up Type', default='physical_group')
    
    # Parent link for follow-up sessions
    parent_template_id = fields.Many2one('academy.session.template', 
                                        string='Parent Template',
                                        help='If this is a follow-up, links to base session')
    is_followup = fields.Boolean(string='Is Follow-up', default=False)
    
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')
    
    # Computed
    occurrence_count = fields.Integer(string='Occurrences', 
                                     compute='_compute_occurrence_count')

    @api.depends('skill_group_id', 'day_of_week', 'start_time', 'session_type')
    def _compute_name(self):
        """Generate template name from key fields."""
        day_names = dict(self._fields['day_of_week'].selection)
        for template in self:
            if template.skill_group_id and template.day_of_week:
                start_h = int(template.start_time)
                start_m = int((template.start_time % 1) * 60)
                time_str = f"{start_h:02d}:{start_m:02d}"
                template.name = (f"{template.skill_group_id.name} - "
                               f"{day_names[template.day_of_week]} {time_str}")
            else:
                template.name = 'New Template'

    @api.depends('start_time', 'end_time')
    def _compute_duration(self):
        """Calculate session duration."""
        for template in self:
            template.duration = template.end_time - template.start_time

    def _compute_occurrence_count(self):
        """Count generated occurrences."""
        for template in self:
            template.occurrence_count = self.env['academy.session.occurrence'].search_count([
                ('template_id', '=', template.id)
            ])

    @api.constrains('start_time', 'end_time')
    def _check_times(self):
        """Validate time fields."""
        for template in self:
            if template.start_time >= template.end_time:
                raise ValidationError('End time must be after start time!')
            if template.start_time < 0 or template.start_time >= 24:
                raise ValidationError('Start time must be between 0 and 24!')
            if template.end_time < 0 or template.end_time > 24:
                raise ValidationError('End time must be between 0 and 24!')

    @api.constrains('court_ids', 'day_of_week', 'start_time', 'end_time', 'season_id')
    def _check_court_conflicts(self):
        """Prevent overlapping court allocations."""
        for template in self:
            if not template.court_ids:
                continue
            
            # Skip validation during creation before all fields are set
            if not template.id or not template.season_id:
                continue
                
            # Find templates on same day with overlapping time
            # We check for actual time overlap: two sessions overlap if one starts 
            # before the other ends AND ends after the other starts
            conflicting = self.search([
                ('id', '!=', template.id),
                ('season_id', '=', template.season_id.id),
                ('day_of_week', '=', template.day_of_week),
                ('active', '=', True),
                ('court_ids', 'in', template.court_ids.ids),
                ('start_time', '<', template.end_time),
                ('end_time', '>', template.start_time),
            ])
            
            if conflicting:
                # Double-check that there's actually a court overlap (not just any court)
                for conf in conflicting:
                    common_courts = set(template.court_ids.ids) & set(conf.court_ids.ids)
                    if common_courts:
                        court_names = ', '.join(
                            self.env['academy.court'].browse(list(common_courts)).mapped('name')
                        )
                        raise ValidationError(
                            f'Court conflict detected! Courts {court_names} are already '
                            f'allocated to: {conf.name}'
                        )

    def generate_occurrences(self, future_only=False):
        """Generate session occurrences from this template.
        
        Args:
            future_only: If True, only generate for dates after today
            
        Returns:
            int: Number of occurrences created
        """
        self.ensure_one()
        
        if not self.season_id or not self.season_id.active:
            raise ValidationError('Cannot generate occurrences for inactive season!')
        
        Occurrence = self.env['academy.session.occurrence']
        created_count = 0
        
        # Determine start date
        start_date = self.season_id.start_date
        if future_only:
            today = fields.Date.today()
            start_date = max(start_date, today)
        
        # Iterate through date range
        current_date = start_date
        target_weekday = int(self.day_of_week)
        
        # Find first matching weekday
        while current_date.weekday() != target_weekday:
            current_date += timedelta(days=1)
            if current_date > self.season_id.end_date:
                break
        
        # Generate occurrences for each matching weekday
        while current_date <= self.season_id.end_date:
            # Check if already exists
            existing = Occurrence.search([
                ('template_id', '=', self.id),
                ('date', '=', current_date),
            ], limit=1)
            
            if not existing:
                # Create occurrence
                occurrence_vals = self._prepare_occurrence_vals(current_date)
                occurrence = Occurrence.create(occurrence_vals)
                created_count += 1
                
                # Create follow-up if configured
                if self.has_followup and not self.is_followup:
                    followup_vals = self._prepare_followup_occurrence_vals(current_date)
                    followup_vals['parent_occurrence_id'] = occurrence.id
                    Occurrence.create(followup_vals)
                    created_count += 1
            
            # Move to next week
            current_date += timedelta(weeks=1)
        
        # Log to chatter
        if created_count > 0:
            self.message_post(
                body=f'Generated {created_count} new occurrence(s) for this template.'
            )
        
        return created_count

    def _prepare_occurrence_vals(self, date):
        """Prepare values for creating an occurrence."""
        # Convert float time to datetime
        start_h = int(self.start_time)
        start_m = int((self.start_time % 1) * 60)
        end_h = int(self.end_time)
        end_m = int((self.end_time % 1) * 60)
        
        # create naive datetimes in local wall time (date + hh:mm)
        start_datetime = datetime.combine(date, time(start_h, start_m))
        end_datetime = datetime.combine(date, time(end_h, end_m))

        # Localize to environment timezone (or user's tz) and convert to UTC
        tz_name = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        try:
            context_tz = pytz.timezone(tz_name)
        except Exception:
            context_tz = pytz.utc

        # Localize naive datetimes to the context timezone, then convert to UTC
        start_dt_localized = context_tz.localize(start_datetime)
        end_dt_localized = context_tz.localize(end_datetime)

        # Odoo stores datetimes in UTC without tzinfo (naive UTC datetimes)
        start_datetime = start_dt_localized.astimezone(pytz.utc).replace(tzinfo=None)
        end_datetime = end_dt_localized.astimezone(pytz.utc).replace(tzinfo=None)
        
        return {
            'template_id': self.id,
            'season_id': self.season_id.id,
            'skill_group_id': self.skill_group_id.id,
            'date': date,
            'start_datetime': start_datetime,
            'end_datetime': end_datetime,
            'session_type': self.session_type,
            'court_ids': [(6, 0, self.court_ids.ids)],
            'coach_id': self.coach_id.id if self.coach_id else False,
            'is_individual': False,
        }

    def _prepare_followup_occurrence_vals(self, date):
        """Prepare values for follow-up occurrence."""
        # Follow-up starts when base session ends
        end_h = int(self.end_time)
        end_m = int((self.end_time % 1) * 60)
        followup_end_time = self.end_time + self.followup_duration
        
        followup_end_h = int(followup_end_time)
        followup_end_m = int((followup_end_time % 1) * 60)
        
        # create naive datetimes in local wall time
        start_datetime = datetime.combine(date, time(end_h, end_m))
        end_datetime = datetime.combine(date, time(followup_end_h, followup_end_m))

        # Localize to environment timezone and convert to UTC naive datetimes
        tz_name = self.env.context.get('tz') or self.env.user.tz or 'UTC'
        try:
            context_tz = pytz.timezone(tz_name)
        except Exception:
            context_tz = pytz.utc

        start_dt_localized = context_tz.localize(start_datetime)
        end_dt_localized = context_tz.localize(end_datetime)

        start_datetime = start_dt_localized.astimezone(pytz.utc).replace(tzinfo=None)
        end_datetime = end_dt_localized.astimezone(pytz.utc).replace(tzinfo=None)
        
        return {
            'parent_occurrence_id': False,  # Will be set after base occurrence created
            'season_id': self.season_id.id,
            'skill_group_id': self.skill_group_id.id,
            'date': date,
            'start_datetime': start_datetime,
            'end_datetime': end_datetime,
            'session_type': self.followup_session_type,
            'court_ids': [(6, 0, self.court_ids.ids)],
            'coach_id': self.coach_id.id if self.coach_id else False,
            'is_individual': False,
            'is_followup': True,
        }

    def action_view_occurrences(self):
        """Open list of generated occurrences."""
        self.ensure_one()
        return {
            'name': f'Occurrences: {self.name}',
            'type': 'ir.actions.act_window',
            'res_model': 'academy.session.occurrence',
            'view_mode': 'tree,form,calendar',
            'domain': [('template_id', '=', self.id)],
            'context': {'default_template_id': self.id},
        }
