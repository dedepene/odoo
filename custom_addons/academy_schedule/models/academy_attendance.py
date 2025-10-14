# -*- coding: utf-8 -*-
"""Academy Attendance - Core attendance tracking models."""

from odoo import models, fields, api
from odoo.exceptions import ValidationError, UserError
from datetime import datetime, timedelta


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
    state = fields.Selection([
        ('present', 'Present'),
        ('late', 'Late'),  # Future: for partial attendance tracking
    ], string='Status', default='present', required=True, tracking=True)
    
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
    walkin_reason = fields.Selection([
        ('trial', 'Trial Session'),
        ('makeup', 'Make-up for Missed Session'),
        ('advancement', 'Skill Level Advancement'),
        ('other', 'Other'),
    ], string='Walk-In Reason', tracking=True)
    
    # Billing integration
    billing_item_id = fields.Many2one(
        'academy.billing.item',
        string='Billing Item',
        readonly=True,
        copy=False,
        help='Link to billing item created for this attendance'
    )
    is_billed = fields.Boolean(
        string='Billed',
        compute='_compute_is_billed',
        store=True,
        help='True if billing item has been created'
    )
    
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
                record.name = f"{record.player_id.name} - {date_str}"
            else:
                record.name = 'New Attendance'

    @api.depends('billing_item_id')
    def _compute_is_billed(self):
        """Check if attendance has been billed."""
        for record in self:
            record.is_billed = bool(record.billing_item_id)

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
            
            if session.session_type in ['tennis_group', 'physical_group']:
                # Group session: check skill group
                if session.skill_group_id and player.skill_group_id != session.skill_group_id:
                    raise ValidationError(
                        f"Player {player.name} is not in the skill group "
                        f"'{session.skill_group_id.name}' for this session. "
                        f"Use 'Add Walk-In Player' instead."
                    )
            elif session.session_type in ['tennis_individual', 'physical_individual']:
                # Individual session: check participant list
                if player not in session.player_ids:
                    raise ValidationError(
                        f"Player {player.name} is not registered for this individual session. "
                        f"Use 'Add Walk-In Player' instead."
                    )

    def unlink(self):
        """Prevent deletion of billed attendance records."""
        for record in self:
            if record.is_billed:
                raise UserError(
                    f"Cannot delete attendance record for {record.player_id.name} - "
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
    walkin_reason = fields.Selection([
        ('trial', 'Trial Session'),
        ('makeup', 'Make-up for Missed Session'),
        ('advancement', 'Skill Level Advancement'),
        ('other', 'Other'),
    ], string='Walk-In Reason')
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


class AcademyBillingItem(models.Model):
    """
    Billing items generated from confirmed attendance.
    One billing item per attendance record.
    """
    
    _name = 'academy.billing.item'
    _description = 'Attendance Billing Item'
    _order = 'session_date desc, player_id'
    _inherit = ['mail.thread', 'mail.activity.mixin']

    name = fields.Char(string='Reference', compute='_compute_name', store=True)
    
    # Core relationships
    player_id = fields.Many2one(
        'academy.player',
        string='Player',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True
    )
    session_id = fields.Many2one(
        'academy.session.occurrence',
        string='Session',
        required=True,
        ondelete='cascade',
        tracking=True,
        index=True
    )
    attendance_id = fields.Many2one(
        'academy.attendance',
        string='Source Attendance',
        required=True,
        ondelete='cascade',
        help='Link to the attendance record that generated this billing item',
        index=True
    )
    
    # Billing details
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
    
    # Pricing
    amount = fields.Monetary(
        string='Amount',
        currency_field='currency_id',
        required=True,
        tracking=True
    )
    currency_id = fields.Many2one(
        'res.currency',
        string='Currency',
        default=lambda self: self.env.company.currency_id,
        required=True
    )
    
    # Guardian for invoicing
    primary_guardian_id = fields.Many2one(
        'res.partner',
        string='Primary Guardian',
        compute='_compute_primary_guardian',
        store=True,
        readonly=True,
        index=True
    )
    
    # Walk-in tracking
    is_walkin = fields.Boolean(
        string='Walk-In',
        related='attendance_id.is_walkin',
        store=True,
        readonly=True,
        help='Flagged for admin review - may need special pricing'
    )
    walkin_reason = fields.Selection(
        string='Walk-In Reason',
        related='attendance_id.walkin_reason',
        store=True,
        readonly=True
    )
    
    # State
    state = fields.Selection([
        ('pending', 'Pending Review'),
        ('approved', 'Approved'),
        ('invoiced', 'Invoiced'),
        ('cancelled', 'Cancelled'),
    ], string='Status', default='pending', required=True, tracking=True, index=True)
    
    # Invoice link
    invoice_line_id = fields.Many2one(
        'account.move.line',
        string='Invoice Line',
        readonly=True,
        copy=False
    )
    invoice_id = fields.Many2one(
        'account.move',
        string='Invoice',
        related='invoice_line_id.move_id',
        store=True,
        readonly=True
    )
    
    # Metadata
    created_by_cron = fields.Boolean(
        string='Auto-Generated',
        default=False,
        help='Created by billing cron vs manually'
    )
    notes = fields.Text(string='Notes')
    
    # Constraints
    _sql_constraints = [
        (
            'unique_attendance_billing',
            'UNIQUE(attendance_id)',
            'Billing item already exists for this attendance record!'
        ),
        (
            'amount_positive',
            'CHECK(amount >= 0)',
            'Amount must be positive or zero!'
        ),
    ]

    @api.depends('player_id', 'session_id', 'session_date', 'amount')
    def _compute_name(self):
        """Generate readable reference."""
        for record in self:
            if record.player_id and record.session_id:
                date_str = record.session_date.strftime('%Y-%m-%d') if record.session_date else 'N/A'
                walkin_flag = ' 🚶' if record.is_walkin else ''
                record.name = f"{record.player_id.name} - {date_str} - ${record.amount:.2f}{walkin_flag}"
            else:
                record.name = 'New Billing Item'

    @api.depends('player_id')
    def _compute_primary_guardian(self):
        """Get primary guardian for billing."""
        for record in self:
            if record.player_id and record.player_id.primary_guardian_id:
                record.primary_guardian_id = record.player_id.primary_guardian_id
            else:
                record.primary_guardian_id = False

    def action_approve(self):
        """Admin approves billing item."""
        for record in self:
            if record.state == 'pending':
                record.write({'state': 'approved'})
                record.message_post(body='Billing item approved for invoicing')
        return True

    def action_cancel(self):
        """Admin cancels billing item."""
        for record in self:
            if record.state in ['pending', 'approved']:
                if record.invoice_line_id:
                    raise UserError('Cannot cancel billed item. Reverse the invoice instead.')
                record.write({'state': 'cancelled'})
                record.message_post(body='Billing item cancelled')
        return True

    def unlink(self):
        """Prevent deletion of invoiced billing items."""
        for record in self:
            if record.state == 'invoiced':
                raise UserError(
                    f"Cannot delete invoiced billing item for {record.player_id.name}. "
                    f"Cancel the invoice first."
                )
        return super().unlink()


class AcademyAttendanceBilling(models.Model):
    """
    Billing processor for attendance records.
    Handles automated billing generation from confirmed attendance.
    """
    
    _name = 'academy.attendance.billing'
    _description = 'Attendance Billing Processor'

    @api.model
    def _get_session_pricing(self, session):
        """
        Determine pricing for a session based on type.
        
        Returns:
            float: Session price in company currency
        """
        # Get pricing from config parameters or use defaults
        config = self.env['ir.config_parameter'].sudo()
        
        if session.session_type == 'tennis_group':
            return float(config.get_param('academy.billing.group_tennis_price', '25.0'))
        elif session.session_type == 'physical_group':
            return float(config.get_param('academy.billing.group_physical_price', '20.0'))
        elif session.session_type == 'tennis_individual':
            return float(config.get_param('academy.billing.individual_tennis_price', '60.0'))
        elif session.session_type == 'physical_individual':
            return float(config.get_param('academy.billing.individual_physical_price', '40.0'))
        else:
            return 25.0  # Default fallback

    @api.model
    def _get_walkin_pricing(self, attendance):
        """
        Determine pricing for walk-in attendance.
        Trial sessions are free, others use normal pricing.
        
        Returns:
            float: Walk-in session price
        """
        if attendance.walkin_reason == 'trial':
            return 0.0  # Trial sessions are free
        else:
            # Normal pricing for makeup/advancement/other
            return self._get_session_pricing(attendance.session_id)

    @api.model
    def generate_billing_items(self, date_from=None, date_to=None):
        """
        Generate billing items for confirmed attendance records.
        
        Args:
            date_from: Start date for billing period (default: start of current month)
            date_to: End date for billing period (default: today)
        
        Returns:
            dict: Summary of billing generation
        """
        # Default date range: current month to today
        if not date_from:
            date_from = fields.Date.today().replace(day=1)
        if not date_to:
            date_to = fields.Date.today()
        
        # Query confirmed sessions with unbilled attendance
        domain = [
            ('session_date', '>=', date_from),
            ('session_date', '<=', date_to),
            ('billing_item_id', '=', False),  # Not yet billed
            ('session_id.attendance_status', '=', 'confirmed'),  # Coach confirmed
        ]
        
        unbilled_attendances = self.env['academy.attendance'].search(domain)
        
        billing_items_created = []
        errors = []
        
        for attendance in unbilled_attendances:
            try:
                # Determine pricing
                if attendance.is_walkin:
                    amount = self._get_walkin_pricing(attendance)
                else:
                    amount = self._get_session_pricing(attendance.session_id)
                
                # Get primary guardian
                primary_guardian = attendance.player_id.primary_guardian_id
                if not primary_guardian:
                    errors.append({
                        'attendance_id': attendance.id,
                        'player': attendance.player_id.name,
                        'error': 'No primary guardian set'
                    })
                    continue
                
                # Create billing item
                billing_item = self.env['academy.billing.item'].create({
                    'player_id': attendance.player_id.id,
                    'session_id': attendance.session_id.id,
                    'attendance_id': attendance.id,
                    'amount': amount,
                    'primary_guardian_id': primary_guardian.id,
                    'state': 'pending' if not attendance.is_walkin else 'pending',
                    'created_by_cron': True,
                    'notes': f"Auto-generated from attendance confirmation on {fields.Date.today()}"
                })
                
                # Link billing item to attendance
                attendance.write({'billing_item_id': billing_item.id})
                
                billing_items_created.append(billing_item.id)
                
            except Exception as e:
                errors.append({
                    'attendance_id': attendance.id,
                    'player': attendance.player_id.name,
                    'error': str(e)
                })
        
        # Log summary
        summary = {
            'date_from': date_from,
            'date_to': date_to,
            'billing_items_created': len(billing_items_created),
            'attendances_processed': len(unbilled_attendances),
            'errors': len(errors),
            'error_details': errors,
        }
        
        _logger = logging.getLogger(__name__)
        _logger.info(
            f"Attendance billing: Created {len(billing_items_created)} billing items "
            f"from {len(unbilled_attendances)} attendance records. "
            f"Errors: {len(errors)}"
        )
        
        return summary

    @api.model
    def cron_generate_monthly_billing(self):
        """
        Cron job to generate monthly billing items.
        Runs on the 1st of each month for previous month's attendance.
        """
        # Calculate previous month date range
        today = fields.Date.today()
        first_of_month = today.replace(day=1)
        last_month_end = first_of_month - timedelta(days=1)
        last_month_start = last_month_end.replace(day=1)
        
        summary = self.generate_billing_items(
            date_from=last_month_start,
            date_to=last_month_end
        )
        
        # Send notification to admins if errors
        if summary['errors'] > 0:
            admin_group = self.env.ref('academy_core.group_academy_manager', raise_if_not_found=False)
            if admin_group:
                for admin in admin_group.users:
                    self.env['mail.mail'].create({
                        'subject': f"Attendance Billing Errors - {last_month_start.strftime('%B %Y')}",
                        'body_html': f"""
                            <p>The monthly billing cron encountered {summary['errors']} errors:</p>
                            <ul>
                                {''.join(f"<li>{e['player']}: {e['error']}</li>" for e in summary['error_details'][:10])}
                            </ul>
                            <p>Please review the attendance records and billing items.</p>
                        """,
                        'email_to': admin.email,
                    })
        
        return summary


# Import logging for cron job
import logging
