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

    @api.constrains('apply_to_group', 'apply_to_individual')
    def _check_scope(self):
        for wizard in self:
            if not wizard.apply_to_group and not wizard.apply_to_individual:
                raise ValidationError('Select at least one session scope to suspend.')

    def action_suspend(self):
        """Create suspension window and update affected sessions."""
        self.ensure_one()
        
        # Create suspension record
        Suspension = self.env['academy.season.suspension'].with_context(
            suspension_apply_existing=self.cancel_existing,
            suspension_warn_empty=self.cancel_existing,
        )
        suspension = Suspension.create({
            'season_id': self.season_id.id,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'reason': self.reason,
            'apply_to_group': self.apply_to_group,
            'apply_to_individual': self.apply_to_individual,
        })
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Suspension window recorded.',
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
        suspension.write({'active': False})
        suspension._lift_suspension()  # type: ignore[attr-defined]
        
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Success',
                'message': 'Suspension removed.',
                'type': 'success',
                'sticky': False,
            }
        }
