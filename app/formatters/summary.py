from __future__ import annotations

from app.formatters.html import bold, html_escape
from app.models import SummaryReport


def format_summary_report(report: SummaryReport) -> str:
    lines: list[str] = []
    for index, line in enumerate(report.text.splitlines()):
        stripped = line.strip()
        if not stripped:
            lines.append("")
            continue

        if index == 0:
            lines.append(bold(stripped))
            continue

        if stripped.endswith(":"):
            lines.append(bold(stripped[:-1]))
            continue

        if stripped.startswith("Источник:"):
            source = stripped.removeprefix("Источник:").strip()
            lines.append(f"{bold('Источник:')} {html_escape(source)}")
            continue

        if ":" in stripped:
            label, value = stripped.split(":", 1)
            lines.append(f"  • {bold(f'{label}:')} {html_escape(value.strip())}")
            continue

        lines.append(f"  • {html_escape(stripped)}")

    return "\n".join(lines)
