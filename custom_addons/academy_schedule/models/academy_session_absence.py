"""Absence tracking for session occurrences."""
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AcademySessionAbsence(models.Model):
    """Track player absences from scheduled sessions."""
    
    _name = 'academy.session.absence'
    _description = 'Session Absence'
    _order = 'create_date desc'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    
    occurrence_id = fields.Many2one('academy.session.occurrence', string='Session',
                                   required=True, ondelete='cascade', tracking=True)
    player_id = fields.Many2one('academy.player', string='Player', required=True,
                               tracking=True)
    
    reason_code = fields.Selection([
        ('illness', 'Illness'),
        ('injury', 'Injury'),
        ('family', 'Family Commitment'),
        ('school', 'School Event'),
        ('vacation', 'Vacation'),
        ('other', 'Other'),
    ], string='Reason', required=True, tracking=True)
    
    reason_note = fields.Text(string='Additional Details')
    attachment_ids = fields.Many2many('ir.attachment', string='Attachments',
                                     help='Optional documents (e.g., doctor note)')
    
    state = fields.Selection([
        ('reported', 'Reported'),
        ('acknowledged', 'Acknowledged by Coach'),
        ('withdrawn', 'Withdrawn'),
    ], string='Status', default='reported', tracking=True)
    
    reporter_id = fields.Many2one('res.users', string='Reported By', 
                                 default=lambda self: self.env.user,
                                 readonly=True)
    report_date = fields.Datetime(string='Report Date', default=fields.Datetime.now,
                                 readonly=True)
    
    @api.depends('player_id', 'occurrence_id')
    def _compute_name(self):
        """Generate reference name."""
        for absence in self:
            if absence.player_id and absence.occurrence_id:
                absence.name = f"{absence.player_id.name} - {absence.occurrence_id.date}"
            else:
                absence.name = 'New Absence'

    @api.constrains('occurrence_id', 'player_id', 'state')
    def _check_duplicate_absence(self):
        """Prevent duplicate active absences for same player/session."""
        for absence in self:
            if absence.state in ('reported', 'acknowledged'):
                duplicate = self.search([
                    ('id', '!=', absence.id),
                    ('occurrence_id', '=', absence.occurrence_id.id),
                    ('player_id', '=', absence.player_id.id),
                    ('state', 'in', ['reported', 'acknowledged']),
                ])
                if duplicate:
                    raise ValidationError(
                        'An active absence already exists for this player and session!'
                    )

    @api.constrains('occurrence_id')
    def _check_future_session(self):
        """Only allow absence reporting for future sessions."""
        for absence in self:
            if absence.occurrence_id.start_datetime:
                if absence.occurrence_id.start_datetime < fields.Datetime.now():
                    raise ValidationError(
                        'Cannot report absence for past sessions! '
                        'Use attendance correction instead.'
                    )

    def action_acknowledge(self):
        """Coach acknowledges the absence."""
        for absence in self:
            absence.write({'state': 'acknowledged'})
            absence.message_post(body='Absence acknowledged by coach')
        return True

    def action_withdraw(self):
        """Guardian/player withdraws the absence report."""
        for absence in self:
            # Can only withdraw before session starts
            if absence.occurrence_id.start_datetime < fields.Datetime.now():
                raise ValidationError('Cannot withdraw absence after session has started!')
            absence.write({'state': 'withdrawn'})
            absence.message_post(body='Absence withdrawn')
        return True
