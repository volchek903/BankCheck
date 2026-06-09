from __future__ import annotations

import logging
from datetime import datetime
from zoneinfo import ZoneInfo

from app.config import Settings
from app.models import AppState, DepositBucket, DepositOffer, DepositsReport, LeaderSnapshot
from app.providers.base import DepositsProvider, ProviderUnavailableError

logger = logging.getLogger(__name__)


class DepositsService:
    def __init__(self, settings: Settings, provider: DepositsProvider) -> None:
        self._settings = settings
        self._provider = provider
        self._timezone = ZoneInfo(settings.timezone)
        self._source_name = getattr(provider, "source_name", "источник не указан")

    async def build_report(self, state: AppState) -> DepositsReport:
        generated_at = datetime.now(self._timezone)
        try:
            offers = await self._provider.fetch_offers()
        except ProviderUnavailableError as exc:
            return DepositsReport(
                generated_at=generated_at,
                source=self._source_name,
                unavailable_reason=str(exc),
            )
        except Exception as exc:  # pragma: no cover - defensive guard
            logger.exception("Unexpected error while building deposits report")
            return DepositsReport(
                generated_at=generated_at,
                source=self._source_name,
                unavailable_reason=f"Внутренняя ошибка парсинга: {exc}",
            )

        bucket_map: dict[tuple[str, bool], list[DepositOffer]] = {}
        for offer in offers:
            if offer.revocable is None:
                continue
            bucket_map.setdefault((offer.currency, offer.revocable), []).append(offer)

        buckets: list[DepositBucket] = []
        for (currency, revocable), bucket_offers in bucket_map.items():
            ranked_offers = self._top_deposits(bucket_offers)
            if ranked_offers:
                buckets.append(
                    DepositBucket(
                        currency=currency,
                        revocable=revocable,
                        offers=ranked_offers,
                    )
                )

        snapshot: dict[str, LeaderSnapshot] = {}
        alerts: list[str] = []
        for bucket in buckets:
            if not bucket.offers:
                continue
            leader = bucket.offers[0]
            key = self._bucket_key(bucket.currency, bucket.revocable)
            snapshot[key] = LeaderSnapshot(
                bank=leader.bank,
                title=leader.product,
                metric=leader.max_rate,
            )
            previous = state.deposits.get(key)
            if previous and (previous.bank != leader.bank or previous.title != leader.product):
                label = f"{bucket.currency} {'отзывные' if bucket.revocable else 'безотзывные'}"
                alerts.append(
                    f"Лидер по вкладам сменился: {label} — теперь {leader.bank}, «{leader.product}»."
                )

        notes = list(getattr(self._provider, "last_warnings", []))

        short_term = self._top_deposits(
            [offer for offer in offers if offer.max_term_months is not None and offer.max_term_months < 12]
        )
        long_term = self._top_deposits(
            [offer for offer in offers if offer.max_term_months is not None and offer.max_term_months >= 12]
        )

        return DepositsReport(
            generated_at=generated_at,
            buckets=buckets,
            short_term=short_term,
            long_term=long_term,
            alerts=alerts,
            notes=notes,
            source=self._source_name,
            snapshot=snapshot,
        )

    @staticmethod
    def _bucket_key(currency: str, revocable: bool) -> str:
        return f"{currency}:{'revocable' if revocable else 'nonrevocable'}"

    @staticmethod
    def _top_deposits(offers: list[DepositOffer], limit: int = 3) -> list[DepositOffer]:
        ranked = sorted(
            offers,
            key=lambda offer: (
                -(offer.max_rate or 0),
                offer.max_term_months if offer.max_term_months is not None else float("inf"),
                offer.bank,
                offer.product,
            ),
        )
        return ranked[:limit]
