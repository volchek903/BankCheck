from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings
from app.models import (
    AppState,
    CurrencyDirection,
    CurrencyPairBest,
    CurrencyRateRow,
    CurrencyReport,
    CurrencyStateEntry,
)
from app.providers.base import CurrencyRatesProvider, ProviderUnavailableError

logger = logging.getLogger(__name__)


class CurrencyService:
    def __init__(self, settings: Settings, provider: CurrencyRatesProvider) -> None:
        self._settings = settings
        self._provider = provider
        self._timezone = ZoneInfo(settings.timezone)
        self._source_name = getattr(provider, "source_name", "источник не указан")
        self._source_url = getattr(provider, "source_url", "")

    async def build_report(self, state: AppState) -> CurrencyReport:
        generated_at = datetime.now(self._timezone)
        try:
            rows = await self._provider.fetch_rates()
        except ProviderUnavailableError as exc:
            return CurrencyReport(
                generated_at=generated_at,
                source=self._source_name,
                source_url=self._source_url,
                unavailable_reason=str(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Unexpected error while building currency report")
            return CurrencyReport(
                generated_at=generated_at,
                source=self._source_name,
                source_url=self._source_url,
                unavailable_reason=f"Внутренняя ошибка парсинга: {exc}",
            )

        pairs: dict[str, CurrencyPairBest] = {}
        snapshot: dict[str, CurrencyStateEntry] = {}
        alerts: list[str] = []

        for code, buy_attr, sell_attr in (
            ("USD", "buy_usd", "sell_usd"),
            ("EUR", "buy_eur", "sell_eur"),
            ("RUB", "buy_rub", "sell_rub"),
        ):
            pair = CurrencyPairBest(
                code=code,
                buy=self._best_direction(rows, sell_attr, pick_lowest=True),
                sell=self._best_direction(rows, buy_attr, pick_lowest=False),
            )
            pairs[code] = pair

            if pair.buy and pair.sell:
                snapshot[code] = CurrencyStateEntry(
                    buy_bank=pair.buy.bank,
                    buy_rate=pair.buy.rate,
                    sell_bank=pair.sell.bank,
                    sell_rate=pair.sell.rate,
                )
                previous = state.currency.get(code)
                if previous:
                    alerts.extend(
                        self._build_alerts(
                            code=code,
                            previous=previous,
                            current=snapshot[code],
                        )
                    )

        return CurrencyReport(
            generated_at=generated_at,
            pairs=pairs,
            alerts=alerts,
            source=self._source_name,
            source_url=self._source_url,
            snapshot=snapshot,
        )

    def _build_alerts(
        self,
        code: str,
        previous: CurrencyStateEntry,
        current: CurrencyStateEntry,
    ) -> list[str]:
        alerts: list[str] = []
        threshold = self._settings.currency_change_threshold_pct

        buy_delta_pct = self._percent_delta(previous.buy_rate, current.buy_rate)
        if abs(buy_delta_pct) >= threshold:
            alerts.append(
                f"⚠️ {code}: лучший курс покупки {'вырос' if buy_delta_pct > 0 else 'снизился'} "
                f"на {abs(buy_delta_pct):.2f}%."
            )

        sell_delta_pct = self._percent_delta(previous.sell_rate, current.sell_rate)
        if abs(sell_delta_pct) >= threshold:
            alerts.append(
                f"⚠️ {code}: лучший курс продажи {'вырос' if sell_delta_pct > 0 else 'снизился'} "
                f"на {abs(sell_delta_pct):.2f}%."
            )

        return alerts

    @staticmethod
    def _percent_delta(old: float, new: float) -> float:
        if old == 0:
            return 0.0
        return ((new - old) / old) * 100

    @staticmethod
    def _best_direction(
        rows: list[CurrencyRateRow],
        rate_attr: str,
        pick_lowest: bool,
    ) -> CurrencyDirection | None:
        candidates = [(row, getattr(row, rate_attr)) for row in rows if getattr(row, rate_attr) is not None]
        if not candidates:
            return None

        rates = [rate for _, rate in candidates]
        best_rate = min(rates) if pick_lowest else max(rates)
        banks: list[str] = []
        for row, rate in candidates:
            if round(rate, 4) == round(best_rate, 4) and row.bank not in banks:
                banks.append(row.bank)
        return CurrencyDirection(bank=banks[0], banks=banks, rate=best_rate)
