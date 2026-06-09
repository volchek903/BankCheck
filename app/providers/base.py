from __future__ import annotations

import abc
import asyncio
import re
from collections.abc import Iterable
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from app.config import Settings
from app.models import CreditOffer, CurrencyRateRow, DepositOffer, LeasingOffer

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/137.0.0.0 Safari/537.36"
)

CTA_LINES = {
    "подробнее",
    "далее",
    "открыть вклад",
    "открыть",
    "получить условия",
    "онлайн-запись в отделение",
    "онлайн-заявка",
    "получить предложение",
    "рассчитать платеж",
    "консультация",
    "подать заявку",
    "получить кредит",
    "отправить заявку",
    "запись в офис",
    "запись в отделение",
    "проверить одобрение",
    "получить условия",
    "рассчитать",
}

SORTING_NOISE = {
    "rate",
    "amount",
    "select_period",
    "payment",
    "percent_payment",
    "advsearch",
    "request_send",
}

ADDRESS_PREFIXES = (
    "г. ",
    "г.",
    "ул. ",
    "пр. ",
    "пр-т ",
    "проспект ",
    "д. ",
    "пл. ",
    "пер. ",
    "поселок ",
    "деревня ",
    "минский район",
)


class ProviderUnavailableError(RuntimeError):
    """Raised when a provider cannot fetch or parse data."""


class CurrencyRatesProvider(abc.ABC):
    @abc.abstractmethod
    async def fetch_rates(self) -> list[CurrencyRateRow]:
        raise NotImplementedError


class DepositsProvider(abc.ABC):
    @abc.abstractmethod
    async def fetch_offers(self) -> list[DepositOffer]:
        raise NotImplementedError


class CreditsProvider(abc.ABC):
    @abc.abstractmethod
    async def fetch_offers(self) -> list[CreditOffer]:
        raise NotImplementedError


class LeasingProvider(abc.ABC):
    @abc.abstractmethod
    async def fetch_offers(self) -> list[LeasingOffer]:
        raise NotImplementedError


