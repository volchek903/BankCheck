from __future__ import annotations

from app.formatters.html import bold, html_escape, notice_block, source_line
from app.models import LeasingOffer, LeasingReport


def format_leasing_report(report: LeasingReport) -> str:
    lines = [bold("🚗 Топ лизинга"), ""]
    source = report.source or "источник не указан"

    if report.unavailable_reason:
        lines.append(f"{bold('Раздел временно недоступен:')} {html_escape(report.unavailable_reason)}")
        lines.extend(["", source_line(source)])
        return "\n".join(lines)

    if not report.offers:
        lines.append("Подходящие предложения не найдены.")
        lines.extend(["", source_line(source)])
        return "\n".join(lines)

    for index, offer in enumerate(report.offers, start=1):
        lines.extend(_format_offer(index, offer))
        lines.append("")

    if report.alerts:
        lines.extend(notice_block("Важно", report.alerts, limit=6))

    if report.notes:
        lines.extend(notice_block("Примечания", report.notes, limit=3))

    lines.append(source_line(source))
    return "\n".join(lines)


def _format_offer(index: int, offer: LeasingOffer) -> list[str]:
    details = [f"  {bold(f'{index}.')} {bold(offer.company)} — «{bold(offer.product)}»"]
    if offer.interest_rate_text:
        details.append(f"     • {bold('Ставка:')} {bold(offer.interest_rate_text)}")
    elif offer.monthly_payment_text:
        details.append(f"     • {bold('Платеж:')} {bold(offer.monthly_payment_text)}")
    if offer.advance_text:
        details.append(f"     • {bold('Аванс:')} {html_escape(offer.advance_text)}")
    if offer.max_term_text:
        details.append(f"     • {bold('Срок:')} {html_escape(offer.max_term_text)}")
    return details
