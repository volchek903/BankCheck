from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings
from app.models import AppState, CreditCategory, CreditOffer, CreditsReport, LeaderSnapshot
from app.providers.base import CreditsProvider, ProviderUnavailableError

logger = logging.getLogger(__name__)


class CreditsService:
    def __init__(self, settings: Settings, provider: CreditsProvider) -> None:
        self._settings = settings
        self._provider = provider
        self._timezone = ZoneInfo(settings.timezone)
        self._source_name = getattr(provider, "source_name", "источник не указан")

    async def build_report(self, state: AppState) -> CreditsReport:
        generated_at = datetime.now(self._timezone)
        try:
            offers = await self._provider.fetch_offers()
        except ProviderUnavailableError as exc:
            return CreditsReport(
                generated_at=generated_at,
                source=self._source_name,
                unavailable_reason=str(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Unexpected error while building credits report")
            return CreditsReport(
                generated_at=generated_at,
                source=self._source_name,
                unavailable_reason=f"Внутренняя ошибка парсинга: {exc}",
            )

        category_map: dict[str, list[CreditOffer]] = {}
        for offer in offers:
            category_map.setdefault(offer.category, []).append(offer)

        categories: list[CreditCategory] = []
        for category, category_offers in category_map.items():
            ranked_offers = self._top_credits(category_offers)
            if ranked_offers:
                categories.append(CreditCategory(category=category, offers=ranked_offers))

        snapshot: dict[str, LeaderSnapshot] = {}
        alerts: list[str] = []
        for category in categories:
            leader = category.offers[0]
            snapshot[category.category] = LeaderSnapshot(
                bank=leader.bank,
                title=leader.product,
                metric=leader.min_rate,
            )
            previous = state.credits.get(category.category)
            if previous and (previous.bank != leader.bank or previous.title != leader.product):
                alerts.append(
                    f"Лидер по кредитам сменился: {self._category_label(category.category)} — "
                    f"теперь {leader.bank}, «{leader.product}»."
                )

        return CreditsReport(
            generated_at=generated_at,
            categories=categories,
            alerts=alerts,
            notes=list(getattr(self._provider, "last_warnings", [])),
            source=self._source_name,
            snapshot=snapshot,
        )

    @staticmethod
    def _top_credits(offers: list[CreditOffer], limit: int = 3) -> list[CreditOffer]:
        ranked = sorted(
            offers,
            key=lambda offer: (
                offer.min_rate if offer.min_rate is not None else float("inf"),
                offer.bank,
                offer.product,
            ),
        )
        return ranked[:limit]

    @staticmethod
    def _category_label(category: str) -> str:
        return {
            "consumer": "потребительские",
            "real_estate": "недвижимость",
            "auto": "автокредиты",
        }.get(category, category)
