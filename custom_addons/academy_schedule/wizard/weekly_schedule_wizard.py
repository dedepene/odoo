"""Weekly schedule definition wizard for creating session templates."""
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class WeeklyScheduleWizard(models.TransientModel):
    """Wizard for defining weekly recurring session templates."""
    
    _name = 'academy.weekly.schedule.wizard'
    _description = 'Weekly Schedule Definition Wizard'

    season_id = fields.Many2one('academy.season', string='Season', required=True,
                               readonly=True)
    line_ids = fields.One2many('academy.weekly.schedule.wizard.line', 'wizard_id',
                              string='Schedule Lines')
    
    @api.model
    def default_get(self, fields_list):
        """Load existing templates if editing."""
        res = super().default_get(fields_list)
        season_id = self.env.context.get('default_season_id')
        
        if season_id and 'line_ids' in fields_list:
            season = self.env['academy.season'].browse(season_id)
            lines = []
            for template in season.template_ids.filtered(lambda t: not t.is_followup):
                lines.append((0, 0, {
                    'template_id': template.id,
                    'skill_group_id': template.skill_group_id.id,
                    'day_of_week': template.day_of_week,
                    'start_time': template.start_time,
                    'end_time': template.end_time,
                    'session_type': template.session_type,
                    'court_ids': [(6, 0, template.court_ids.ids)],
                    'coach_id': template.coach_id.id if template.coach_id else False,
                    'has_followup': template.has_followup,
                    'followup_duration': template.followup_duration,
                    'followup_session_type': template.followup_session_type,
                }))
            res['line_ids'] = lines
        
        return res

    def action_apply(self):
        """Create or update templates and generate occurrences."""
        self.ensure_one()
        
        Template = self.env['academy.session.template']
        created_count = 0
        updated_count = 0
        occurrence_count = 0
        
        # Process each line
        for line in self.line_ids:
            line._validate_line()
            
            if line.template_id:
                # Update existing template
                line.template_id.write(line._prepare_template_vals())
                updated_count += 1
            else:
                # Create new template
                template = Template.create(line._prepare_template_vals())
                line.template_id = template
                created_count += 1
            
            # Generate occurrences
            count = line.template_id.generate_occurrences()
            occurrence_count += count
        
        # Log to season chatter
        summary = (
            f"Weekly schedule updated:\n"
            f"- Created {created_count} new templates\n"
            f"- Updated {updated_count} templates\n"
            f"- Generated {occurrence_count} occurrences"
        )
        self.season_id.message_post(body=summary)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Schedule updated. Generated {occurrence_count} sessions.',
                'type': 'success',
                'sticky': False,
            }
        }


class WeeklyScheduleWizardLine(models.TransientModel):
    """Individual schedule line for wizard."""
    
    _name = 'academy.weekly.schedule.wizard.line'
    _description = 'Weekly Schedule Line'

    wizard_id = fields.Many2one('academy.weekly.schedule.wizard', required=True,
                               ondelete='cascade')
    template_id = fields.Many2one('academy.session.template', string='Existing Template')
    
    # Template fields
    skill_group_id = fields.Many2one('academy.skill.group', string='Skill Group',
                                    required=True)
    day_of_week = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], string='Day', required=True)
    
    start_time = fields.Float(string='Start Time', required=True)
    end_time = fields.Float(string='End Time', required=True)
    
    session_type = fields.Selection([
        ('tennis_group', 'Tennis Skills (Group)'),
        ('physical_group', 'Physical Activities (Group)'),
    ], string='Type', default='tennis_group', required=True)
    
    court_ids = fields.Many2many('academy.court', string='Courts', required=True)
    coach_id = fields.Many2one('res.users', string='Coach')
    
    # Follow-up configuration
    has_followup = fields.Boolean(string='Add Physical Follow-up', default=False)
    followup_duration = fields.Float(string='Follow-up Duration', default=1.0)
    followup_session_type = fields.Selection([
        ('physical_group', 'Physical Activities (Group)'),
    ], string='Follow-up Type', default='physical_group')
    
    def _validate_line(self):
        """Validate line data before creating template."""
        self.ensure_one()
        
        if self.start_time >= self.end_time:
            raise ValidationError(
                f'Invalid time for {self.skill_group_id.name}: '
                f'End time must be after start time!'
            )
        
        # Check for court conflicts with other lines in this wizard
        for other_line in self.wizard_id.line_ids:
            if other_line.id == self.id or other_line.day_of_week != self.day_of_week:
                continue
            
            # Check time overlap
            if (self.start_time < other_line.end_time and 
                self.end_time > other_line.start_time):
                # Check court overlap
                common_courts = set(self.court_ids.ids) & set(other_line.court_ids.ids)
                if common_courts:
                    court_names = ', '.join(
                        self.env['academy.court'].browse(list(common_courts)).mapped('name')
                    )
                    raise ValidationError(
                        f'Court conflict on {dict(self._fields["day_of_week"].selection)[self.day_of_week]}:\n'
                        f'{self.skill_group_id.name} and {other_line.skill_group_id.name} '
                        f'both use courts: {court_names}'
                    )
    
    def _prepare_template_vals(self):
        """Prepare values for template creation/update."""
        return {
            'season_id': self.wizard_id.season_id.id,
            'skill_group_id': self.skill_group_id.id,
            'day_of_week': self.day_of_week,
            'start_time': self.start_time,
            'end_time': self.end_time,
            'session_type': self.session_type,
            'court_ids': [(6, 0, self.court_ids.ids)],
            'coach_id': self.coach_id.id if self.coach_id else False,
            'has_followup': self.has_followup,
            'followup_duration': self.followup_duration,
            'followup_session_type': self.followup_session_type,
            'active': True,
        }
