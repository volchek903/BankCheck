from __future__ import annotations

from app.models import CurrencyReport


def format_currency_report(report: CurrencyReport) -> str:
    time_label = report.generated_at.strftime("%H:%M")
    lines = [f"💱 Курсы валют — {time_label}", ""]
    source = report.source or "источник не указан"

    if report.unavailable_reason:
        lines.append(f"Раздел временно недоступен: {report.unavailable_reason}")
        lines.extend(["", f"Источник: {source}"])
        return "\n".join(lines)

    labels = {
        "USD": ("🇺🇸 USD", "Купить доллар", "Продать доллар"),
        "EUR": ("🇪🇺 EUR", "Купить евро", "Продать евро"),
        "RUB": ("🇷🇺 RUB", "Купить 100 RUB", "Продать 100 RUB"),
    }

    for code in ("USD", "EUR", "RUB"):
        pair = report.pairs.get(code)
        title, buy_label, sell_label = labels[code]
        lines.append(title)
        if pair and pair.buy:
            lines.append(f"{buy_label}: {pair.buy.bank} — {pair.buy.rate:.4f} BYN")
        else:
            lines.append(f"{buy_label}: нет данных")
        if pair and pair.sell:
            lines.append(f"{sell_label}: {pair.sell.bank} — {pair.sell.rate:.4f} BYN")
        else:
            lines.append(f"{sell_label}: нет данных")
        lines.append("")

    if report.alerts:
        lines.extend(report.alerts[:6])
        lines.append("")

    lines.append(f"Источник: {source}")
    return "\n".join(lines)
