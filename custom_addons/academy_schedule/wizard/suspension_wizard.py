"""Suspension wizard for temporarily halting session generation."""
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class SuspensionWizard(models.TransientModel):
    """Wizard for suspending sessions during dome installation or tournaments."""
    
    _name = 'academy.suspension.wizard'
    _description = 'Season Suspension Wizard'

    season_id = fields.Many2one('academy.season', string='Season', required=True,
                               readonly=True)
    start_date = fields.Date(string='Suspension Start', required=True)
    end_date = fields.Date(string='Suspension End', required=True)
    reason = fields.Char(string='Reason', required=True,
                        default='Indoor dome installation',
                        help='e.g., Indoor dome installation, Tournament')
    
    apply_to_group = fields.Boolean(string='Suspend Group Sessions', default=True)
    apply_to_individual = fields.Boolean(string='Suspend Individual Sessions',
                                        default=False)
    cancel_existing = fields.Boolean(string='Cancel Existing Sessions in Window',
                                    default=True,
                                    help='Mark existing planned sessions as suspended')

    @api.constrains('start_date', 'end_date')
    def _check_dates(self):
        """Validate date range."""
        for wizard in self:
            if wizard.end_date < wizard.start_date:
                raise ValidationError('End date must be on or after start date!')

    def action_suspend(self):
        """Create suspension window and update affected sessions."""
        self.ensure_one()
        
        # Create suspension record
        suspension = self.env['academy.season.suspension'].create({
            'season_id': self.season_id.id,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'reason': self.reason,
            'apply_to_group': self.apply_to_group,
            'apply_to_individual': self.apply_to_individual,
        })
        
        suspended_count = 0
        
        if self.cancel_existing:
            # Find and suspend existing planned sessions in the window
            domain = [
                ('season_id', '=', self.season_id.id),
                ('date', '>=', self.start_date),
                ('date', '<=', self.end_date),
                ('state', '=', 'planned'),
            ]
            
            # Add session type filter
            if self.apply_to_group and not self.apply_to_individual:
                domain.append(('is_individual', '=', False))
            elif self.apply_to_individual and not self.apply_to_group:
                domain.append(('is_individual', '=', True))
            
            occurrences = self.env['academy.session.occurrence'].search(domain)
            
            for occurrence in occurrences:
                occurrence.write({'state': 'suspended'})
                occurrence.message_post(
                    body=f'Session suspended: {self.reason}'
                )
                suspended_count += 1
        
        # Log to season
        summary = (
            f"Sessions suspended from {self.start_date} to {self.end_date}\n"
            f"Reason: {self.reason}\n"
            f"Affected sessions: {suspended_count}"
        )
        self.season_id.message_post(body=summary)
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Suspended {suspended_count} sessions',
                'type': 'success',
                'sticky': False,
            }
        }

    def action_remove_suspension(self):
        """Remove a suspension window and reactivate affected sessions."""
        # This would be called from a different context with suspension_id
        suspension_id = self.env.context.get('suspension_id')
        if not suspension_id:
            raise ValidationError('No suspension specified!')
        
        suspension = self.env['academy.season.suspension'].browse(suspension_id)
        
        # Reactivate future suspended sessions
        today = fields.Date.today()
        occurrences = self.env['academy.session.occurrence'].search([
            ('season_id', '=', suspension.season_id.id),
            ('date', '>=', max(suspension.start_date, today)),
            ('date', '<=', suspension.end_date),
            ('state', '=', 'suspended'),
        ])
        
        reactivated_count = 0
        for occurrence in occurrences:
            occurrence.write({'state': 'planned'})
            occurrence.message_post(body='Session reactivated - suspension removed')
            reactivated_count += 1
        
        # Deactivate or delete suspension
        suspension.write({'active': False})
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': f'Reactivated {reactivated_count} sessions',
                'type': 'success',
                'sticky': False,
            }
        }
