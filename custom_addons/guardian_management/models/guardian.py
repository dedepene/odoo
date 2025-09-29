from odoo import models, fields, api
from odoo.exceptions import ValidationError


class Guardian(models.Model):
    _name = 'guardian.guardian'
    _description = 'Guardian/Parent Entity'
    _rec_name = 'display_name'

    # Basic Information
    name = fields.Char('Full Name', required=True)
    email = fields.Char('Email', required=True)
    phone = fields.Char('Phone Number')
    mobile = fields.Char('Mobile Number')
    
    # Address Information
    street = fields.Char('Street')
    street2 = fields.Char('Street 2')
    city = fields.Char('City')
    state_id = fields.Many2one('res.country.state', 'State')
    country_id = fields.Many2one('res.country', 'Country')
    zip = fields.Char('ZIP Code')
    
    # Account Status
    is_active = fields.Boolean('Account Active', default=True)
    user_id = fields.Many2one('res.users', 'Related User Account', 
                             help='Linked user account for login access')
    
    # Relationship with Kids
    kid_ids = fields.Many2many(
        'guardian.kid',
        'guardian_kid_rel',
        'guardian_id',
        'kid_id',
        string='Kids'
    )
    
    # Computed Fields
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True)
    kids_count = fields.Integer('Number of Kids', compute='_compute_kids_count')
    
    @api.depends('name', 'email')
    def _compute_display_name(self):
        for record in self:
            if record.name and record.email:
                record.display_name = f"{record.name} ({record.email})"
            else:
                record.display_name = record.name or record.email or 'Unnamed Guardian'
    
    @api.depends('kid_ids')
    def _compute_kids_count(self):
        for record in self:
            record.kids_count = len(record.kid_ids)

    def action_view_kids(self):
        """Action to view kids related to this guardian"""
        return {
            'name': 'My Kids',
            'type': 'ir.actions.act_window',
            'res_model': 'guardian.kid',
            'view_mode': 'list,form',
            'domain': [('guardian_ids', 'in', self.ids)],
            'context': {'default_guardian_ids': [(6, 0, self.ids)]},
        }

    def toggle_active(self):
        """Toggle the active status of the guardian"""
        for record in self:
            record.is_active = not record.is_active


class Kid(models.Model):
    _name = 'guardian.kid'
    _description = 'Kid/Child Entity'
    _rec_name = 'display_name'

    # Basic Information
    name = fields.Char('Full Name', required=True)
    birth_date = fields.Date('Birth Date')
    age = fields.Integer('Age', compute='_compute_age', store=True)
    gender = fields.Selection([
        ('male', 'Male'),
        ('female', 'Female'),
        ('other', 'Other')
    ], 'Gender')
    
    # Contact Information (optional for managed accounts)
    email = fields.Char('Email', help='Only if kid has managed account')
    phone = fields.Char('Phone Number', help='Only if kid has managed account')
    
    # Account Management
    has_managed_account = fields.Boolean('Has Managed Account', default=False)
    user_id = fields.Many2one('res.users', 'User Account', 
                             help='User account if kid has managed access')
    
    # Relationship with Guardians
    guardian_ids = fields.Many2many(
        'guardian.guardian',
        'guardian_kid_rel',
        'kid_id',
        'guardian_id',
        string='Guardians'
    )
    
    # Primary Guardian (optional - for cases where you need to identify main guardian)
    primary_guardian_id = fields.Many2one(
        'guardian.guardian',
        'Primary Guardian',
        help='Main guardian for this child'
    )
    
    # Additional Information
    notes = fields.Text('Notes')
    active = fields.Boolean('Active', default=True)
    
    # Computed Fields
    display_name = fields.Char('Display Name', compute='_compute_display_name', store=True)
    guardians_count = fields.Integer('Number of Guardians', compute='_compute_guardians_count')
    
    @api.depends('name', 'age')
    def _compute_display_name(self):
        for record in self:
            if record.name and record.age:
                record.display_name = f"{record.name} (Age: {record.age})"
            else:
                record.display_name = record.name or 'Unnamed Child'
    
    @api.depends('birth_date')
    def _compute_age(self):
        from datetime import date
        today = date.today()
        for record in self:
            if record.birth_date:
                record.age = today.year - record.birth_date.year - (
                    (today.month, today.day) < (record.birth_date.month, record.birth_date.day)
                )
            else:
                record.age = 0
    
    @api.depends('guardian_ids')
    def _compute_guardians_count(self):
        for record in self:
            record.guardians_count = len(record.guardian_ids)
    
    @api.constrains('primary_guardian_id', 'guardian_ids')
    def _check_primary_guardian(self):
        for record in self:
            if record.primary_guardian_id and record.primary_guardian_id not in record.guardian_ids:
                raise ValidationError(
                    "Primary guardian must be one of the assigned guardians."
                )

    def action_view_guardians(self):
        """Action to view guardians related to this kid"""
        return {
            'name': 'My Guardians',
            'type': 'ir.actions.act_window',
            'res_model': 'guardian.guardian',
            'view_mode': 'list,form',
            'domain': [('kid_ids', 'in', self.ids)],
            'context': {'default_kid_ids': [(6, 0, self.ids)]},
        }


