"""Weekly schedule definition wizard for selecting and scheduling session templates."""
import logging
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class WeeklyScheduleWizard(models.TransientModel):
    """Wizard for selecting which session templates to schedule."""
    
    _name = 'academy.weekly.schedule.wizard'
    _description = 'Weekly Schedule Definition Wizard'

    season_id = fields.Many2one('academy.season', string='Season', required=True,
                               readonly=True)
    line_ids = fields.One2many('academy.weekly.schedule.wizard.line', 'wizard_id',
                              string='Available Templates')
    
    @api.model
    def default_get(self, fields_list):
        """Load existing templates as selectable lines."""
        _logger = logging.getLogger(__name__)
        _logger.info(f"=== DEFAULT_GET CALLED ===")
        _logger.info(f"fields_list: {fields_list}")
        _logger.info(f"context: {self.env.context}")
        
        res = super().default_get(fields_list)
        season_id = self.env.context.get('default_season_id')
        
        _logger.info(f"season_id from context: {season_id}")
        
        if season_id and 'line_ids' in fields_list:
            season = self.env['academy.season'].browse(season_id)
            _logger.info(f"Season: {season.name}, Templates count: {len(season.template_ids)}")
            lines = []
            # Load all non-followup templates as selectable lines
            for template in season.template_ids.filtered(lambda t: not t.is_followup and t.active):
                _logger.info(f"Adding template: {template.skill_group_id.name} - {template.day_of_week}")
                lines.append((0, 0, {
                    'template_id': template.id,
                    'selected': True,  # Pre-select all by default
                    # Copy template data directly so it persists
                    'multi_skill_mode': template.multi_skill_mode,
                    'skill_group_id': template.skill_group_id.id if not template.multi_skill_mode else False,
                    'skill_group_ids': [(6, 0, template.skill_group_ids.ids)] if template.multi_skill_mode else [],
                    'day_of_week': template.day_of_week,
                    'start_time': template.start_time,
                    'end_time': template.end_time,
                    'session_type': template.session_type,
                    'court_ids': [(6, 0, template.court_ids.ids)],
                    'coach_id': template.coach_id.id if template.coach_id else False,
                    'occurrence_count': template.occurrence_count,
                }))
            res['line_ids'] = lines
            _logger.info(f"Created {len(lines)} wizard lines")
        
        _logger.info(f"default_get returning: {res}")
        return res

    def action_apply(self):
        """Generate occurrences for selected templates only."""
        self.ensure_one()
        
        # Debug: Check what we have
        _logger = logging.getLogger(__name__)
        _logger.info(f"=== WIZARD DEBUG ===")
        _logger.info(f"Season: {self.season_id.name} (ID: {self.season_id.id})")
        _logger.info(f"Total lines: {len(self.line_ids)}")
        
        occurrence_count = 0
        selected_count = 0
        
        # Process only selected lines
        for line in self.line_ids:
            _logger.info(f"Line ID {line.id}: selected={line.selected}, template_id={line.template_id.id if line.template_id else 'MISSING'}")
            if line.selected and line.template_id:
                count = line.template_id.generate_occurrences()
                occurrence_count += count
                selected_count += 1
        
        # Log to season chatter
        summary = (
            f"Weekly schedule applied:\n"
            f"- Scheduled {selected_count} template(s)\n"
            f"- Generated {occurrence_count} session occurrences"
        )
        self.season_id.message_post(body=summary)
        
        # Show success message in UI
        self.env['bus.bus']._sendone(
            self.env.user.partner_id,
            'simple_notification',
            {
                'title': 'Success',
                'message': f'Generated {occurrence_count} sessions from {selected_count} template(s).',
                'type': 'success',
                'sticky': False,
            }
        )
        
        # Close the wizard
        return {'type': 'ir.actions.act_window_close'}


class WeeklyScheduleWizardLine(models.TransientModel):
    """Selectable template line for scheduling."""
    
    _name = 'academy.weekly.schedule.wizard.line'
    _description = 'Weekly Schedule Line'

    wizard_id = fields.Many2one('academy.weekly.schedule.wizard', required=True,
                               ondelete='cascade')
    template_id = fields.Many2one('academy.session.template', string='Template', 
                                 required=True, readonly=False)  # Must be editable for web client to send it
    
    selected = fields.Boolean(string='Schedule', default=True,
                            help='Check to generate sessions for this template')
    
    # Store template data directly (not as related fields) so it persists in transient model
    multi_skill_mode = fields.Boolean(string='Multi-Skill Mode', readonly=True)
    skill_group_id = fields.Many2one('academy.skill.group', string='Skill Group', readonly=True)
    skill_group_ids = fields.Many2many('academy.skill.group', string='Skill Groups', readonly=True)
    day_of_week = fields.Selection([
        ('0', 'Monday'),
        ('1', 'Tuesday'),
        ('2', 'Wednesday'),
        ('3', 'Thursday'),
        ('4', 'Friday'),
        ('5', 'Saturday'),
        ('6', 'Sunday'),
    ], readonly=True)
    start_time = fields.Float(string='Start Time', readonly=True)
    end_time = fields.Float(string='End Time', readonly=True)
    session_type = fields.Selection([
        ('tennis_group', 'Tennis Group'),
        ('physical_group', 'Physical Group'),
    ], readonly=True)
    court_ids = fields.Many2many('academy.court', string='Courts', readonly=True)
    coach_id = fields.Many2one('res.users', string='Coach', readonly=True)
    occurrence_count = fields.Integer(string='Existing Sessions', readonly=True)
