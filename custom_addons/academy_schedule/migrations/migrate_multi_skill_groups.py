#!/usr/bin/env python3
"""Migration script to populate skill_group_ids from skill_group_id."""
import sys
import os

# Add Odoo to path
sys.path.insert(0, os.path.dirname(__file__))

def migrate_multi_skill_groups():
    """Populate Many2many relationships from existing data."""
    import odoo
    from odoo import api, SUPERUSER_ID
    
    # Connect to database
    odoo.tools.config['db_name'] = 'odoo'
    odoo.tools.config['db_user'] = 'odoo'
    odoo.tools.config['db_password'] = 'letmein_n0w'
    odoo.tools.config['db_host'] = 'localhost'
    odoo.tools.config['db_port'] = 5432
    
    with api.Environment.manage():
        registry = odoo.registry('odoo')
        with registry.cursor() as cr:
            env = api.Environment(cr, SUPERUSER_ID, {})
            
            print("=" * 70)
            print("MULTI-SKILL GROUP MIGRATION")
            print("=" * 70)
            
            # Part 1: Session Templates
            print("\n1. Migrating Session Templates...")
            cr.execute("""
                INSERT INTO academy_session_template_skill_group_rel (template_id, skill_group_id)
                SELECT id, skill_group_id
                FROM academy_session_template
                WHERE skill_group_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM academy_session_template_skill_group_rel rel
                    WHERE rel.template_id = academy_session_template.id
                      AND rel.skill_group_id = academy_session_template.skill_group_id
                  )
            """)
            template_count = cr.rowcount
            print(f"   ✓ Migrated {template_count} session templates")
            
            # Part 2: Session Occurrences
            print("\n2. Migrating Session Occurrences...")
            cr.execute("""
                INSERT INTO academy_session_occurrence_skill_group_rel (occurrence_id, skill_group_id)
                SELECT id, skill_group_id
                FROM academy_session_occurrence
                WHERE skill_group_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM academy_session_occurrence_skill_group_rel rel
                    WHERE rel.occurrence_id = academy_session_occurrence.id
                      AND rel.skill_group_id = academy_session_occurrence.skill_group_id
                  )
            """)
            occurrence_count = cr.rowcount
            print(f"   ✓ Migrated {occurrence_count} session occurrences")
            
            # Part 3: Validation
            print("\n3. Validating migration...")
            cr.execute("""
                SELECT COUNT(*) 
                FROM academy_session_template t
                WHERE t.skill_group_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM academy_session_template_skill_group_rel rel
                    WHERE rel.template_id = t.id
                  )
            """)
            invalid_templates = cr.fetchone()[0]
            
            cr.execute("""
                SELECT COUNT(*) 
                FROM academy_session_occurrence o
                WHERE o.skill_group_id IS NOT NULL
                  AND NOT EXISTS (
                    SELECT 1 FROM academy_session_occurrence_skill_group_rel rel
                    WHERE rel.occurrence_id = o.id
                  )
            """)
            invalid_occurrences = cr.fetchone()[0]
            
            if invalid_templates == 0 and invalid_occurrences == 0:
                print("   ✓ All data migrated successfully")
                print(f"   ✓ 0 templates without many2many relationship")
                print(f"   ✓ 0 occurrences without many2many relationship")
            else:
                print(f"   ✗ VALIDATION FAILED!")
                print(f"   ✗ {invalid_templates} templates without many2many")
                print(f"   ✗ {invalid_occurrences} occurrences without many2many")
                cr.rollback()
                return False
            
            # Part 4: Summary
            print("\n4. Migration Summary:")
            cr.execute("""
                SELECT COUNT(*) as total_templates,
                       COUNT(DISTINCT skill_group_id) as distinct_skill_groups
                FROM academy_session_template
                WHERE skill_group_id IS NOT NULL
            """)
            t_total, t_groups = cr.fetchone()
            
            cr.execute("""
                SELECT COUNT(*) as total_occurrences,
                       COUNT(DISTINCT skill_group_id) as distinct_skill_groups
                FROM academy_session_occurrence
                WHERE skill_group_id IS NOT NULL
            """)
            o_total, o_groups = cr.fetchone()
            
            print(f"   • Total templates: {t_total} (across {t_groups} skill groups)")
            print(f"   • Total occurrences: {o_total} (across {o_groups} skill groups)")
            
            # Commit
            cr.commit()
            
            print("\n" + "=" * 70)
            print("MIGRATION COMPLETE!")
            print("=" * 70)
            return True

if __name__ == '__main__':
    success = migrate_multi_skill_groups()
    sys.exit(0 if success else 1)