class GuardianKidRelationship(models.Model):
    _name = 'guardian.kid.relationship'
    _description = 'Guardian-Kid Relationship Details'
    _rec_name = 'display_name'

    guardian_id = fields.Many2one('guardian.guardian', 'Guardian', required=True)
    kid_id = fields.Many2one('guardian.kid', 'Kid', required=True)
    
    # Relationship Details
    relationship_type = fields.Selection([
        ('parent', 'Parent'),
        ('guardian', 'Legal Guardian'),
        ('grandparent', 'Grandparent'),
        ('foster', 'Foster Parent'),
        ('relative', 'Other Relative'),
        ('other', 'Other')
    ], 'Relationship Type', default='parent', required=True)
    
    # Legal and Contact Permissions
    has_legal_custody = fields.Boolean('Has Legal Custody', default=True)
    can_pick_up = fields.Boolean('Can Pick Up Child', default=True)
    emergency_contact = fields.Boolean('Emergency Contact', default=True)
    can_make_decisions = fields.Boolean('Can Make Decisions', default=True)
    
    # Contact Preferences
    preferred_contact_method = fields.Selection([
        ('email', 'Email'),
        ('phone', 'Phone'),
        ('mobile', 'Mobile'),
        ('mail', 'Mail')
    ], 'Preferred Contact Method', default='email')
    
    # Dates
    relationship_start_date = fields.Date('Relationship Start Date', default=fields.Date.today)
    relationship_end_date = fields.Date('Relationship End Date')
    
    # Status
    active = fields.Boolean('Active', default=True)
    notes = fields.Text('Notes')
    
    # Computed Fields
    display_name = fields.Char('Display Name', compute='_compute_display_name')
    
    @api.depends('guardian_id.name', 'kid_id.name', 'relationship_type')
    def _compute_display_name(self):
        for record in self:
            guardian_name = record.guardian_id.name or 'Unknown Guardian'
            kid_name = record.kid_id.name or 'Unknown Kid'
            relationship = dict(record._fields['relationship_type'].selection).get(
                record.relationship_type, 'Unknown'
            )
            record.display_name = f"{guardian_name} - {kid_name} ({relationship})"
    
    @api.model
    def create(self, vals):
        """Create relationship and sync Many2many fields"""
        relationship = super().create(vals)
        relationship._sync_many2many()
        return relationship
    
    def write(self, vals):
        """Update relationship and sync Many2many fields"""
        result = super().write(vals)
        if 'guardian_id' in vals or 'kid_id' in vals:
            for record in self:
                record._sync_many2many()
        return result
    
    def unlink(self):
        """Delete relationship and sync Many2many fields"""
        # Store relationships before deletion
        relationships_data = []
        for record in self:
            relationships_data.append((record.guardian_id, record.kid_id))
        
        result = super().unlink()
        
        # Update Many2many after deletion
        for guardian, kid in relationships_data:
            if guardian and kid:
                guardian.write({'kid_ids': [(3, kid.id)]})  # Remove from Many2many
        
        return result
    
    def _sync_many2many(self):
        """Synchronize Many2many relationships"""
        for record in self:
            if record.guardian_id and record.kid_id:
                # Add to Many2many if not already there
                if record.kid_id not in record.guardian_id.kid_ids:
                    record.guardian_id.write({'kid_ids': [(4, record.kid_id.id)]})
                if record.guardian_id not in record.kid_id.guardian_ids:
                    record.kid_id.write({'guardian_ids': [(4, record.guardian_id.id)]})
    
    _sql_constraints = [
        ('unique_guardian_kid', 
         'UNIQUE(guardian_id, kid_id)', 
         'A guardian-kid relationship already exists!')
    ]