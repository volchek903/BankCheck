from __future__ import annotations

from app.models import LeasingOffer, LeasingReport


def format_leasing_report(report: LeasingReport) -> str:
    lines = ["🚗 Топ лизинга", ""]
    source = report.source or "источник не указан"

    if report.unavailable_reason:
        lines.append(f"Раздел временно недоступен: {report.unavailable_reason}")
        lines.extend(["", f"Источник: {source}"])
        return "\n".join(lines)

    if not report.offers:
        lines.append("Подходящие предложения не найдены.")
        lines.extend(["", f"Источник: {source}"])
        return "\n".join(lines)

    for index, offer in enumerate(report.offers, start=1):
        lines.append(f"{index}. {_format_offer(offer)}")

    if report.alerts:
        lines.extend(["", *report.alerts[:6]])

    if report.notes:
        lines.extend(["", *report.notes[:3]])

    lines.extend(["", f"Источник: {source}"])
    return "\n".join(lines)


def _format_offer(offer: LeasingOffer) -> str:
    details = [f"{offer.company} — «{offer.product}»"]
    if offer.interest_rate_text:
        details.append(offer.interest_rate_text)
    elif offer.monthly_payment_text:
        details.append(f"платеж {offer.monthly_payment_text}")
    if offer.advance_text:
        details.append(offer.advance_text)
    if offer.max_term_text:
        details.append(offer.max_term_text)
    return ", ".join(details)
