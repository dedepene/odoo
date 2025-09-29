#!/usr/bin/env python3
"""
Script to add current user to Guardian Manager group
Run this with: python add_guardian_manager.py
"""

import sys
import os

# Add odoo directory to path
sys.path.insert(0, os.path.dirname(__file__))

import odoo
from odoo import api, SUPERUSER_ID

def add_user_to_guardian_manager():
    # Configure Odoo
    odoo.tools.config.parse_config([
        '--database=odoo',
        '--db_user=odoo',
        '--db_password=letmein_n0w',
        '--addons-path=./addons,./custom_addons'
    ])
    
    # Initialize database
    with odoo.registry('odoo').cursor() as cr:
        env = api.Environment(cr, SUPERUSER_ID, {})
        
        # Find Guardian Manager group
        guardian_manager = env.ref('guardian_management.group_guardian_manager', False)
        if not guardian_manager:
            print("Guardian Manager group not found!")
            return
            
        # Find your user (replace with your actual login/email)
        user_email = input("Enter your user email: ")
        user = env['res.users'].search([('login', '=', user_email)], limit=1)
        if not user:
            user = env['res.users'].search([('email', '=', user_email)], limit=1)
        
        if not user:
            print(f"User {user_email} not found!")
            return
            
        # Add user to group
        guardian_manager.write({'users': [(4, user.id)]})
        cr.commit()
        
        print(f"Successfully added {user.name} to Guardian Manager group!")

if __name__ == "__main__":
    add_user_to_guardian_manager()