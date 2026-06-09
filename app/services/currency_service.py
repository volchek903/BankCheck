from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings
from app.models import (
    AppState,
    CurrencyDirection,
    CurrencyPairBest,
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
            best_buy_row = min(
                (row for row in rows if getattr(row, sell_attr) is not None),
                default=None,
                key=lambda row: getattr(row, sell_attr),
            )
            best_sell_row = max(
                (row for row in rows if getattr(row, buy_attr) is not None),
                default=None,
                key=lambda row: getattr(row, buy_attr),
            )

            pair = CurrencyPairBest(
                code=code,
                buy=(
                    CurrencyDirection(bank=best_buy_row.bank, rate=getattr(best_buy_row, sell_attr))
                    if best_buy_row
                    else None
                ),
                sell=(
                    CurrencyDirection(bank=best_sell_row.bank, rate=getattr(best_sell_row, buy_attr))
                    if best_sell_row
                    else None
                ),
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
