from __future__ import annotations

from app.models import DepositOffer, DepositsReport


def format_deposits_report(report: DepositsReport) -> str:
    lines = ["🏦 Топ вкладов", ""]
    source = report.source or "источник не указан"

    if report.unavailable_reason:
        lines.append(f"Раздел временно недоступен: {report.unavailable_reason}")
        lines.extend(["", f"Источник: {source}"])
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
        lines.append(f"{bucket_title}:")
        for index, offer in enumerate(offers, start=1):
            lines.append(f"{index}. {_format_offer(offer)}")
        lines.append("")

    if report.short_term:
        lines.append("Короткий срок:")
        for index, offer in enumerate(report.short_term, start=1):
            lines.append(f"{index}. {_format_offer(offer)}")
        lines.append("")

    if report.long_term:
        lines.append("Длинный срок:")
        for index, offer in enumerate(report.long_term, start=1):
            lines.append(f"{index}. {_format_offer(offer)}")
        lines.append("")

    if report.alerts:
        lines.extend(report.alerts[:6])
        lines.append("")

    if report.notes:
        lines.extend(report.notes[:3])
        lines.append("")

    lines.append(f"Источник: {source}")
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


def _format_offer(offer: DepositOffer) -> str:
    term = offer.term_text or "срок не указан"
    return f"{offer.bank} — «{offer.product}», {offer.rate_text}, {term}"
