from __future__ import annotations

from app.formatters.html import bold, html_escape, notice_block, source_line
from app.models import CurrencyDirection, CurrencyReport


def format_currency_report(report: CurrencyReport) -> str:
    time_label = report.generated_at.strftime("%H:%M")
    lines = [bold(f"💱 Курсы валют — {time_label}"), ""]
    source = report.source or "источник не указан"

    if report.unavailable_reason:
        lines.append(f"{bold('Раздел временно недоступен:')} {html_escape(report.unavailable_reason)}")
        lines.extend(["", source_line(source)])
        return "\n".join(lines)

    labels = {
        "USD": ("🇺🇸 USD", "Купить доллар", "Продать доллар"),
        "EUR": ("🇪🇺 EUR", "Купить евро", "Продать евро"),
        "RUB": ("🇷🇺 RUB", "Купить 100 RUB", "Продать 100 RUB"),
    }

    for code in ("USD", "EUR", "RUB"):
        pair = report.pairs.get(code)
        title, buy_label, sell_label = labels[code]
        lines.append(bold(title))
        lines.append(_format_direction(buy_label, pair.buy if pair else None))
        lines.append(_format_direction(sell_label, pair.sell if pair else None))
        lines.append("")

    if report.alerts:
        lines.extend(notice_block("Важно", report.alerts, limit=6))

    lines.append(source_line(source))
    return "\n".join(lines)


def _format_direction(label: str, direction: CurrencyDirection | None) -> str:
    if not direction:
        return f"  {bold(label)}: нет данных"

    rate = f"{direction.rate:.4f} BYN"
    return f"  {bold(label)}: {bold(direction.bank)} — {bold(rate)}"
