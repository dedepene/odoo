# -*- coding: utf-8 -*-
# pyright: reportGeneralTypeIssues=false
# mypy: ignore-errors
"""Academy Attendance - Core attendance tracking models."""

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError


class AcademyAttendance(models.Model):
    """
    Attendance records for academy sessions.
    Only created for players marked PRESENT by coach during confirmation.
    No attendance record = player was absent or didn't attend.
    """
    
    _name = 'academy.attendance'
    _description = 'Player Session Attendance'
    _order = 'confirmation_time desc, session_id, player_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    
    # Core relationships
    session_id = fields.Many2one(
        'academy.session.occurrence', 
        string='Session',
        required=True, 
        ondelete='cascade', 
        tracking=True,
        index=True
    )
    player_id = fields.Many2one(
        'academy.player', 
        string='Player', 
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True
    )
    
    # Session details (for reporting convenience)
    session_date = fields.Date(
        string='Session Date',
        related='session_id.date',
        store=True,
        readonly=True,
        index=True
    )
    session_type = fields.Selection(
        string='Session Type',
        related='session_id.session_type',
        store=True,
        readonly=True
    )
    skill_group_id = fields.Many2one(
        'academy.skill.group',
        string='Skill Group',
        related='session_id.skill_group_id',
        store=True,
        readonly=True
    )
    
    # Attendance state
    state = fields.Selection(selection=[
        ('present', 'Present'),
        ('late', 'Late'),
    ], string='Status', default='present', required=True, tracking=True)  # type: ignore[arg-type]
    
    # Confirmation metadata
    marked_by_id = fields.Many2one(
        'res.users',
        string='Marked By (Coach)',
        default=lambda self: self.env.user,
        readonly=True,
        required=True
    )
    confirmation_time = fields.Datetime(
        string='Confirmation Time',
        default=fields.Datetime.now,
        readonly=True,
        required=True,
        index=True
    )
    
    # Walk-in tracking
    is_walkin = fields.Boolean(
        string='Walk-In Player',
        default=False,
        help='Player was added to session ad-hoc (not pre-registered)',
        tracking=True
    )
    walkin_reason = fields.Selection(selection=[
        ('trial', 'Trial Session'),
        ('makeup', 'Make-up for Missed Session'),
        ('advancement', 'Skill Level Advancement'),
        ('other', 'Other'),
    ], string='Walk-In Reason', tracking=True)  # type: ignore[arg-type]
    
    # Additional info
    notes = fields.Text(string='Notes')
    
    # Constraints
    _sql_constraints = [
        (
            'unique_session_player_attendance',
            'UNIQUE(session_id, player_id)',
            'Attendance record already exists for this player in this session!'
        ),
    ]

    @api.depends('player_id', 'session_id', 'session_date')
    def _compute_name(self):
        """Generate readable reference."""
        for record in self:
            if record.player_id and record.session_id:
                date_str = record.session_date.strftime('%Y-%m-%d') if record.session_date else 'N/A'
                record.name = f"{record.player_id.name} - {date_str}"  # type: ignore[attr-defined]
            else:
                record.name = 'New Attendance'

    @api.constrains('session_id', 'player_id')
    def _check_player_eligible(self):
        """
        Validate player is eligible for the session.
        For group sessions: player should be in skill group OR be a walk-in.
        For individual sessions: player should be in participant list OR be a walk-in.
        """
        for record in self:
            if record.is_walkin:
                # Walk-ins are always allowed (validated in wizard)
                continue
            
            session = record.session_id
            player = record.player_id

            if session.session_type in ['tennis_group', 'physical_group']:  # type: ignore[attr-defined]
                # Group session: check skill group
                if session.skill_group_id and player.skill_group_id != session.skill_group_id:  # type: ignore[attr-defined]
                    raise ValidationError(  # type: ignore[attr-defined]
                        f"Player {player.name} is not in the skill group "  # type: ignore[attr-defined]
                        f"'{session.skill_group_id.name}' for this session. "  # type: ignore[attr-defined]
                        f"Use 'Add Walk-In Player' instead."
                    )
            elif session.session_type in ['tennis_individual', 'physical_individual']:  # type: ignore[attr-defined]
                # Individual session: check participant list
                if player not in session.player_ids:  # type: ignore[attr-defined]
                    raise ValidationError(  # type: ignore[attr-defined]
                        f"Player {player.name} is not registered for this individual session. "  # type: ignore[attr-defined]
                        f"Use 'Add Walk-In Player' instead."
                    )

    def unlink(self):
        """Prevent deletion of billed attendance records when billing is installed."""
        if 'billing_item_id' in self._fields:
            for record in self:
                if record.billing_item_id:  # type: ignore[attr-defined]
                    raise UserError(
                        f"Cannot delete attendance record for {record.player_id.name} - "  # type: ignore[attr-defined]
                        f"it has already been billed. Contact administrator."
                    )
        return super().unlink()


class AcademySessionParticipant(models.Model):
    """
    Session participants including walk-ins.
    Links players to sessions temporarily (ad-hoc additions).
    """

    _name = 'academy.session.participant'
    _description = 'Session Participant (Walk-In Support)'
    _order = 'session_id, player_id'

    session_id = fields.Many2one(
        'academy.session.occurrence',
        string='Session',
        required=True,
        ondelete='cascade',
        index=True
    )
    player_id = fields.Many2one(
        'academy.player',
        string='Player',
        required=True,
        ondelete='cascade',
        index=True
    )

    # Walk-in metadata
    is_walkin = fields.Boolean(
        string='Walk-In',
        default=False,
        help='Player added ad-hoc, not part of regular roster'
    )
    walkin_reason = fields.Selection(selection=[
        ('trial', 'Trial Session'),
        ('makeup', 'Make-up for Missed Session'),
        ('advancement', 'Skill Level Advancement'),
        ('other', 'Other'),
    ], string='Walk-In Reason')  # type: ignore[arg-type]
    walkin_reason_note = fields.Text(string='Walk-In Reason Note')

    added_by_id = fields.Many2one(
        'res.users',
        string='Added By',
        default=lambda self: self.env.user,
        readonly=True
    )
    added_date = fields.Datetime(
        string='Added Date',
        default=fields.Datetime.now,
        readonly=True
    )

    # Constraints
    _sql_constraints = [
        (
            'unique_session_player',
            'UNIQUE(session_id, player_id)',
            'Player already in this session roster!'
        ),
    ]
