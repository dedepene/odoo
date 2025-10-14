from datetime import date
from typing import List

from dateutil.relativedelta import relativedelta

from odoo import api, fields, models
from odoo.exceptions import ValidationError
from odoo.tools import frozendict


class AcademyPlayer(models.Model):
    _name = 'academy.player'
    _description = 'Academy Player'
    _inherits = frozendict({'res.partner': 'partner_id'})
    _order = 'reference, partner_id'

    partner_id = fields.Many2one('res.partner', required=True, ondelete='cascade', index=True)
    name = fields.Char(related='partner_id.name', store=True, readonly=False)
    email = fields.Char(related='partner_id.email', store=True, readonly=False)
    phone = fields.Char(related='partner_id.phone', store=True, readonly=False)
    mobile = fields.Char(related='partner_id.mobile', store=True, readonly=False)
    street = fields.Char(related='partner_id.street', store=True, readonly=False)
    street2 = fields.Char(related='partner_id.street2', store=True, readonly=False)
    city = fields.Char(related='partner_id.city', store=True, readonly=False)
    zip = fields.Char(related='partner_id.zip', store=True, readonly=False)
    country_id = fields.Many2one('res.country', related='partner_id.country_id', store=True, readonly=False)
    reference = fields.Char(readonly=True, copy=False)
    dob = fields.Date(string='Date of Birth', required=True)
    age_years = fields.Float(string='Age (Years)', compute='_compute_age', store=True)
    skill_group_id = fields.Many2one('academy.skill.group', required=True, index=True)
    guardian_ids = fields.Many2many(
        'res.partner',
        'academy_player_guardian_rel',
        'player_id',
        'guardian_id',
        string='Guardians',
        domain=[('academy_is_guardian', '=', True)],
    )
    primary_guardian_id = fields.Many2one(
        'res.partner',
        string='Primary Guardian',
        domain=[('academy_is_guardian', '=', True)],
        required=True,
    )
    lead_coach_id = fields.Many2one(
        'res.users',
        string='Lead Coach',
        domain=[('academy_is_coach', '=', True)],
    )
    portal_user_id = fields.Many2one('res.users', string='Portal User', readonly=True, copy=False)
    elevation_allowed = fields.Boolean(string='Allow Elevation', default=True)
    notes = fields.Text()
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('academy_player_partner_unique', 'unique(partner_id)', 'A player already exists for this contact.'),
    ]

    def name_get(self):
        """
        Custom name display for players with skill group prefix.
        Format: [Skill Group] Player Name
        If multiple players have same name and skill group, add primary guardian name.
        """
        result = []
        for player in self:
            skill_prefix = f"[{player.skill_group_id.name}]" if player.skill_group_id else ""
            base_name = f"{skill_prefix} {player.name}".strip()
            
            # Check for duplicates (same name + skill group)
            if player.skill_group_id:
                duplicates = self.search([
                    ('id', '!=', player.id),
                    ('name', '=', player.name),
                    ('skill_group_id', '=', player.skill_group_id.id),
                    ('active', '=', True)
                ])
                
                if duplicates:
                    # Add primary guardian name in brackets
                    guardian_name = player.primary_guardian_id.name if player.primary_guardian_id else "No Guardian"
                    base_name = f"{base_name} ({guardian_name})"
            
            result.append((player.id, base_name))
        
        return result

    @api.depends('dob')
    def _compute_age(self):
        today = date.today()
        for player in self:
            if player.dob:
                delta = relativedelta(today, player.dob)
                player.age_years = delta.years + (delta.months / 12) + (delta.days / 365.0)
            else:
                player.age_years = 0.0

    def _prepare_player_create_vals(self, vals):
        prepared = dict(vals)
        if not prepared.get('partner_id'):
            partner_vals = {
                'name': prepared.get('name') or 'New Player',
                'company_type': 'person',
                'is_company': False,
            }
            partner = self.env['res.partner'].create(partner_vals)
            prepared['partner_id'] = partner.id
        return prepared

    @api.model
    def create(self, vals_list):
        if isinstance(vals_list, list):
            prepared_vals = [self._prepare_player_create_vals(vals) for vals in vals_list]
        else:
            prepared_vals = [self._prepare_player_create_vals(vals_list)]

        players = super().create(prepared_vals)
        players._assign_sequence_if_needed()
        players._mark_related_partners()
        players._validate_guardians_contact_info()
        return players[0] if isinstance(vals_list, dict) else players

    def write(self, vals):
        res = super().write(vals)
        self._assign_sequence_if_needed()
        self._mark_related_partners()
        self._validate_guardians_contact_info()
        return res

    def _assign_sequence_if_needed(self):
        for player in self.filtered(lambda rec: not rec.reference):
            player.reference = player.env['ir.sequence'].next_by_code('academy.player')  # type: ignore[attr-defined]

    def _mark_related_partners(self):
        for player in self:
            if player.partner_id:
                player.partner_id.write({'academy_is_player': True})
            if player.guardian_ids:
                player.guardian_ids.write({'academy_is_guardian': True})

    def _validate_guardians_contact_info(self):
        for player in self:
            missing_names: List[str] = []
            for guardian in player.guardian_ids:
                email = getattr(guardian, 'email', False)
                phone = getattr(guardian, 'phone', False) or getattr(guardian, 'mobile', False)
                display_label = str(guardian.display_name or guardian.id)
                if not email or not phone:
                    missing_names.append(display_label)
            if missing_names:
                raise ValidationError(
                    'Each guardian must have an email and a phone or mobile number set. Missing for: %s'
                    % ', '.join(str(name) for name in missing_names)
                )

    @api.constrains('dob')
    def _check_dob_not_future(self):
        today = fields.Date.today()
        for player in self:
            if player.dob and player.dob > today:
                raise ValidationError('The date of birth cannot be in the future.')

    @api.constrains('guardian_ids', 'primary_guardian_id')
    def _check_guardians(self):
        for player in self:
            if not player.guardian_ids:
                raise ValidationError('Each player must have at least one guardian.')
            if player.primary_guardian_id not in player.guardian_ids:
                raise ValidationError('The primary guardian must be among the assigned guardians.')

    @api.constrains('skill_group_id', 'dob')
    def _check_skill_group_age_alignment(self):
        today = fields.Date.today()
        for player in self:
            if not player.skill_group_id or not player.dob:
                continue
            group_vals = player.skill_group_id.read(['enforce_age_range', 'min_age', 'max_age', 'name'])[0]
            if not group_vals.get('enforce_age_range'):
                continue
            delta = relativedelta(today, player.dob)
            age_years = delta.years + (delta.months / 12) + (delta.days / 365.0)
            min_age = group_vals.get('min_age') or None
            max_age = group_vals.get('max_age') or None
            if min_age and age_years < min_age:
                raise ValidationError(
                    'Player %s is %.1f years old and younger than the minimum of %s for group %s.'
                    % (
                        player.display_name or player.partner_id.display_name,
                        age_years,
                        min_age,
                        group_vals.get('name'),
                    )
                )
            if max_age and age_years > max_age:
                raise ValidationError(
                    'Player %s is %.1f years old and older than the maximum of %s for group %s.'
                    % (
                        player.display_name or player.partner_id.display_name,
                        age_years,
                        max_age,
                        group_vals.get('name'),
                    )
                )

    def action_open_elevation_wizard(self):
        self.ensure_one()
        return {
            'name': 'Elevate Player',
            'type': 'ir.actions.act_window',
            'res_model': 'academy.player.elevation.wizard',
            'view_mode': 'form',
            'target': 'new',
            'context': {
                'default_player_id': self.id,
            },
        }

    def action_invite_primary_guardian(self):
        """Invite the primary guardian (if set) to the portal.

        This delegates to the partner method and posts a chatter message on the player.
        """
        self.ensure_one()
        guardian = self.primary_guardian_id
        if not guardian:
            raise ValidationError('This player has no primary guardian to invite.')
        try:
            user = guardian.action_invite_guardian_to_portal()
        except Exception as e:
            # Propagate useful errors (e.g., ValidationError about email/duplicate)
            raise
        # Post message on player record
        self.message_post(body='An invitation to the portal was sent to guardian %s.' % (guardian.email or guardian.name))
        # Also link portal_user_id to created user if not set
        if user and not self.portal_user_id:
            # if the created user was intended as a player portal (not guardian), we still store for visibility
            try:
                self.portal_user_id = user.id
            except Exception:
                pass
        return True
