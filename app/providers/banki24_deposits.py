from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from app.models import DepositOffer
from app.providers.base import BaseHttpProvider, DepositsProvider, ProviderUnavailableError


class Banki24DepositsProvider(BaseHttpProvider, DepositsProvider):
    source_name = "banki24.by"
    source_url = "https://banki24.by/vklady"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.last_warnings: list[str] = []
        self._routes: dict[tuple[str, bool], str] = {
            ("BYN", False): "https://banki24.by/vklady/bezotzyvnye-v-rublyah",
            ("BYN", True): "https://banki24.by/vklady/otzyvnye-v-rublyah",
            ("USD", False): "https://banki24.by/vklady/bezotzyvnye-v-valute?curr=107",
            ("USD", True): "https://banki24.by/vklady?curr=107&early=1",
            ("EUR", False): "https://banki24.by/vklady/bezotzyvnye-v-valute?curr=32",
            ("EUR", True): "https://banki24.by/vklady?curr=32&early=1",
            ("RUB", False): "https://banki24.by/vklady/bezotzyvnye-v-valute?curr=87",
            ("RUB", True): "https://banki24.by/vklady?curr=87&early=1",
        }

    async def fetch_offers(self) -> list[DepositOffer]:
        self.last_warnings = []
        offers: list[DepositOffer] = []

        for (currency, revocable), url in self._routes.items():
            try:
                offers.extend(await self._fetch_bucket(currency=currency, revocable=revocable, url=url))
            except ProviderUnavailableError as exc:
                label = f"{currency} {'отзывные' if revocable else 'безотзывные'}"
                self.last_warnings.append(f"{label}: {exc}")

        if not offers:
            reason = "; ".join(self.last_warnings) if self.last_warnings else "Нет доступных данных по вкладам."
            raise ProviderUnavailableError(reason)
        return offers

    async def _fetch_bucket(self, currency: str, revocable: bool, url: str) -> list[DepositOffer]:
        html = await self.fetch_html(url)
        soup = self.make_soup(html)
        page_urls = self._build_page_urls(url, soup)

        extra_pages = page_urls[1:]
        extra_html = await asyncio.gather(*(self.fetch_html(page_url) for page_url in extra_pages))

        offers = self._parse_offers(soup, currency=currency, revocable=revocable, page_url=url)
        for page_url, page_html in zip(extra_pages, extra_html, strict=False):
            offers.extend(
                self._parse_offers(
                    self.make_soup(page_html),
                    currency=currency,
                    revocable=revocable,
                    page_url=page_url,
                )
            )

        if not offers:
            raise ProviderUnavailableError(f"На странице {url} не найдено предложений по вкладам.")
        return offers

    def _parse_offers(self, soup, currency: str, revocable: bool, page_url: str) -> list[DepositOffer]:
        offers: list[DepositOffer] = []
        for row in soup.select("table.table-paginate tbody tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 4:
                continue

            product_link = cells[0].select_one(".prod-info a[href]")
            bank_node = cells[0].select_one(".prod-text-sm")
            if product_link is None or bank_node is None:
                continue

            product = self.normalize_space(product_link.get_text(" ", strip=True))
            bank = self.normalize_space(bank_node.get_text(" ", strip=True))
            rate_text = self.normalize_space(cells[1].get_text(" ", strip=True))
            term_text = self.normalize_space(cells[3].get_text(" ", strip=True))
            if not product or not bank or not rate_text:
                continue
            if not self._matches_revocability(product=product, revocable=revocable):
                continue

            offers.append(
                DepositOffer(
                    bank=bank,
                    product=product,
                    currency=currency,
                    rate_text=rate_text,
                    max_rate=self.parse_max_percent(rate_text),
                    term_text=term_text or None,
                    max_term_months=self.parse_max_term_months(term_text),
                    revocable=revocable,
                    source_url=urljoin(page_url, product_link["href"]),
                )
            )
        return offers

    def _build_page_urls(self, base_url: str, soup) -> list[str]:
        page_numbers = {1}
        for link in soup.select("ul.pagination a.page-link[href]"):
            page_number = self._extract_page_number(urljoin(base_url, link["href"]))
            if page_number is not None:
                page_numbers.add(page_number)

        max_page = max(page_numbers)
        return [self._set_page_number(base_url, page) for page in range(1, max_page + 1)]

    @staticmethod
    def _matches_revocability(product: str, revocable: bool) -> bool:
        lowered = product.lower()
        has_nonrevocable_marker = "безотзыв" in lowered
        has_revocable_marker = "отзыв" in lowered and not has_nonrevocable_marker
        if revocable and has_nonrevocable_marker:
            return False
        if not revocable and has_revocable_marker:
            return False
        return True

    @staticmethod
    def _extract_page_number(url: str) -> int | None:
        values = parse_qs(urlparse(url).query).get("page")
        if not values:
            return None
        try:
            return int(values[0])
        except ValueError:
            return None

    @staticmethod
    def _set_page_number(url: str, page: int) -> str:
        parsed = urlparse(url)
        query = parse_qs(parsed.query)
        if page == 1:
            query.pop("page", None)
        else:
            query["page"] = [str(page)]
        return urlunparse(parsed._replace(query=urlencode(query, doseq=True)))
