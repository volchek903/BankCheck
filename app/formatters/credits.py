from __future__ import annotations

from app.formatters.html import bold, html_escape, notice_block, source_line
from app.models import CreditOffer, CreditsReport


def format_credits_report(report: CreditsReport) -> str:
    lines = [bold("💳 Топ кредитов"), ""]
    source = report.source or "источник не указан"

    if report.unavailable_reason:
        lines.append(f"{bold('Раздел временно недоступен:')} {html_escape(report.unavailable_reason)}")
        lines.extend(["", source_line(source)])
        return "\n".join(lines)

    category_titles = {
        "consumer": "Потребительские кредиты",
        "real_estate": "Кредиты на недвижимость",
        "auto": "Автокредиты",
    }

    for category in report.categories:
        if not category.offers:
            continue
        lines.append(bold(category_titles.get(category.category, category.category)))
        for index, offer in enumerate(category.offers, start=1):
            lines.extend(_format_offer(index, offer))
            lines.append("")

    if report.alerts:
        lines.extend(notice_block("Важно", report.alerts, limit=6))

    if report.notes:
        lines.extend(notice_block("Примечания", report.notes, limit=6))

    lines.append(source_line(source))
    return "\n".join(lines)


def _format_offer(index: int, offer: CreditOffer) -> list[str]:
    details = [
        f"  {bold(f'{index}.')} {bold(offer.bank)} — «{bold(offer.product)}»",
        f"     • {bold('Ставка:')} {bold(offer.rate_text)}",
    ]
    if offer.term_text:
        details.append(f"     • {bold('Срок:')} {html_escape(offer.term_text)}")
    if offer.down_payment_text:
        details.append(f"     • {bold('Первый взнос:')} {html_escape(offer.down_payment_text.lower())}")
    if offer.promo_rate_text:
        details.append(f"     • {bold('Промо:')} {html_escape(offer.promo_rate_text)}")
    return details
