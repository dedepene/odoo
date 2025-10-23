"""Trigger manual billing flows using the Odoo shell environment.

This script is intended to be executed via:

    python odoo-bin shell -c odoo.conf -d <database> --no-http < scripts/manual_billing.py

Optional environment variables:

    FORCE_DATE     - ISO date (YYYY-MM-DD) to simulate the cron run date.

The shell runner injects ``env`` and ``cr`` objects, so no explicit registry
bootstrap is required here.
"""
from __future__ import annotations

import os
from datetime import date

from odoo import fields
from odoo.tools import date_utils


def _resolve_force_date() -> date:
    force_date_str = os.environ.get("FORCE_DATE")
    if force_date_str:
        force_date_str = force_date_str.strip()
        try:
            return date.fromisoformat(force_date_str)
        except ValueError as exc:  # pragma: no cover - defensive
            print(
                f"[manual_billing] Ignoring invalid FORCE_DATE '{force_date_str}': {exc}. "
                "Falling back to today."
            )
    return fields.Date.context_today(env["academy.billing.template"])  # type: ignore[name-defined]


def _filtered_template_env(target_date: date):
    ctx = dict(env.context, force_date=target_date)  # type: ignore[name-defined]
    return env["academy.billing.template"].with_context(ctx)  # type: ignore[name-defined]


def _format_summary(label: str, summary) -> str:
    if isinstance(summary, list):
        blocks = []
        for entry in summary:
            block = [f"template_id={entry.get('template_id')}"]
            block.append(
                f"period={entry.get('period_start')} -> {entry.get('period_end')}"
            )
            block.append(f"invoices_created={entry.get('invoices_created')}")
            invoice_ids = entry.get('invoice_ids') or []
            if invoice_ids:
                block.append(f"invoice_ids={invoice_ids}")
            errors = entry.get('errors') or []
            if errors:
                block.append(f"errors={len(errors)}: {', '.join(map(str, errors))}")
            blocks.append("; ".join(block))
        details = os.linesep.join(f"    - {line}" for line in blocks) if blocks else "    - (no templates)"
        return f"{label}:{os.linesep}{details}"
    return f"{label}: {summary}"


def main():
    target_date = _resolve_force_date()
    template_env = _filtered_template_env(target_date)

    print(f"Running manual billing for {target_date.isoformat()}")

    invoice_summary = template_env.cron_generate_monthly_prepaid_invoices()
    print(_format_summary("Invoice generation", invoice_summary))

    absence_summary = template_env.cron_reconcile_monthly_absences()
    print(_format_summary("Absence reconciliation", absence_summary))

    attendance_model = env.get("academy.attendance.billing")  # type: ignore[name-defined]
    if attendance_model:
        attendance_window_end = target_date if target_date.day > 1 else date_utils.end_of(target_date, "month")
        attendance_window_start = date_utils.start_of(
            attendance_window_end - date_utils.relativedelta(months=1), "month"
        )
        attendance_summary = attendance_model.with_context(force_date=target_date).generate_billing_items(
            date_from=attendance_window_start,
            date_to=attendance_window_end,
        )
        print(_format_summary("Attendance billing", attendance_summary))

    env.cr.commit()  # type: ignore[name-defined]
    print("Database changes committed.")

    print("Manual billing run completed successfully.")


if __name__ == "__main__":
    main()
