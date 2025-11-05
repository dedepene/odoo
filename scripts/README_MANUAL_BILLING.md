# Manual Billing Scripts

This directory contains scripts for manually triggering the academy billing cron jobs outside of their normal scheduled execution.

## Overview

The academy billing system normally runs automatically via scheduled actions (cron jobs):
- **Monthly Prepaid Invoices** - Generates invoices for monthly billing templates
- **Monthly Absence Reconciliation** - Creates credit notes for absences
- **Attendance-Based Billing** - Generates billing items from attendance records

These scripts allow you to trigger these billing processes manually for testing, debugging, or administrative purposes.

## Scripts

### 1. `run_manual_billing.cmd` (Local Development - Windows)

For local development environments running Odoo directly on Windows.

**Usage:**
```cmd
scripts\run_manual_billing.cmd [database] [date]
```

**Arguments:**
- `database` - Database name (default: `odoo`)
- `date` - Force date in YYYY-MM-DD format (default: today)

**Examples:**
```cmd
REM Run billing for today on default database
scripts\run_manual_billing.cmd

REM Run billing for specific database
scripts\run_manual_billing.cmd my_academy_db

REM Run billing for a specific date
scripts\run_manual_billing.cmd odoo 2025-10-01

REM Run billing for specific database and date
scripts\run_manual_billing.cmd academy_test 2025-11-01
```

**Requirements:**
- Python environment with Odoo dependencies
- `odoo.conf` configuration file in project root
- Database must be accessible with credentials in `odoo.conf`

---

### 2. `run_manual_billing_production.sh` (Production - Docker)

For production deployments running Odoo in Docker containers (using `docker-compose-production.yml`).

**Usage:**
```bash
./scripts/run_manual_billing_production.sh [database] [date]
```

**Arguments:**
- `database` - Database name (default: `postgres`)
- `date` - Force date in YYYY-MM-DD format (default: today)

**Examples:**
```bash
# Run billing for today on default database
./scripts/run_manual_billing_production.sh

# Run billing for specific database
./scripts/run_manual_billing_production.sh academy_prod

# Run billing for a specific date (useful for backdated runs)
./scripts/run_manual_billing_production.sh postgres 2025-10-01

# Run billing for specific database and date
./scripts/run_manual_billing_production.sh academy_prod 2025-11-01
```

**Requirements:**
- Docker and docker-compose installed
- `odoo_app` container must be running
- Access to production server with appropriate permissions
- Script must be run from the Odoo project root directory

**Making the script executable:**
```bash
chmod +x scripts/run_manual_billing_production.sh
```

---

## What These Scripts Do

Both scripts execute the same Python code (`manual_billing.py`) which:

1. **Prepaid Invoice Generation** - Calls `academy.billing.template.cron_generate_monthly_prepaid_invoices()`
   - Finds active billing templates for the target month
   - Creates draft invoices for players with prepaid billing schedules
   - Returns summary of invoices created per template

2. **Absence Reconciliation** - Calls `academy.billing.template.cron_reconcile_monthly_absences()`
   - Processes confirmed absences for prepaid billing
   - Creates credit notes to offset prepaid charges
   - Returns summary of credit notes created

3. **Attendance Billing** - Calls `academy.attendance.billing.generate_billing_items()`
   - Scans attendance records for the previous month
   - Creates billing items for pay-as-you-go sessions
   - Returns summary of billing items created

4. **Commits Changes** - All database changes are committed automatically

## Force Date Feature

The `FORCE_DATE` environment variable allows you to simulate running the cron on a different date. This is useful for:

- **Testing** - Verify billing logic for future or past periods
- **Backdated Runs** - Generate missed billing for previous months
- **End-of-Month Testing** - Test month-end logic before it actually runs
- **Debugging** - Reproduce issues from specific dates

**Important Notes:**
- The force date affects which billing periods are selected
- For attendance billing, it determines the window: previous month from the force date
- Absences are filtered based on the force date's month
- The force date does NOT change existing invoice dates or billing periods

