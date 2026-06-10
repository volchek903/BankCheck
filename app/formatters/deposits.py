from __future__ import annotations

from app.formatters.html import bold, html_escape, notice_block, source_line
from app.models import DepositOffer, DepositsReport


def format_deposits_report(report: DepositsReport) -> str:
    lines = [bold("🏦 Топ вкладов"), ""]
    source = report.source or "источник не указан"

    if report.unavailable_reason:
        lines.append(f"{bold('Раздел временно недоступен:')} {html_escape(report.unavailable_reason)}")
        lines.extend(["", source_line(source)])
        return "\n".join(lines)

    bucket_order = [
        ("BYN", False),
        ("BYN", True),
        ("USD", False),
        ("USD", True),
        ("EUR", False),
        ("EUR", True),
        ("RUB", False),
        ("RUB", True),
        ("FX", False),
        ("FX", True),
    ]
    bucket_map = {(bucket.currency, bucket.revocable): bucket.offers for bucket in report.buckets}

    for currency, revocable in bucket_order:
        offers = bucket_map.get((currency, revocable))
        if not offers:
            continue
        bucket_title = _bucket_title(currency, revocable)
        lines.append(bold(bucket_title))
        for index, offer in enumerate(offers, start=1):
            lines.extend(_format_offer(index, offer))
            lines.append("")

    if report.short_term:
        lines.append(bold("Короткий срок"))
        for index, offer in enumerate(report.short_term, start=1):
            lines.extend(_format_offer(index, offer))
            lines.append("")

    if report.long_term:
        lines.append(bold("Длинный срок"))
        for index, offer in enumerate(report.long_term, start=1):
            lines.extend(_format_offer(index, offer))
            lines.append("")

    if report.alerts:
        lines.extend(notice_block("Важно", report.alerts, limit=6))

    if report.notes:
        lines.extend(notice_block("Примечания", report.notes, limit=3))

    lines.append(source_line(source))
    return "\n".join(lines)


def _bucket_title(currency: str, revocable: bool) -> str:
    prefix = {
        "BYN": "BYN",
        "USD": "USD",
        "EUR": "EUR",
        "RUB": "RUB",
        "FX": "Иностранная валюта",
    }.get(currency, currency)
    suffix = "отзывные" if revocable else "безотзывные"
    return f"{prefix} — {suffix}"


def _format_offer(index: int, offer: DepositOffer) -> list[str]:
    term = offer.term_text or "срок не указан"
    return [
        f"  {bold(f'{index}.')} {bold(offer.bank)} — «{bold(offer.product)}»",
        f"     • {bold('Ставка:')} {bold(offer.rate_text)}",
        f"     • {bold('Срок:')} {html_escape(term)}",
    ]
