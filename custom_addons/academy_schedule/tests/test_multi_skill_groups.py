# -*- coding: utf-8 -*-
"""Tests for multi-skill group session functionality."""

from datetime import date, timedelta
from odoo.tests import TransactionCase, tagged
from odoo.exceptions import ValidationError


@tagged('academy_schedule', 'multi_skill')
class TestMultiSkillGroupSessions(TransactionCase):
    """Test multi-skill group session functionality."""

    def setUp(self):
        super().setUp()
        
        # Create skill groups
        self.green_group = self.env['academy.skill.group'].create({
            'name': 'Green Ball',
            'code': 'GREEN',
            'min_age': 8,
            'max_age': 10,
        })
        
        self.orange_group = self.env['academy.skill.group'].create({
            'name': 'Orange Ball',
            'code': 'ORANGE',
            'min_age': 10,
            'max_age': 12,
        })
        
        # Create season
        today = date.today()
        self.season = self.env['academy.season'].create({
            'name': 'Test Season 2025',
            'start_date': today,
            'end_date': today + timedelta(days=90),
            'active': True,
        })
        
        # Create court
        self.court = self.env['academy.court'].create({
            'name': 'Court 1',
            'active': True,
        })
        
        # Create billing template
        self.billing_template = self.env['academy.billing.template'].create({
            'name': 'Test Billing Template',
            'billing_frequency': 'monthly',
            'billing_day': 1,
        })
        
        # Create guardians
        self.guardian1 = self.env['res.partner'].create({
            'name': 'Guardian 1',
            'email': 'guardian1@test.com',
            'phone': '+1234567890',
            'academy_is_guardian': True,
        })
        
        self.guardian2 = self.env['res.partner'].create({
            'name': 'Guardian 2',
            'email': 'guardian2@test.com',
            'mobile': '+0987654321',
            'academy_is_guardian': True,
        })
        
        # Create players with guardians
        self.green_player1 = self.env['academy.player'].create({
            'name': 'Green Player 1',
            'dob': today - timedelta(days=365 * 9),
            'skill_group_id': self.green_group.id,
            'primary_guardian_id': self.guardian1.id,
            'guardian_ids': [(6, 0, [self.guardian1.id])],
        })
        
        self.green_player2 = self.env['academy.player'].create({
            'name': 'Green Player 2',
            'dob': today - timedelta(days=365 * 9),
            'skill_group_id': self.green_group.id,
            'primary_guardian_id': self.guardian1.id,
            'guardian_ids': [(6, 0, [self.guardian1.id])],
        })
        
        self.orange_player1 = self.env['academy.player'].create({
            'name': 'Orange Player 1',
            'dob': today - timedelta(days=365 * 11),
            'skill_group_id': self.orange_group.id,
            'primary_guardian_id': self.guardian2.id,
            'guardian_ids': [(6, 0, [self.guardian2.id])],
        })
        
        self.orange_player2 = self.env['academy.player'].create({
            'name': 'Orange Player 2',
            'dob': today - timedelta(days=365 * 11),
            'skill_group_id': self.orange_group.id,
            'primary_guardian_id': self.guardian2.id,
            'guardian_ids': [(6, 0, [self.guardian2.id])],
        })

    def test_multi_skill_template_creation(self):
        """Test creating a multi-skill template."""
        template = self.env['academy.session.template'].create({
            'season_id': self.season.id,
            'multi_skill_mode': True,
            'skill_group_ids': [(6, 0, [self.green_group.id, self.orange_group.id])],
            'day_of_week': '0',  # Monday
            'start_time': 17.0,
            'end_time': 18.0,
            'session_type': 'physical_group',
            'court_ids': [(6, 0, [self.court.id])],
            'billing_template_id': self.billing_template.id,
        })
        
        self.assertTrue(template.multi_skill_mode)
        self.assertEqual(len(template.skill_group_ids), 2)
        self.assertIn(self.green_group, template.skill_group_ids)
        self.assertIn(self.orange_group, template.skill_group_ids)
        self.assertEqual(template.primary_skill_group_id, self.green_group)

    def test_multi_skill_template_requires_skill_groups(self):
        """Test that multi-skill mode requires skill groups."""
        with self.assertRaises(ValidationError):
            self.env['academy.session.template'].create({
                'season_id': self.season.id,
                'multi_skill_mode': True,
                'skill_group_ids': [(6, 0, [])],  # Empty
                'day_of_week': '0',
                'start_time': 17.0,
                'end_time': 18.0,
                'session_type': 'physical_group',
                'court_ids': [(6, 0, [self.court.id])],
                'billing_template_id': self.billing_template.id,
            })

    def test_single_skill_template_requires_skill_group(self):
        """Test that single-skill mode requires a skill group."""
        with self.assertRaises(ValidationError):
            self.env['academy.session.template'].create({
                'season_id': self.season.id,
                'multi_skill_mode': False,
                'skill_group_id': False,  # Empty
                'day_of_week': '0',
                'start_time': 17.0,
                'end_time': 18.0,
                'session_type': 'tennis_group',
                'court_ids': [(6, 0, [self.court.id])],
                'billing_template_id': self.billing_template.id,
            })

    def test_multi_skill_occurrence_generation(self):
        """Test that multi-skill occurrences inherit multiple skill groups."""
        template = self.env['academy.session.template'].create({
            'season_id': self.season.id,
            'multi_skill_mode': True,
            'skill_group_ids': [(6, 0, [self.green_group.id, self.orange_group.id])],
            'day_of_week': '0',  # Monday
            'start_time': 17.0,
            'end_time': 18.0,
            'session_type': 'physical_group',
            'court_ids': [(6, 0, [self.court.id])],
            'billing_template_id': self.billing_template.id,
        })
        
        # Generate occurrences
        count = template.generate_occurrences()
        self.assertGreater(count, 0)
        
        # Check first occurrence
        occurrence = self.env['academy.session.occurrence'].search([
            ('template_id', '=', template.id)
        ], limit=1)
        
        self.assertTrue(occurrence.multi_skill_mode)
        self.assertEqual(len(occurrence.skill_group_ids), 2)
        self.assertIn(self.green_group, occurrence.skill_group_ids)
        self.assertIn(self.orange_group, occurrence.skill_group_ids)
        self.assertEqual(occurrence.skill_group_id, self.green_group)

    def test_multi_skill_registered_players(self):
        """Test that _get_registered_players returns players from all skill groups."""
        # Create multi-skill occurrence
        occurrence = self.env['academy.session.occurrence'].create({
            'season_id': self.season.id,
            'multi_skill_mode': True,
            'skill_group_ids': [(6, 0, [self.green_group.id, self.orange_group.id])],
            'skill_group_id': self.green_group.id,
            'date': date.today() + timedelta(days=7),
            'start_datetime': '2025-10-31 17:00:00',
            'end_datetime': '2025-10-31 18:00:00',
            'session_type': 'physical_group',
            'court_ids': [(6, 0, [self.court.id])],
        })
        
        # Get registered players
        players = occurrence._get_registered_players()
        
        # Should have 4 players (2 green + 2 orange)
        self.assertEqual(len(players), 4)
        self.assertIn(self.green_player1, players)
        self.assertIn(self.green_player2, players)
        self.assertIn(self.orange_player1, players)
        self.assertIn(self.orange_player2, players)

    def test_single_skill_registered_players(self):
        """Test that single-skill sessions only return players from one group."""
        # Create single-skill occurrence
        occurrence = self.env['academy.session.occurrence'].create({
            'season_id': self.season.id,
            'multi_skill_mode': False,
            'skill_group_id': self.green_group.id,
            'skill_group_ids': [(6, 0, [self.green_group.id])],
            'date': date.today() + timedelta(days=7),
            'start_datetime': '2025-10-31 17:00:00',
            'end_datetime': '2025-10-31 18:00:00',
            'session_type': 'tennis_group',
            'court_ids': [(6, 0, [self.court.id])],
        })
        
        # Get registered players
        players = occurrence._get_registered_players()
        
        # Should have 2 players (only green)
        self.assertEqual(len(players), 2)
        self.assertIn(self.green_player1, players)
        self.assertIn(self.green_player2, players)
        self.assertNotIn(self.orange_player1, players)
        self.assertNotIn(self.orange_player2, players)

    def test_multi_skill_attendance_validation_accepts_all_groups(self):
        """Test that attendance validation allows players from any linked skill group."""
        # Create multi-skill occurrence
        occurrence = self.env['academy.session.occurrence'].create({
            'season_id': self.season.id,
            'multi_skill_mode': True,
            'skill_group_ids': [(6, 0, [self.green_group.id, self.orange_group.id])],
            'skill_group_id': self.green_group.id,
            'date': date.today() + timedelta(days=7),
            'start_datetime': '2025-10-31 17:00:00',
            'end_datetime': '2025-10-31 18:00:00',
            'session_type': 'physical_group',
            'court_ids': [(6, 0, [self.court.id])],
        })
        
        # Create attendance for green player - should succeed
        attendance1 = self.env['academy.attendance'].create({
            'session_id': occurrence.id,
            'player_id': self.green_player1.id,
            'state': 'present',
        })
        self.assertTrue(attendance1.exists())
        
        # Create attendance for orange player - should succeed
        attendance2 = self.env['academy.attendance'].create({
            'session_id': occurrence.id,
            'player_id': self.orange_player1.id,
            'state': 'present',
        })
        self.assertTrue(attendance2.exists())

    def test_multi_skill_attendance_validation_rejects_wrong_group(self):
        """Test that attendance validation rejects players from non-linked skill groups."""
        # Create another skill group
        red_group = self.env['academy.skill.group'].create({
            'name': 'Red Ball',
            'code': 'RED',
            'min_age': 12,
            'max_age': 14,
        })
        
        red_player = self.env['academy.player'].create({
            'name': 'Red Player 1',
            'dob': date.today() - timedelta(days=365 * 13),
            'skill_group_id': red_group.id,
            'primary_guardian_id': self.guardian1.id,
            'guardian_ids': [(6, 0, [self.guardian1.id])],
        })
        
        # Create multi-skill occurrence (only green + orange)
        occurrence = self.env['academy.session.occurrence'].create({
            'season_id': self.season.id,
            'multi_skill_mode': True,
            'skill_group_ids': [(6, 0, [self.green_group.id, self.orange_group.id])],
            'skill_group_id': self.green_group.id,
            'date': date.today() + timedelta(days=7),
            'start_datetime': '2025-10-31 17:00:00',
            'end_datetime': '2025-10-31 18:00:00',
            'session_type': 'physical_group',
            'court_ids': [(6, 0, [self.court.id])],
        })
        
        # Try to create attendance for red player - should fail
        with self.assertRaises(ValidationError):
            self.env['academy.attendance'].create({
                'session_id': occurrence.id,
                'player_id': red_player.id,
                'state': 'present',
            })

    def test_single_skill_attendance_validation(self):
        """Test that single-skill validation still works."""
        # Create single-skill occurrence
        occurrence = self.env['academy.session.occurrence'].create({
            'season_id': self.season.id,
            'multi_skill_mode': False,
            'skill_group_id': self.green_group.id,
            'skill_group_ids': [(6, 0, [self.green_group.id])],
            'date': date.today() + timedelta(days=7),
            'start_datetime': '2025-10-31 17:00:00',
            'end_datetime': '2025-10-31 18:00:00',
            'session_type': 'tennis_group',
            'court_ids': [(6, 0, [self.court.id])],
        })
        
        # Green player should succeed
        attendance1 = self.env['academy.attendance'].create({
            'session_id': occurrence.id,
            'player_id': self.green_player1.id,
            'state': 'present',
        })
        self.assertTrue(attendance1.exists())
        
        # Orange player should fail
        with self.assertRaises(ValidationError):
            self.env['academy.attendance'].create({
                'session_id': occurrence.id,
                'player_id': self.orange_player1.id,
                'state': 'present',
            })

    def test_billing_with_multi_skill_session(self):
        """Test that billing works correctly with multi-skill sessions."""
        # Create multi-skill occurrence
        occurrence = self.env['academy.session.occurrence'].create({
            'season_id': self.season.id,
            'multi_skill_mode': True,
            'skill_group_ids': [(6, 0, [self.green_group.id, self.orange_group.id])],
            'skill_group_id': self.green_group.id,
            'date': date.today() + timedelta(days=7),
            'start_datetime': '2025-10-31 17:00:00',
            'end_datetime': '2025-10-31 18:00:00',
            'session_type': 'physical_group',
            'court_ids': [(6, 0, [self.court.id])],
        })
        
        # Get registered players
        players = occurrence._get_registered_players()
        
        # Billing should count all 4 players
        self.assertEqual(len(players), 4)
        
        # Check that billing pricing works
        if hasattr(self.env['academy.billing.pricing.mixin'], '_get_session_pricing'):
            pricing_mixin = self.env['academy.billing.pricing.mixin']
            price = pricing_mixin._get_session_pricing(occurrence)
            self.assertGreater(price, 0)
            # Physical group sessions should be priced
            self.assertEqual(price, 20.0)  # As per attendance_billing_cron.xml
