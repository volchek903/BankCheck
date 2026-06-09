from __future__ import annotations

from app.models import SummaryReport


def format_summary_report(report: SummaryReport) -> str:
    return report.text
