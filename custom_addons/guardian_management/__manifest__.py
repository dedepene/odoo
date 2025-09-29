{
    'name': 'Guardian-Kid Management',
    'version': '19.0.1.0.0',
    'summary': 'Manage relationships between guardians and kids with flexible account management',
    'description': '''
        Guardian-Kid Management Module
        ===============================
        
        This module provides a comprehensive system for managing relationships between 
        guardians (parents/legal guardians) and kids, with the following features:
        
        Key Features:
        * Guardian management with mandatory active accounts
        * Kid management with optional managed accounts
        * Many-to-many relationships (one kid can have multiple guardians)
        * Detailed relationship tracking with permissions and legal status
        * Flexible contact preferences and emergency contact designation
        * Primary guardian designation for each kid
        * User account integration for both guardians and kids
        
        Use Cases:
        * School management systems
        * Childcare facilities
        * Youth programs
        * Family service organizations
        * Any organization managing parent-child relationships
        
        Security Features:
        * Role-based access (Users vs Managers)
        * Record-level security rules
        * Guardians can only see their own kids
        * Managers have full system access
    ''',
    'author': 'Your Company',
    'website': 'https://www.yourcompany.com',
    'category': 'Human Resources',
    'depends': ['base', 'contacts'],
    'data': [
        'security/guardian_security.xml',
        'security/ir.model.access.csv',
        'views/guardian_views.xml',
    ],
    'demo': [
        # 'demo/guardian_demo.xml',  # You can add demo data later
    ],
    'installable': True,
    'auto_install': False,
    'application': True,
    'sequence': 10,
    'license': 'LGPL-3',
} # type: ignore to suppress linting errors