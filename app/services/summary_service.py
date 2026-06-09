from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings
from app.models import CreditsReport, CurrencyReport, DepositsReport, LeasingReport, SummaryReport


class SummaryService:
    def __init__(self, settings: Settings) -> None:
        self._timezone = ZoneInfo(settings.timezone)

    def build_report(
        self,
        currency: CurrencyReport | None,
        deposits: DepositsReport | None,
        credits: CreditsReport | None,
        leasing: LeasingReport | None,
    ) -> SummaryReport:
        generated_at = datetime.now(self._timezone)
        time_label = generated_at.strftime("%H:%M")
        lines = [f"📌 Краткая сводка — {time_label}", ""]

        if currency and not currency.unavailable_reason:
            lines.append("Валюта:")
            for code in ("USD", "EUR", "RUB"):
                pair = currency.pairs.get(code)
                if not pair or not pair.buy or not pair.sell:
                    continue
                unit = "100 RUB" if code == "RUB" else code
                lines.append(
                    f"{unit}: купить у {pair.buy.bank} по {pair.buy.rate:.4f}, "
                    f"продать в {pair.sell.bank} по {pair.sell.rate:.4f}."
                )
            lines.append("")

        if deposits and not deposits.unavailable_reason:
            if deposits.short_term:
                leader = deposits.short_term[0]
                lines.append(
                    f"Короткие вклады: {leader.bank}, «{leader.product}» — {leader.rate_text}, {leader.term_text or 'срок не указан'}."
                )
            if deposits.long_term:
                leader = deposits.long_term[0]
                lines.append(
                    f"Длинные вклады: {leader.bank}, «{leader.product}» — {leader.rate_text}, {leader.term_text or 'срок не указан'}."
                )
            lines.append("")

        if credits and not credits.unavailable_reason:
            for category in credits.categories:
                if not category.offers:
                    continue
                leader = category.offers[0]
                label = {
                    "consumer": "Потребкредит",
                    "real_estate": "Недвижимость",
                    "auto": "Автокредит",
                }.get(category.category, category.category)
                lines.append(f"{label}: {leader.bank}, «{leader.product}» — {leader.rate_text}.")
            lines.append("")

        if leasing and not leasing.unavailable_reason and leasing.offers:
            leader = leasing.offers[0]
            details = []
            if leader.interest_rate_text:
                details.append(leader.interest_rate_text)
            if leader.advance_text:
                details.append(leader.advance_text)
            if leader.max_term_text:
                details.append(leader.max_term_text)
            suffix = ", ".join(details) if details else "параметры уточняются"
            lines.append(f"Лизинг: {leader.company}, «{leader.product}» — {suffix}.")
            lines.append("")

        for report in (currency, deposits, credits, leasing):
            if not report:
                continue
            if getattr(report, "alerts", None):
                lines.append(report.alerts[0])

        if lines[-1] == "":
            lines.pop()
        if len(lines) <= 2:
            lines.append("Доступных данных сейчас нет.")

        source = self._merge_sources(currency, deposits, credits, leasing)
        lines.extend(["", f"Источник: {source}"])
        return SummaryReport(generated_at=generated_at, text="\n".join(lines), source=source)

    @staticmethod
    def _merge_sources(*reports) -> str:
        sources: list[str] = []
        for report in reports:
            if report is None:
                continue
            raw_source = getattr(report, "source", "")
            for part in raw_source.split(","):
                source = part.strip()
                if source and source not in sources:
                    sources.append(source)
        return ", ".join(sources) if sources else "источник не указан"
