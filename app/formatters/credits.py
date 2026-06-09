from __future__ import annotations

from app.models import CreditOffer, CreditsReport


def format_credits_report(report: CreditsReport) -> str:
    lines = ["💳 Топ кредитов", ""]
    source = report.source or "источник не указан"

    if report.unavailable_reason:
        lines.append(f"Раздел временно недоступен: {report.unavailable_reason}")
        lines.extend(["", f"Источник: {source}"])
        return "\n".join(lines)

    category_titles = {
        "consumer": "Потребительские кредиты",
        "real_estate": "Кредиты на недвижимость",
        "auto": "Автокредиты",
    }

    for category in report.categories:
        if not category.offers:
            continue
        lines.append(f"{category_titles.get(category.category, category.category)}:")
        for index, offer in enumerate(category.offers, start=1):
            lines.append(f"{index}. {_format_offer(offer)}")
        lines.append("")

    if report.alerts:
        lines.extend(report.alerts[:6])
        lines.append("")

    if report.notes:
        lines.extend(report.notes[:6])
        lines.append("")

    lines.append(f"Источник: {source}")
    return "\n".join(lines)


def _format_offer(offer: CreditOffer) -> str:
    details = [f"{offer.bank} — «{offer.product}», {offer.rate_text}"]
    if offer.term_text:
        details.append(offer.term_text)
    if offer.down_payment_text:
        details.append(f"первый взнос {offer.down_payment_text.lower()}")
    if offer.promo_rate_text:
        details.append(offer.promo_rate_text)
    return ", ".join(details)
