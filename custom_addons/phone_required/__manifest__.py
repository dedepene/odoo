{
    'name': 'Phone Number Required',
    'version': '1.0',
    'category': 'Base',
    'summary': 'Make phone number mandatory for users',
    'description': '''
        This module makes the phone number field mandatory 
        when creating or editing users.
    ''',
    'author': 'Your Name',
    'depends': ['base'],
    'data': [
        'views/res_users_views.xml',
    ],
    'installable': True,
    'auto_install': False,
    'application': False,
} # type: ignore to suppress linting errors