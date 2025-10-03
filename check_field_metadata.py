"""Check selection field metadata - run from odoo shell."""

# Get the model
model = env['academy.session.occurrence']

# Check the field definition in Python
print("=" * 80)
print("Field definition in Python (_fields):")
print("=" * 80)
state_field = model._fields['state']
print(f"Field name: state")
print(f"Field type: {state_field.type}")
print(f"Selection: {state_field.selection}")
print()

# Check what fields_get returns
print("=" * 80)
print("Field metadata from fields_get():")
print("=" * 80)
fields_info = model.fields_get(['state'], attributes=['string', 'type', 'selection'])
print(f"State field info:")
for key, value in fields_info['state'].items():
    print(f"  {key}: {value}")
print()

# Check the database metadata
print("=" * 80)
print("Field metadata from ir.model.fields:")
print("=" * 80)
field_record = env['ir.model.fields'].search([
    ('model', '=', 'academy.session.occurrence'),
    ('name', '=', 'state')
])
if field_record:
    print(f"Field ID: {field_record.id}")
    print(f"Name: {field_record.name}")
    print(f"Field Description: {field_record.field_description}")
    print(f"Ttype: {field_record.ttype}")
    print(f"Selection IDs: {field_record.selection_ids}")
    if field_record.selection_ids:
        print("Selection values:")
        for sel in field_record.selection_ids:
            print(f"  - {sel.value}: {sel.name} (sequence: {sel.sequence})")
else:
    print("Field not found in ir.model.fields!")

print()
print("=" * 80)
