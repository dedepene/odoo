"""Season model for managing temporal boundaries of academy operations."""
from odoo import models, fields, api
from odoo.exceptions import ValidationError
from datetime import date


class AcademySeason(models.Model):
    """Season defines the temporal scope for recurring session generation."""
    
    _name = 'academy.season'
    _description = 'Academy Season'
    _order = 'start_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Season Name', required=True, tracking=True, 
                      help='e.g., Fall 2025, Spring 2026')
    start_date = fields.Date(string='Start Date', required=True, tracking=True)
    end_date = fields.Date(string='End Date', required=True, tracking=True)
    active = fields.Boolean(string='Active', default=True, tracking=True,
                           help='Only one season can be active at a time')
    state = fields.Selection([
        ('draft', 'Draft'),
        ('active', 'Active'),
        ('suspended', 'Suspended'),
        ('completed', 'Completed'),
    ], string='Status', default='draft', tracking=True)
    
    # Relations
    template_ids = fields.One2many('academy.session.template', 'season_id', 
                                   string='Session Templates')
    occurrence_ids = fields.One2many('academy.session.occurrence', 'season_id',
                                    string='Session Occurrences')
    suspension_ids = fields.One2many('academy.season.suspension', 'season_id',
                                    string='Suspension Windows')
    
    # Computed fields
    template_count = fields.Integer(string='Templates', compute='_compute_counts')
    occurrence_count = fields.Integer(string='Occurrences', compute='_compute_counts')
    suspension_count = fields.Integer(string='Suspensions', compute='_compute_counts')
    
    notes = fields.Text(string='Notes')
    
    _sql_constraints = [
        ('check_dates', 'CHECK(end_date > start_date)', 
         'End date must be after start date!'),
    ]

    @api.depends('template_ids', 'occurrence_ids', 'suspension_ids')
    def _compute_counts(self):
        """Compute record counts for smart buttons."""
        for season in self:
            season.template_count = len(season.template_ids)
            season.occurrence_count = len(season.occurrence_ids)
            season.suspension_count = len(season.suspension_ids)

    @api.constrains('active', 'start_date', 'end_date')
    def _check_active_season_overlap(self):
        """Ensure only one active season exists and no date overlaps."""
        for season in self:
            if season.active and season.state == 'active':
                # Check for other active seasons with overlapping dates
                overlapping = self.search([
                    ('id', '!=', season.id),
                    ('active', '=', True),
                    ('state', '=', 'active'),
                    '|',
                    '&', ('start_date', '<=', season.end_date), 
                         ('end_date', '>=', season.start_date),
                    '&', ('start_date', '<=', season.start_date),
                         ('end_date', '>=', season.end_date),
                ])
                if overlapping:
                    raise ValidationError(
                        f'Cannot have overlapping active seasons. '
                        f'Conflicting season: {overlapping[0].name}'
                    )

    def action_activate(self):
        """Activate the season."""
        self.ensure_one()
        self.write({'state': 'active', 'active': True})
        self.message_post(body='Season activated')
        return True

    def action_suspend(self):
        """Suspend the season."""
        self.ensure_one()
        self.write({'state': 'suspended'})
        self.message_post(body='Season suspended')
        return True

    def action_complete(self):
        """Mark season as completed."""
        self.ensure_one()
        self.write({'state': 'completed', 'active': False})
        self.message_post(body='Season completed')
        return True

    def action_open_schedule_wizard(self):
        """Open the weekly schedule definition wizard."""
        self.ensure_one()
        return {
            'name': 'Define Weekly Schedule',
            'type': 'ir.actions.act_window',
            'res_model': 'academy.weekly.schedule.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_season_id': self.id},
        }

    def action_generate_occurrences(self):
        """Generate missing occurrences from templates."""
        self.ensure_one()
        generated_count = 0
        for template in self.template_ids:
            count = template.generate_occurrences()
            generated_count += count
        
        self.message_post(
            body=f'Generated {generated_count} new occurrences from templates.'
        )
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Generated {generated_count} occurrences',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_open_suspension_wizard(self):
        """Open the suspension wizard."""
        self.ensure_one()
        return {
            'name': 'Suspend Sessions',
            'type': 'ir.actions.act_window',
            'res_model': 'academy.suspension.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {'default_season_id': self.id},
        }

    def action_view_templates(self):
        """Smart button action to view session templates for this season."""
        self.ensure_one()
        return {
            'name': 'Session Templates',
            'type': 'ir.actions.act_window',
            'res_model': 'academy.session.template',
            'view_mode': 'list,form',
            'domain': [('season_id', '=', self.id)],
            'context': {'default_season_id': self.id},
        }

    def action_view_occurrences(self):
        """Smart button action to view session occurrences for this season."""
        self.ensure_one()
        return {
            'name': 'Session Occurrences',
            'type': 'ir.actions.act_window',
            'res_model': 'academy.session.occurrence',
            'view_mode': 'list,form,calendar',
            'domain': [('season_id', '=', self.id)],
            'context': {'default_season_id': self.id},
        }


class AcademySeasonSuspension(models.Model):
    """Suspension windows for temporarily halting session generation."""
    
    _name = 'academy.season.suspension'
    _description = 'Season Suspension Window'
    _order = 'start_date desc'

    season_id = fields.Many2one('academy.season', string='Season', required=True, 
                               ondelete='cascade')
    start_date = fields.Date(string='Suspension Start', required=True)
    end_date = fields.Date(string='Suspension End', required=True)
    reason = fields.Char(string='Reason', required=True,
                        help='e.g., Indoor dome installation, Tournament')
    apply_to_group = fields.Boolean(string='Apply to Group Sessions', default=True)
    apply_to_individual = fields.Boolean(string='Apply to Individual Sessions', 
                                        default=False)
    active = fields.Boolean(string='Active', default=True)
    
    _sql_constraints = [
        ('check_dates', 'CHECK(end_date >= start_date)',
         'End date must be on or after start date!'),
    ]

    def name_get(self):
        """Custom display name."""
        result = []
        for suspension in self:
            name = f"{suspension.reason} ({suspension.start_date} - {suspension.end_date})"
            result.append((suspension.id, name))
        return result
