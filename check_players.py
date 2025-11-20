#!/usr/bin/env python3
"""Query player data from Odoo database."""

import sys
sys.path.insert(0, 'd:\\Code\\projects\\odoo\\odoo')

import odoo
from odoo import registry, api

# Parse config
odoo.tools.config.parse_config(['-c', 'odoo.conf'])

# Get database registry
db = registry('odoo')

with db.cursor() as cr:
    env = api.Environment(cr, odoo.SUPERUSER_ID, {})
    
    # Query players with IDs 6 and 7
    players = env['academy.player'].search([('id', 'in', [6, 7])])
    
    print("Player Data:")
    print("-" * 50)
    for player in players:
        print(f"ID: {player.id}")
        print(f"Name: {player.name}")
        print(f"Partner ID: {player.partner_id.id if player.partner_id else 'None'}")
        print(f"Partner Name: {player.partner_id.name if player.partner_id else 'None'}")
        print("-" * 50)