## Output

Both scripts provide detailed output including:
- Target date for billing run
- Number of invoices/credit notes created per template
- Number of billing items generated from attendance
- Any errors encountered during processing
- Success/failure status

Example output:
```
Running manual billing for 2025-11-01
Invoice generation:
    - template_id=5; period=2025-11-01 -> 2025-11-30; invoices_created=12
    - template_id=8; period=2025-11-01 -> 2025-11-30; invoices_created=8
Absence reconciliation:
    - template_id=5; period=2025-11-01 -> 2025-11-30; invoices_created=2
Attendance billing:
    - billing_items_created=45; period=2025-10-01 -> 2025-10-31
Database changes committed.
Manual billing run completed successfully.
```

## Troubleshooting

### Windows Script Issues

**"Database not found"**
- Check that the database name is correct
- Verify database credentials in `odoo.conf`
- Ensure PostgreSQL is running

**"Module not found"**
- Ensure you're running from the project root directory
- Verify Python environment has Odoo dependencies installed
- Check that `custom_addons` is in the addons path

### Docker Script Issues

**"Container not running"**
```bash
# Check container status
docker ps -a | grep odoo

# Start containers if needed
docker-compose -f docker-compose-production.yml up -d
```

**"Permission denied"**
```bash
# Make script executable
chmod +x scripts/run_manual_billing_production.sh

# Or run with bash explicitly
bash scripts/run_manual_billing_production.sh
```

**"Script not found in container"**
- Verify the `manual_billing.py` script exists in the `scripts/` directory
- Check Docker volume mounts in `docker-compose-production.yml`

### General Issues

**"No invoices created"**
- Verify billing templates exist and are active
- Check that players are assigned to billing templates
- Ensure the force date is within a valid billing period
- Review billing template `date_start` and frequency settings

**"Database transaction failed"**
- Check Odoo logs for detailed error messages
- Verify database has sufficient permissions
- Ensure no conflicting processes are running

## Development Notes

### Testing Locally Before Production

Always test billing runs on a local copy of the production database first:

```cmd
REM 1. Create database dump from production
pg_dump -U odoo -h production_host -d postgres > prod_backup.sql

REM 2. Restore to local test database
psql -U odoo -h localhost -d odoo_test < prod_backup.sql

REM 3. Test billing on local copy
scripts\run_manual_billing.cmd odoo_test 2025-11-01

REM 4. Review results in local Odoo instance
python odoo-bin -c odoo.conf -d odoo_test
```

### Adding New Billing Processes

To add new billing cron jobs to these scripts:

1. Add the cron method to the appropriate model in `custom_addons/academy_billing/`
2. Update `scripts/manual_billing.py` to call the new method
3. Add documentation to this README
4. Test with both local and production scripts

### Script Maintenance

When updating these scripts:
- Test on a development database first
- Keep Windows (.cmd) and Linux (.sh) versions in sync
- Update this README with any new features or changes
- Version control all script changes

## Related Files

- `scripts/manual_billing.py` - Core Python logic for billing operations
- `custom_addons/academy_billing/models/billing_template.py` - Prepaid billing logic
- `custom_addons/academy_billing/models/attendance_billing.py` - Attendance billing logic
- `custom_addons/academy_billing/data/billing_cron.xml` - Scheduled cron job definitions
- `docker-compose-production.yml` - Production Docker configuration

## Security Considerations

⚠️ **Important Security Notes:**

- These scripts have full database access and commit changes automatically
- Always verify the force date before running in production
- Consider taking a database backup before manual billing runs
- Review generated invoices before sending to customers
- Restrict access to these scripts to authorized administrators only
- For production, consider requiring additional confirmation for backdated runs

## Support

For issues or questions about manual billing:
1. Check the troubleshooting section above
2. Review Odoo logs in `logs/odoo-server.log` (production) or console output (local)
3. Verify billing template and player configurations in Odoo
4. Test on a development database with `--log-level=debug` for detailed output
