from odoo import api, fields, models
from odoo.exceptions import ValidationError


class PlayerElevationWizard(models.TransientModel):
    _name = 'academy.player.elevation.wizard'
    _description = 'Player Elevation Wizard'

    player_id = fields.Many2one('academy.player', required=True, readonly=True)
    login = fields.Char(string='Login / Username')
    email = fields.Char(string='Portal Email')
    send_portal_welcome = fields.Boolean(default=True)
    assign_guardian_groups = fields.Boolean(
        string='Inherit Guardian Portal Groups',
        default=True,
        help='Also assign guardian portal groups if player should see sibling information.',
    )

    @api.model
    def default_get(self, fields_list):
        res = super().default_get(fields_list)
        player_id = res.get('player_id') or self.env.context.get('default_player_id')
        if player_id:
            player = self.env['academy.player'].browse(player_id)
            if player.exists():
                partner = player.partner_id  # type: ignore[attr-defined]
                email = getattr(partner, 'email', False)
                if 'login' in fields_list and email and 'login' not in res:
                    res['login'] = email
                if 'email' in fields_list and email and 'email' not in res:
                    res['email'] = email
        return res

    def action_confirm(self):
        self.ensure_one()
        player = self.player_id
        if not player:
            raise ValidationError('Player record is required.')
        partner = player.partner_id  # type: ignore[attr-defined]
        if player.portal_user_id:  # type: ignore[attr-defined]
            raise ValidationError('The player already has an associated user account.')
        if not player.elevation_allowed:  # type: ignore[attr-defined]
            raise ValidationError('Elevation is disabled for this player.')

        login = self.login or getattr(partner, 'email', False)
        email = self.email or getattr(partner, 'email', False)
        if not login or not email:
            raise ValidationError('A login and email are required to create a portal user.')

        groups = [self.env.ref('academy_core.group_academy_player_portal').id]
        if self.assign_guardian_groups:
            guardian_group = self.env.ref('academy_core.group_academy_guardian')
            groups.append(guardian_group.id)

        user_vals = {
            'name': partner.display_name,
            'login': login,
            'email': email,
            'partner_id': partner.id,
            'groups_id': [(6, 0, groups)],
        }
        user = self.env['res.users'].with_context(no_reset_password=not self.send_portal_welcome).create(user_vals)

        player.write({'portal_user_id': user.id})
        partner.write({'academy_is_player': True})

        if self.send_portal_welcome:
            user.action_reset_password()  # type: ignore[attr-defined]

        return {
            'type': 'ir.actions.act_window_close'
        }
