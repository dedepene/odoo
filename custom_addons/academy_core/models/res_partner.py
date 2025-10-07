from odoo import fields, models, api
from odoo.exceptions import ValidationError


class ResPartner(models.Model):
    _inherit = ['res.partner']

    academy_is_guardian = fields.Boolean(string='Academy Guardian')
    academy_is_player = fields.Boolean(string='Academy Player')
    mobile = fields.Char(string='Mobile')
    academy_guardian_child_ids = fields.Many2many(
        'academy.player',
        'academy_player_guardian_rel',
        'guardian_id',
        'player_id',
        string='Academy Children',
        readonly=True,
    )
    academy_primary_player_ids = fields.One2many(
        'academy.player',
        'primary_guardian_id',
        string='Primary Player Relationships',
        readonly=True,
    )

    def action_invite_guardian_to_portal(self):
        """Invite this guardian to the portal by creating a linked res.users and sending an invite.

        Behaviour:
        - Validates an email exists on the partner.
        - Ensures there isn't already a user with the same login/email (case-insensitive).
        - Creates the user linked to this partner, assigns portal and guardian groups.
        - Sends a single portal invitation email with signup token.
        - Posts a chatter message on the partner record about the invite.
        """
        self.ensure_one()
        email = (self.email or '').strip()
        if not email:
            raise ValidationError('Guardian must have an email address to be invited to the portal.')

        # Case-insensitive uniqueness check on login/email
        users = self.env['res.users'].search([('login', '!=', False)])
        for u in users:
            login = (u.login or '').strip()
            if login and login.lower() == email.lower():
                raise ValidationError('A user already exists with this login/email: %s' % login)

        # Get groups: portal + academy guardian group
        portal_group = self.env.ref('base.group_portal', raise_if_not_found=False)
        group_public = self.env.ref('base.group_public', raise_if_not_found=False)
        guardian_group = self.env.ref('academy_core.group_academy_guardian', raise_if_not_found=False)
        
        group_ids = []
        if portal_group:
            group_ids.append((4, portal_group.id))
        if guardian_group:
            group_ids.append((4, guardian_group.id))
        if group_public:
            group_ids.append((3, group_public.id))  # Remove public group

        # Create the user with no_reset_password context to prevent automatic password email
        user_vals = {
            'name': self.name or email,
            'login': email,
            'email': email,
            'partner_id': self.id,
            'active': True,
            'group_ids': group_ids,
        }
        user = self.env['res.users'].with_context(no_reset_password=True).create(user_vals)

        # Prepare signup token for the partner
        self.signup_prepare()

        # Send the portal invitation email using the proper template
        template = self.env.ref('auth_signup.portal_set_password_email', raise_if_not_found=False)
        if template:
            try:
                template.with_context(
                    dbname=self.env.cr.dbname,
                    lang=user.sudo().lang,
                    welcome_message='You have been invited to access the academy portal.',
                    medium='portalinvite'
                ).send_mail(user.id, force_send=True)
            except Exception as e:
                # Don't fail the whole flow if mail sending fails
                self.message_post(body='Portal user created but invitation email failed to send: %s' % str(e))
        
        # Post chatter message
        self.message_post(body='Portal access granted and invitation sent to %s.' % email)
        return user
