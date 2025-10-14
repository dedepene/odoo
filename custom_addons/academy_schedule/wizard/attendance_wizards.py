# -*- coding: utf-8 -*-
"""Attendance confirmation wizards for coaches."""

from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AttendanceConfirmationWizard(models.TransientModel):
    """
    Wizard for coach to confirm attendance.
    Displays prepopulated roster with all players checked by default.
    Coach unchecks absentees and confirms.
    """
    
    _name = 'academy.attendance.confirmation.wizard'
    _description = 'Attendance Confirmation Wizard'

    session_id = fields.Many2one(
        'academy.session.occurrence',
        string='Session',
        required=True,
        readonly=True
    )
    
    # Session display info
    session_name = fields.Char(
        string='Session',
        related='session_id.name',
        readonly=True
    )
    session_date = fields.Date(
        string='Date',
        related='session_id.date',
        readonly=True
    )
    session_start = fields.Datetime(
        string='Start Time',
        related='session_id.start_datetime',
        readonly=True
    )
    
    # Players
    registered_player_ids = fields.Many2many(
        'academy.player',
        'attendance_wizard_registered_rel',
        'wizard_id',
        'player_id',
        string='Registered Players',
        readonly=True,
        help='All players registered for this session'
    )
    
    # Present players (checked by default, coach unchecks absentees)
    present_player_ids = fields.Many2many(
        'academy.player',
        'attendance_wizard_present_rel',
        'wizard_id',
        'player_id',
        string='Present Players',
        help='Players who are present (checked). Uncheck to mark absent.'
    )
    
    # Pre-reported absences (displayed separately, read-only)
    absence_request_ids = fields.Many2many(
        'academy.session.absence',
        'attendance_wizard_absence_rel',
        'wizard_id',
        'absence_id',
        string='Pre-Reported Absences',
        readonly=True,
        help='Players who reported absence beforehand'
    )
    
    # Computed counts
    total_count = fields.Integer(
        string='Total Registered',
        compute='_compute_counts',
        store=False
    )
    present_count = fields.Integer(
        string='Present',
        compute='_compute_counts',
        store=False
    )
    absent_count = fields.Integer(
        string='Absent (Unreported)',
        compute='_compute_counts',
        store=False
    )
    pre_reported_count = fields.Integer(
        string='Pre-Reported Absences',
        compute='_compute_counts',
        store=False
    )
    
    # Confirmation message
    confirmation_message = fields.Html(
        string='Confirmation Summary',
        compute='_compute_confirmation_message',
        store=False
    )
    
    # Walk-in player fields
    walkin_player_id = fields.Many2one(
        'academy.player',
        string='Add Walk-In Player',
        domain=[('active', '=', True)],
        help='Search and select a player to add as walk-in'
    )
    
    walkin_reason = fields.Selection(
        [
            ('trial', 'Trial (Free)'),
            ('makeup', 'Makeup Session'),
            ('advancement', 'Skill Level Advancement'),
            ('other', 'Other'),
        ],
        string='Walk-In Reason',
        default='makeup',
        help='Reason for walk-in affects pricing: Trial is free, others are normal price'
    )
    
    walkin_ids = fields.One2many(
        'academy.attendance.confirmation.wizard.walkin',
        'wizard_id',
        string='Walk-In Players',
        help='Players added as walk-ins for this session'
    )
    
    walkin_count = fields.Integer(
        string='Walk-Ins',
        compute='_compute_counts',
        store=False
    )

    @api.model_create_multi
    def create(self, vals_list):
        """Override create to filter out invalid walk-in records."""
        for vals in vals_list:
            # Clean up walk-in commands - remove any without player_id
            if 'walkin_ids' in vals and vals['walkin_ids']:
                cleaned_commands = []
                for cmd in vals['walkin_ids']:
                    # cmd is a tuple like (0, 0, {dict}) or (4, id) or (6, 0, [ids])
                    if cmd[0] == 0 and len(cmd) >= 3:  # Create command
                        # Only keep if it has a player_id
                        if cmd[2].get('player_id'):
                            cleaned_commands.append(cmd)
                    else:
                        cleaned_commands.append(cmd)
                vals['walkin_ids'] = cleaned_commands
        return super().create(vals_list)
    
    def write(self, vals):
        """Override write to filter out invalid walk-in records BEFORE writing."""
        # Filter walk-in commands BEFORE calling super()
        if 'walkin_ids' in vals and vals['walkin_ids']:
            cleaned_commands = []
            for cmd in vals['walkin_ids']:
                # cmd is a tuple like (0, 0, {dict}) or (4, id) or (6, 0, [ids])
                if cmd[0] == 0 and len(cmd) >= 3:  # Create command
                    # Only keep if it has a player_id
                    if cmd[2].get('player_id'):
                        cleaned_commands.append(cmd)
                else:
                    cleaned_commands.append(cmd)
            vals['walkin_ids'] = cleaned_commands
        
        # Call super with filtered vals
        result = super().write(vals)
        
        # After write, clean up orphaned walk-in players from present_player_ids
        for wizard in self:
            # Get current walk-in player IDs
            walkin_player_ids = set(wizard.walkin_ids.mapped('player_id').ids) if wizard.walkin_ids else set()
            registered_ids = set(wizard.registered_player_ids.ids)
            present_ids = set(wizard.present_player_ids.ids)
            
            # Orphaned players = present but not registered and not in walk-ins
            orphaned_ids = present_ids - registered_ids - walkin_player_ids
            
            if orphaned_ids:
                # Remove orphaned players from present_player_ids
                wizard.present_player_ids = [(3, pid) for pid in orphaned_ids]
        
        return result
    
    @api.model
    def default_get(self, fields_list):
        """Pre-populate present players with all registered players."""
        res = super().default_get(fields_list)
        
        # Default all registered players as present (checked)
        if 'present_player_ids' in fields_list and 'registered_player_ids' in res:
            # registered_player_ids is a list of tuples: [(6, 0, [ids])]
            if res['registered_player_ids'] and res['registered_player_ids'][0]:
                # Extract the ID list from the tuple (6, 0, [id1, id2, ...])
                player_ids = res['registered_player_ids'][0][2] if len(res['registered_player_ids'][0]) > 2 else []
                res['present_player_ids'] = [(6, 0, player_ids)]
        
        return res

    @api.depends('registered_player_ids', 'present_player_ids', 'absence_request_ids', 'walkin_ids')
    def _compute_counts(self):
        """Calculate attendance counts."""
        for wizard in self:
            wizard.total_count = len(wizard.registered_player_ids)
            wizard.present_count = len(wizard.present_player_ids)
            wizard.pre_reported_count = len(wizard.absence_request_ids)
            wizard.walkin_count = len(wizard.walkin_ids)
            
            # Absent = registered - present (excluding pre-reported)
            absent_players = wizard.registered_player_ids - wizard.present_player_ids
            absence_player_ids = wizard.absence_request_ids.mapped('player_id')
            wizard.absent_count = len(absent_players - absence_player_ids)

    @api.depends('present_count', 'absent_count', 'pre_reported_count', 'total_count', 'walkin_count')
    def _compute_confirmation_message(self):
        """Generate confirmation summary message."""
        for wizard in self:
            walkin_row = ""
            if wizard.walkin_count > 0:
                walkin_row = f"""
                        <tr>
                            <td><strong>Walk-ins:</strong></td>
                            <td style="text-align: right; color: #17a2b8;">
                                {wizard.walkin_count} players
                            </td>
                        </tr>
                """
            
            wizard.confirmation_message = f"""
                <div style="padding: 15px; background-color: #f8f9fa; border-radius: 5px;">
                    <h4 style="margin-top: 0;">Attendance Summary</h4>
                    <table style="width: 100%; font-size: 14px;">
                        <tr>
                            <td><strong>Present:</strong></td>
                            <td style="text-align: right; color: #28a745;">
                                <strong>{wizard.present_count}</strong> players
                            </td>
                        </tr>
                        {walkin_row}
                        <tr>
                            <td><strong>Absent (unreported):</strong></td>
                            <td style="text-align: right; color: #dc3545;">
                                {wizard.absent_count} players
                            </td>
                        </tr>
                        <tr>
                            <td><strong>Pre-reported absences:</strong></td>
                            <td style="text-align: right; color: #6c757d;">
                                {wizard.pre_reported_count} players
                            </td>
                        </tr>
                        <tr style="border-top: 2px solid #dee2e6;">
                            <td><strong>Total Registered:</strong></td>
                            <td style="text-align: right;">
                                <strong>{wizard.total_count}</strong> players
                            </td>
                        </tr>
                    </table>
                    <p style="margin-bottom: 0; margin-top: 10px; color: #6c757d; font-size: 12px;">
                        <em>⚠️ This action cannot be undone. Contact admin to adjust later.</em>
                    </p>
                </div>
            """

    @api.onchange('walkin_player_id', 'walkin_reason')
    def _onchange_walkin_player(self):
        """Add selected player to walk-ins list when player selected."""
        if not self.walkin_player_id:
            return
        
        # Check if player is already in registered roster
        if self.walkin_player_id in self.registered_player_ids:
            return {
                'warning': {
                    'title': 'Player Already Registered',
                    'message': f'{self.walkin_player_id.name} is already in the session roster!'
                }
            }
        
        # Check if player already added as walk-in
        if self.walkin_player_id.id in self.walkin_ids.mapped('player_id').ids:
            return {
                'warning': {
                    'title': 'Player Already Added',
                    'message': f'{self.walkin_player_id.name} has already been added as a walk-in!'
                }
            }
        
        # Add to walk-ins list
        self.walkin_ids = [(0, 0, {
            'player_id': self.walkin_player_id.id,
            'reason': self.walkin_reason or 'makeup',
        })]
        
        # Add to present players list (auto-mark as present)
        self.present_player_ids = [(4, self.walkin_player_id.id)]
        
        # Clear the selection field for next entry
        self.walkin_player_id = False
        # Note: Keep walkin_reason as-is for next entry

    def action_confirm(self):
        """Confirm attendance and create attendance records."""
        self.ensure_one()
        
        # Validate at least one player present
        if not self.present_player_ids:
            raise ValidationError(
                'No players marked present. If session had zero attendance, '
                'consider cancelling the session instead.'
            )
        
        # Create participant records for walk-ins
        for walkin in self.walkin_ids:
            self.env['academy.session.participant'].create({
                'session_id': self.session_id.id,
                'player_id': walkin.player_id.id,
                'is_walkin': True,
                'walkin_reason': walkin.reason,
                'added_by_id': self.env.user.id,
            })
        
        # Refresh session cache to see newly created participants
        self.session_id.invalidate_recordset(['participant_ids'])
        
        # Process attendance confirmation
        result = self.session_id.process_attendance_confirmation(
            self.present_player_ids.ids
        )
        
        # Return success message with summary
        walkin_msg = f" (including {len(self.walkin_ids)} walk-ins)" if self.walkin_ids else ""
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Attendance Confirmed!',
                'message': (
                    f"✅ {result['present_count']} of {result['total_count']} players present{walkin_msg}. "
                    f"Session ready for billing."
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def action_cancel(self):
        """Cancel wizard without saving."""
        return {'type': 'ir.actions.act_window_close'}


class AttendanceWalkinWizard(models.TransientModel):
    """
    Wizard for adding walk-in players to session.
    Allows coach to search academy players and add them to attendance.
    """
    
    _name = 'academy.attendance.walkin.wizard'
    _description = 'Add Walk-In Player Wizard'

    session_id = fields.Many2one(
        'academy.session.occurrence',
        string='Session',
        required=True,
        readonly=True
    )
    
    # Session display info
    session_name = fields.Char(
        string='Session',
        related='session_id.name',
        readonly=True
    )
    session_skill_group_id = fields.Many2one(
        'academy.skill.group',
        string='Session Skill Group',
        related='session_id.skill_group_id',
        readonly=True
    )
    
    # Player selection
    player_id = fields.Many2one(
        'academy.player',
        string='Player',
        required=True,
        domain=[('active', '=', True)],
        help='Search for academy player to add to session'
    )
    
    # Player info (displayed after selection)
    player_skill_group_id = fields.Many2one(
        'academy.skill.group',
        string='Player Skill Group',
        related='player_id.skill_group_id',
        readonly=True
    )
    player_age = fields.Float(
        string='Player Age',
        related='player_id.age_years',
        readonly=True
    )
    
    # Skill group mismatch warning
    skill_group_mismatch = fields.Boolean(
        string='Skill Group Mismatch',
        compute='_compute_skill_group_mismatch',
        store=False
    )
    mismatch_warning = fields.Html(
        string='Warning',
        compute='_compute_mismatch_warning',
        store=False
    )
    
    # Walk-in reason
    walkin_reason = fields.Selection([
        ('trial', 'Trial Session'),
        ('makeup', 'Make-up for Missed Session'),
        ('advancement', 'Skill Level Advancement'),
        ('other', 'Other'),
    ], string='Reason', required=True, default='advancement')
    
    walkin_reason_note = fields.Text(string='Additional Notes')

    @api.depends('player_id', 'session_skill_group_id', 'player_skill_group_id')
    def _compute_skill_group_mismatch(self):
        """Check if player's skill group differs from session."""
        for wizard in self:
            if wizard.player_id and wizard.session_skill_group_id:
                wizard.skill_group_mismatch = (
                    wizard.player_skill_group_id != wizard.session_skill_group_id
                )
            else:
                wizard.skill_group_mismatch = False

    @api.depends('skill_group_mismatch', 'player_skill_group_id', 'session_skill_group_id')
    def _compute_mismatch_warning(self):
        """Generate warning message for skill group mismatch."""
        for wizard in self:
            if wizard.skill_group_mismatch:
                wizard.mismatch_warning = f"""
                    <div style="padding: 10px; background-color: #fff3cd; border: 1px solid #ffc107; border-radius: 5px;">
                        <strong>⚠️ Skill Group Mismatch</strong><br/>
                        Player's normal group: <strong>{wizard.player_skill_group_id.name or 'None'}</strong><br/>
                        Session group: <strong>{wizard.session_skill_group_id.name or 'None'}</strong>
                    </div>
                """
            else:
                wizard.mismatch_warning = ""

    @api.constrains('player_id', 'session_id')
    def _check_player_not_in_roster(self):
        """Validate player is not already in session roster."""
        for wizard in self:
            if wizard.player_id and wizard.session_id:
                # Check if already registered
                registered = wizard.session_id._get_registered_players()
                if wizard.player_id in registered:
                    raise ValidationError(
                        f'Player {wizard.player_id.name} is already in the session roster!'
                    )
                
                # Check if already added as participant
                existing_participant = self.env['academy.session.participant'].search([
                    ('session_id', '=', wizard.session_id.id),
                    ('player_id', '=', wizard.player_id.id)
                ])
                if existing_participant:
                    raise ValidationError(
                        f'Player {wizard.player_id.name} has already been added to this session!'
                    )

    def action_add_player(self):
        """Add walk-in player to session and create attendance record."""
        self.ensure_one()
        
        # Create participation record
        participant = self.env['academy.session.participant'].create({
            'session_id': self.session_id.id,
            'player_id': self.player_id.id,
            'is_walkin': True,
            'walkin_reason': self.walkin_reason,
            'walkin_reason_note': self.walkin_reason_note,
            'added_by_id': self.env.user.id,
            'added_date': fields.Datetime.now(),
        })
        
        # Create attendance record (marked present by default)
        attendance = self.env['academy.attendance'].create({
            'session_id': self.session_id.id,
            'player_id': self.player_id.id,
            'state': 'present',
            'is_walkin': True,
            'walkin_reason': self.walkin_reason,
            'marked_by_id': self.env.user.id,
            'confirmation_time': fields.Datetime.now(),
            'notes': self.walkin_reason_note,
        })
        
        # Post chatter message
        reason_text = dict(self._fields['walkin_reason'].selection).get(
            self.walkin_reason, 'Not specified'
        )
        self.session_id.message_post(
            body=f"🚶 Walk-in player <strong>{self.player_id.name}</strong> "
                 f"({self.player_id.reference}) added by {self.env.user.name}.<br/>"
                 f"<strong>Reason:</strong> {reason_text}<br/>"
                 f"Player's normal group: <strong>{self.player_skill_group_id.name or 'None'}</strong>; "
                 f"Session group: <strong>{self.session_skill_group_id.name or 'None'}</strong>"
        )
        
        # Return success notification
        return {
            'type': 'ir.actions.client',
            'tag': 'display_notification',
            'params': {
                'title': 'Walk-In Player Added!',
                'message': (
                    f"✅ {self.player_id.name} added to session and marked present. "
                    f"Flagged for billing review."
                ),
                'type': 'success',
                'sticky': False,
                'next': {'type': 'ir.actions.act_window_close'},
            }
        }

    def action_cancel(self):
        """Cancel wizard without adding player."""
        return {'type': 'ir.actions.act_window_close'}


class AttendanceConfirmationWizardWalkin(models.TransientModel):
    """Line model for walk-in players in attendance confirmation wizard."""
    
    _name = 'academy.attendance.confirmation.wizard.walkin'
    _description = 'Walk-In Player Line'
    _rec_name = 'player_id'
    
    wizard_id = fields.Many2one(
        'academy.attendance.confirmation.wizard',
        string='Wizard',
        required=True,
        ondelete='cascade'
    )
    
    player_id = fields.Many2one(
        'academy.player',
        string='Player',
        required=True,
        readonly=True
    )
    
    reason = fields.Selection(
        [
            ('trial', 'Trial (Free)'),
            ('makeup', 'Makeup Session'),
            ('advancement', 'Skill Level Advancement'),
            ('other', 'Other'),
        ],
        string='Reason',
        required=True,
        readonly=True
    )
    
    skill_group_id = fields.Many2one(
        'academy.skill.group',
        string='Skill Group',
        related='player_id.skill_group_id',
        readonly=True
    )
