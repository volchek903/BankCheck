from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings
from app.models import AppState, LeaderSnapshot, LeasingOffer, LeasingReport
from app.providers.base import LeasingProvider, ProviderUnavailableError

logger = logging.getLogger(__name__)


class LeasingService:
    def __init__(self, settings: Settings, provider: LeasingProvider) -> None:
        self._settings = settings
        self._provider = provider
        self._timezone = ZoneInfo(settings.timezone)
        self._source_name = getattr(provider, "source_name", "источник не указан")

    async def build_report(self, state: AppState) -> LeasingReport:
        generated_at = datetime.now(self._timezone)
        try:
            offers = await self._provider.fetch_offers()
        except ProviderUnavailableError as exc:
            return LeasingReport(
                generated_at=generated_at,
                source=self._source_name,
                unavailable_reason=str(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Unexpected error while building leasing report")
            return LeasingReport(
                generated_at=generated_at,
                source=self._source_name,
                unavailable_reason=f"Внутренняя ошибка парсинга: {exc}",
            )

        top_offers = self._top_offers(offers)
        notes = list(getattr(self._provider, "last_warnings", []))
        if top_offers and not any(offer.interest_rate is not None for offer in top_offers):
            notes.append(
                "По части лизинговых предложений нет явной процентной ставки, поэтому рейтинг построен по доступным параметрам: аванс, платеж и срок."
            )

        snapshot: dict[str, LeaderSnapshot] = {}
        alerts: list[str] = []
        if top_offers:
            leader = top_offers[0]
            snapshot["top"] = LeaderSnapshot(
                bank=leader.company,
                title=leader.product,
                metric=leader.interest_rate,
            )
            previous = state.leasing.get("top")
            if previous and (previous.bank != leader.company or previous.title != leader.product):
                alerts.append(f"Лидер по лизингу сменился: теперь {leader.company}, «{leader.product}».")

        return LeasingReport(
            generated_at=generated_at,
            offers=top_offers,
            alerts=alerts,
            notes=notes,
            source=self._source_name,
            snapshot=snapshot,
        )

    @staticmethod
    def _top_offers(offers: list[LeasingOffer], limit: int = 3) -> list[LeasingOffer]:
        ranked = sorted(
            offers,
            key=lambda offer: (
                offer.interest_rate is None,
                offer.interest_rate if offer.interest_rate is not None else float("inf"),
                offer.advance_percent if offer.advance_percent is not None else float("inf"),
                offer.monthly_payment_value if offer.monthly_payment_value is not None else float("inf"),
                -(offer.max_term_months or 0),
                offer.company,
            ),
        )
        unique_offers: list[LeasingOffer] = []
        seen_companies: set[str] = set()
        for offer in ranked:
            if offer.company in seen_companies:
                continue
            seen_companies.add(offer.company)
            unique_offers.append(offer)
            if len(unique_offers) >= limit:
                break
        return unique_offers
