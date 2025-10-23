{
    'name': 'Academy Schedule',
    'version': '19.0.1.0.0',
    'summary': 'Session scheduling and calendar management for Tennis Academy',
    'description': '''
        Comprehensive scheduling module for tennis academy including:
        - Courts and court allocation management
        - Season definition and management
        - Weekly recurring session templates
        - Automatic occurrence generation from templates
        - Individual session booking with conflict detection
        - Absence reporting and tracking
        - Season suspension for dome installation or tournaments
        - Calendar visibility scoping by role
        - Follow-up physical training session auto-linking
    ''',
    'author': 'dedepene',
    'website': 'https://example.com',
    'category': 'Education',
    'depends': ['academy_core', 'calendar'],
    'data': [
        'security/ir.model.access.csv',
        'data/session_type_data.xml',
        
        # Views - Actions must be defined before menus reference them
        'views/attendance_views.xml', # Defines action_academy_attendance
        'views/academy_court_views.xml', # Defines action_academy_court
        'views/academy_season_views.xml', # Defines action_academy_season_suspension
        'views/academy_session_template_views.xml',
        'views/academy_session_occurrence_views.xml', # Defines action_academy_today_sessions, action_academy_session_occurrence
        'views/academy_session_absence_views.xml', # Defines action_academy_session_absence
        
        # Wizards - Actions must be defined before menus reference them
        'wizard/weekly_schedule_wizard_views.xml',
        'wizard/individual_session_wizard_views.xml', # Defines action_individual_session_wizard
        'wizard/suspension_wizard_views.xml',
        'views/attendance_wizard_views.xml',
        
        # Menus MUST be loaded LAST - they reference all the actions defined above
        'views/academy_schedule_menu_views.xml',
    ],
    'demo': [],
    'installable': True,
    'auto_install': False,
    'application': False,
    'license': 'LGPL-3',
}
