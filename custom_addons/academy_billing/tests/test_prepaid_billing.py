from __future__ import annotations

from datetime import date, datetime, timedelta

from dateutil.relativedelta import relativedelta

from odoo import fields
from odoo.tests import common
from odoo.tests.common import tagged
from odoo.tools.float_utils import float_compare


@tagged('post_install', '-at_install', 'academy_billing')
class TestAcademyBilling(common.TransactionCase):
    def setUp(self):
        super().setUp()
        self.company = self.env.company
        self.currency = self.company.currency_id
        self.billing_template = self.env.ref('academy_billing.billing_template_monthly_prepaid')

        # Core records
        self.skill_group = self.env['academy.skill.group'].create({
            'name': 'Green',
            'enforce_age_range': False,
        })
        self.court = self.env['academy.court'].create({
            'name': 'Court 1',
        })

        guardian_partner = self.env['res.partner'].create({
            'name': 'Guardian Smith',
            'email': 'guardian@example.com',
            'phone': '+15550000001',
            'customer_rank': 1,
        })
        child_partner = self.env['res.partner'].create({
            'name': 'Player Smith',
            'email': 'player@example.com',
        })

        self.player = self.env['academy.player'].create({
            'partner_id': child_partner.id,
            'dob': date(2012, 5, 1),
            'skill_group_id': self.skill_group.id,
            'guardian_ids': [(6, 0, [guardian_partner.id])],
            'primary_guardian_id': guardian_partner.id,
        })
        self.guardian = guardian_partner

        self.season = self.env['academy.season'].create({
            'name': 'Winter Season',
            'start_date': date(2025, 1, 1),
            'end_date': date(2025, 3, 31),
            'state': 'active',
            'active': True,
        })

        self.session_template = self.env['academy.session.template'].create({
            'season_id': self.season.id,
            'skill_group_id': self.skill_group.id,
            'day_of_week': '0',
            'start_time': 17.0,
            'end_time': 19.0,
            'session_type': 'tennis_group',
            'court_ids': [(6, 0, [self.court.id])],
            'billing_template_id': self.billing_template.id,
        })

    def _create_occurrence(self, session_date: date):
        start_dt = datetime.combine(session_date, datetime.min.time()) + timedelta(hours=17)
        end_dt = start_dt + timedelta(hours=2)
        return self.env['academy.session.occurrence'].create({
            'template_id': self.session_template.id,
            'season_id': self.season.id,
            'date': session_date,
            'start_datetime': start_dt,
            'end_datetime': end_dt,
            'session_type': 'tennis_group',
            'skill_group_id': self.skill_group.id,
            'court_ids': [(6, 0, [self.court.id])],
        })

    def _create_credit_note(self, guardian, amount):
        refund = self.env['account.move'].with_context(default_move_type='out_refund').create({
            'move_type': 'out_refund',
            'partner_id': guardian.id,
            'invoice_date': date(2024, 12, 31),
            'invoice_line_ids': [(0, 0, {
                'name': 'Existing Credit',
                'quantity': 1,
                'price_unit': amount,
                'product_id': self.env.ref('academy_billing.product_product_prepaid_session').id,
            })],
        })
        refund.action_post()
        return refund

    def test_monthly_prepaid_invoice_generation(self):
        first_of_month = date(2025, 1, 1)
        self._create_occurrence(first_of_month + timedelta(days=1))
        self._create_occurrence(first_of_month + timedelta(days=8))

        ad_hoc_item = self.env['academy.billing.item'].create({
            'origin_type': 'extra',
            'guardian_id': self.guardian.id,
            'player_id': self.player.id,
            'amount': 15.0,
            'description': 'Pro Shop Purchase',
            'charge_date': first_of_month,
        })

        credit = self._create_credit_note(self.guardian, 10.0)

        self.env['academy.billing.template'].with_context(force_date=first_of_month).cron_generate_monthly_prepaid_invoices()

        invoices = self.env['account.move'].search([
            ('partner_id', '=', self.guardian.id),
            ('invoice_origin', '=', f"{self.billing_template.name} - {first_of_month.strftime('%B %Y')}")
        ])
        self.assertEqual(len(invoices), 1)
        invoice = invoices[0]
        self.assertEqual(invoice.invoice_date, first_of_month)
        expected_due = first_of_month + relativedelta(days=self.billing_template.payment_due_days)
        self.assertEqual(invoice.invoice_date_due, expected_due)

        base_amount = 2 * 25.0
        total_expected = base_amount + 15.0
        self.assertAlmostEqual(invoice.amount_total, total_expected, places=2)

        self.assertTrue(any(line.product_id == self.env.ref('academy_billing.product_product_ad_hoc_charge') for line in invoice.invoice_line_ids))
        self.assertEqual(ad_hoc_item.state, 'invoiced')
        self.assertTrue(ad_hoc_item.invoice_id)

        self.assertIn(invoice.payment_state, ('partial', 'paid'))
        self.assertTrue(any(line.reconciled for line in credit.line_ids if line.account_id.internal_type == 'receivable'))

    def test_acknowledged_absence_credit_generation(self):
        january_date = date(2024, 12, 15)
        future_occurrence = self._create_occurrence(date(2025, 1, 10))
        absence = self.env['academy.session.absence'].create({
            'occurrence_id': future_occurrence.id,
            'player_id': self.player.id,
            'reason_code': 'illness',
        })
        absence.action_acknowledge()
        # move occurrence to previous month to be processed
        future_occurrence.write({
            'date': january_date,
            'start_datetime': datetime.combine(january_date, datetime.min.time()) + timedelta(hours=17),
            'end_datetime': datetime.combine(january_date, datetime.min.time()) + timedelta(hours=19),
        })

        self.env['academy.billing.template'].with_context(force_date=date(2025, 1, 1)).cron_reconcile_monthly_absences()

        self.assertEqual(absence.state, 'credited')
        self.assertTrue(absence.credit_move_id)
        credit_amount = 25.0
        self.assertAlmostEqual(absence.credit_amount, credit_amount, places=2)
        self.assertEqual(absence.credit_move_id.move_type, 'out_refund')
        self.assertEqual(absence.credit_move_id.partner_id, self.guardian)
        self.assertEqual(absence.credit_move_id.payment_state, 'not_paid')
```}