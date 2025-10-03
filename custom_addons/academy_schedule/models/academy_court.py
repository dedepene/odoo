"""Court model for tennis academy scheduling."""
from odoo import models, fields, api
from odoo.exceptions import ValidationError


class AcademyCourt(models.Model):
    """Tennis courts available for session scheduling."""
    
    _name = 'academy.court'
    _description = 'Tennis Court'
    _order = 'name'

    name = fields.Char(string='Court Name', required=True, help='e.g., Court 1, Court 2')
    code = fields.Char(string='Court Code', help='Short code for quick reference')
    surface_type = fields.Selection([
        ('hard', 'Hard Court'),
        ('clay', 'Clay Court'),
        ('grass', 'Grass Court'),
        ('synthetic', 'Synthetic'),
    ], string='Surface Type', default='hard')
    is_indoor = fields.Boolean(string='Indoor Court', default=False)
    active = fields.Boolean(string='Active', default=True)
    notes = fields.Text(string='Notes')
    
    _sql_constraints = [
        ('name_unique', 'unique(name)', 'Court name must be unique!'),
    ]

    def name_get(self):
        """Custom display name."""
        result = []
        for court in self:
            display_name = court.name
            if court.code:
                display_name = f"[{court.code}] {court.name}"
            result.append((court.id, display_name))
        return result
