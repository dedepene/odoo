-- Multi-Skill Group Sessions Migration
-- Populate skill_group_ids from skill_group_id for backward compatibility
-- Run AFTER adding new fields, BEFORE deploying new business logic

-- ======================================================================
-- PART 1: Populate Many2many relationships from existing data
-- ======================================================================

-- Session Templates: Populate skill_group_ids from skill_group_id
INSERT INTO academy_session_template_skill_group_rel (template_id, skill_group_id)
SELECT id, skill_group_id
FROM academy_session_template
WHERE skill_group_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM academy_session_template_skill_group_rel rel
    WHERE rel.template_id = academy_session_template.id
      AND rel.skill_group_id = academy_session_template.skill_group_id
  );

-- Session Occurrences: Populate skill_group_ids from skill_group_id
INSERT INTO academy_session_occurrence_skill_group_rel (occurrence_id, skill_group_id)
SELECT id, skill_group_id
FROM academy_session_occurrence
WHERE skill_group_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM academy_session_occurrence_skill_group_rel rel
    WHERE rel.occurrence_id = academy_session_occurrence.id
      AND rel.skill_group_id = academy_session_occurrence.skill_group_id
  );

-- ======================================================================
-- PART 2: Validation queries to check data integrity
-- ======================================================================

-- Check for templates with skill_group_id but no skill_group_ids relationship
SELECT COUNT(*) as templates_without_many2many
FROM academy_session_template t
WHERE t.skill_group_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM academy_session_template_skill_group_rel rel
    WHERE rel.template_id = t.id
  );
-- Expected: 0

-- Check for occurrences with skill_group_id but no skill_group_ids relationship
SELECT COUNT(*) as occurrences_without_many2many
FROM academy_session_occurrence o
WHERE o.skill_group_id IS NOT NULL
  AND NOT EXISTS (
    SELECT 1 FROM academy_session_occurrence_skill_group_rel rel
    WHERE rel.occurrence_id = o.id
  );
-- Expected: 0

-- ======================================================================
-- PART 3: Summary statistics
-- ======================================================================

-- Total templates migrated
SELECT COUNT(*) as total_templates,
       COUNT(DISTINCT skill_group_id) as distinct_skill_groups
FROM academy_session_template
WHERE skill_group_id IS NOT NULL;

-- Total occurrences migrated
SELECT COUNT(*) as total_occurrences,
       COUNT(DISTINCT skill_group_id) as distinct_skill_groups
FROM academy_session_occurrence
WHERE skill_group_id IS NOT NULL;

-- ======================================================================
-- Migration complete!
-- ======================================================================
