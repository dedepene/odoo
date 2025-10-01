from odoo import api, fields, models
from odoo.exceptions import ValidationError


class AcademySkillGroup(models.Model):
    _name = 'academy.skill.group'
    _description = 'Academy Skill Group'
    _order = 'sequence, name'

    name = fields.Char(required=True)
    code = fields.Char(required=True, help='Short unique code used for references and integrations.')
    description = fields.Text()
    sequence = fields.Integer(default=10)
    min_age = fields.Integer(string='Minimum Age', help='Inclusive minimum age (years) for this skill group.')
    max_age = fields.Integer(string='Maximum Age', help='Inclusive maximum age (years) for this skill group. Leave empty if open-ended.')
    enforce_age_range = fields.Boolean(default=True)
    capacity = fields.Integer(string='Suggested Capacity')
    active = fields.Boolean(default=True)

    _sql_constraints = [
        ('academy_skill_group_code_unique', 'unique(code)', 'The skill group code must be unique.'),
        ('academy_skill_group_name_unique', 'unique(name)', 'The skill group name must be unique.'),
    ]

    @api.constrains('min_age', 'max_age')
    def _check_age_bounds(self):
        for group in self:
            if group.min_age and group.min_age < 0:
                raise ValidationError('Minimum age cannot be negative.')
            if group.max_age and group.max_age < 0:
                raise ValidationError('Maximum age cannot be negative.')
            if group.min_age and group.max_age and group.min_age > group.max_age:
                raise ValidationError('Minimum age cannot be greater than maximum age.')

    def allows_age(self, age_years: float) -> bool:
        self.ensure_one()
        if not self.enforce_age_range:
            return True
        if self.min_age and age_years < self.min_age:
            return False
        if self.max_age and age_years > self.max_age:
            return False
        return True