class BaseHttpProvider:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._timeout = httpx.Timeout(settings.request_timeout_seconds)
        self._headers = {
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": (
                "text/html,application/xhtml+xml,application/xml;q=0.9,"
                "image/avif,image/webp,*/*;q=0.8"
            ),
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Cache-Control": "no-cache",
            "Pragma": "no-cache",
        }
        self._semaphore = asyncio.Semaphore(6)
        self._client = httpx.AsyncClient(
            headers=self._headers,
            timeout=self._timeout,
            follow_redirects=True,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def fetch_html(self, url: str) -> str:
        last_error: Exception | None = None
        host = urlparse(url).netloc.replace("www.", "") or "источник"
        async with self._semaphore:
            for attempt in range(self.settings.request_retries + 1):
                try:
                    response = await self._client.get(url)
                    if response.status_code == 423:
                        raise ProviderUnavailableError(
                            f"{host} временно блокирует HTTP-запросы (HTTP 423 Locked)."
                        )
                    response.raise_for_status()
                    return response.text
                except ProviderUnavailableError:
                    raise
                except httpx.HTTPStatusError as exc:
                    last_error = exc
                    if (
                        exc.response.status_code in {429, 500, 502, 503, 504}
                        and attempt < self.settings.request_retries
                    ):
                        await asyncio.sleep(1 + attempt)
                        continue
                    raise ProviderUnavailableError(
                        f"{host} вернул HTTP {exc.response.status_code}."
                    ) from exc
                except httpx.RequestError as exc:
                    last_error = exc
                    if attempt < self.settings.request_retries:
                        await asyncio.sleep(1 + attempt)
                        continue
                    raise ProviderUnavailableError(
                        f"Не удалось подключиться к {host}: {exc!s}"
                    ) from exc
        raise ProviderUnavailableError(f"Источник недоступен: {last_error!s}")

    @staticmethod
    def make_soup(html: str) -> BeautifulSoup:
        return BeautifulSoup(html, "html.parser")

    @staticmethod
    def extract_lines(html: str) -> list[str]:
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()
        text = soup.get_text("\n", strip=True)
        lines = [BaseHttpProvider.normalize_space(line) for line in text.splitlines()]
        return [line for line in lines if line]

    @staticmethod
    def normalize_space(value: str) -> str:
        return " ".join(value.split())

    @staticmethod
    def extract_numbers(text: str) -> list[float]:
        matches = re.findall(r"\d+(?:[.,]\d+)?", text.replace(" ", ""))
        return [float(match.replace(",", ".")) for match in matches]

    @classmethod
    def parse_min_percent(cls, text: str | None) -> float | None:
        if not text:
            return None
        values = cls.extract_numbers(text)
        return min(values) if values else None

    @classmethod
    def parse_max_percent(cls, text: str | None) -> float | None:
        if not text:
            return None
        values = cls.extract_numbers(text)
        return max(values) if values else None

    @classmethod
    def parse_money_value(cls, text: str | None) -> float | None:
        if not text or "индивидуально" in text.lower():
            return None
        values = cls.extract_numbers(text)
        return values[0] if values else None

    @classmethod
    def parse_max_term_months(cls, text: str | None) -> float | None:
        if not text:
            return None
        months: list[float] = []
        for value in re.findall(r"(\d+(?:[.,]\d+)?)\s*мес", text.lower()):
            months.append(float(value.replace(",", ".")))
        for value in re.findall(r"(\d+(?:[.,]\d+)?)\s*(?:год|года|лет)", text.lower()):
            months.append(float(value.replace(",", ".")) * 12)
        for value in re.findall(r"(\d+(?:[.,]\d+)?)\s*дн", text.lower()):
            months.append(float(value.replace(",", ".")) / 30)
        return max(months) if months else None

    @staticmethod
    def is_rating_line(line: str) -> bool:
        return bool(re.fullmatch(r"\d+(?:[.,]\d+)?", line))

    @staticmethod
    def is_address_line(line: str) -> bool:
        lowered = line.lower()
        return lowered.startswith(ADDRESS_PREFIXES)

    @staticmethod
    def is_call_to_action(line: str) -> bool:
        lowered = line.lower()
        return lowered in CTA_LINES or lowered.startswith("онлайн-")

    @staticmethod
    def is_noise_line(line: str) -> bool:
        lowered = line.lower()
        return lowered in SORTING_NOISE

    @classmethod
    def find_after_marker(cls, lines: list[str], marker: str) -> int:
        for index, line in enumerate(lines):
            if marker in line:
                return index
        return -1

    @classmethod
    def backtrack_title_and_entity(
        cls,
        lines: list[str],
        index: int,
        field_names: Iterable[str],
    ) -> tuple[str, str] | None:
        names: list[str] = []
        field_names_lower = {item.lower() for item in field_names}
        for pointer in range(index - 1, max(index - 8, -1), -1):
            value = lines[pointer]
            lowered = value.lower()
            if lowered in field_names_lower:
                continue
            if cls.is_call_to_action(value) or cls.is_noise_line(value):
                continue
            if cls.is_rating_line(value):
                continue
            names.append(value)
            if len(names) == 2:
                entity = names[0]
                title = names[1]
                return title, entity
        return None

    @classmethod
    def collect_field_block(
        cls,
        lines: list[str],
        start_index: int,
        field_names: Iterable[str],
    ) -> tuple[dict[str, str], list[str], int]:
        canonical_map = {item.lower(): item for item in field_names}
        fields: dict[str, str] = {}
        features: list[str] = []
        pointer = start_index
        while pointer < len(lines):
            current = lines[pointer]
            lowered = current.lower()
            if cls.is_call_to_action(current):
                pointer += 1
                break
            field_name = None
            if lowered in canonical_map:
                field_name = canonical_map[lowered]
            elif lowered.startswith("аванс"):
                field_name = "Аванс"
            if field_name:
                if field_name in fields:
                    break
                if pointer + 1 >= len(lines):
                    break
                if field_name == "Аванс" and current != field_name:
                    fields[field_name] = f"{current} {lines[pointer + 1]}"
                else:
                    fields[field_name] = lines[pointer + 1]
                pointer += 2
                continue
            if not cls.is_noise_line(current):
                features.append(current)
            pointer += 1
        return fields, features, pointer
