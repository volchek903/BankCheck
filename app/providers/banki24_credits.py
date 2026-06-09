from __future__ import annotations

import asyncio
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urlunparse

from app.models import CreditOffer
from app.providers.base import BaseHttpProvider, CreditsProvider, ProviderUnavailableError


class Banki24CreditsProvider(BaseHttpProvider, CreditsProvider):
    source_name = "banki24.by, belapb.by"
    source_url = "https://banki24.by/kredity/potrebitelskie"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.last_warnings: list[str] = []
        self._consumer_url = "https://banki24.by/kredity/potrebitelskie"
        self._auto_url = "https://banki24.by/kredity/avto"
        self._real_estate_url = (
            "https://www.belapb.by/chastnomu-klientu/kredity/filter/"
            "purpose_loan-is-nedvijimost/apply/"
        )

    async def fetch_offers(self) -> list[CreditOffer]:
        self.last_warnings = []
        offers: list[CreditOffer] = []

        for category, url, handler in (
            ("consumer", self._consumer_url, self._fetch_banki24_category),
            ("auto", self._auto_url, self._fetch_banki24_category),
            ("real_estate", self._real_estate_url, self._fetch_real_estate),
        ):
            try:
                offers.extend(await handler(url=url, category=category))
            except ProviderUnavailableError as exc:
                self.last_warnings.append(f"{self._category_label(category)}: {exc}")

        if not offers:
            reason = "; ".join(self.last_warnings) if self.last_warnings else "Нет доступных данных по кредитам."
            raise ProviderUnavailableError(reason)
        return offers

    async def _fetch_banki24_category(self, url: str, category: str) -> list[CreditOffer]:
        html = await self.fetch_html(url)
        soup = self.make_soup(html)
        page_urls = self._build_page_urls(url, soup)
        extra_pages = page_urls[1:]
        extra_html = await asyncio.gather(*(self.fetch_html(page_url) for page_url in extra_pages))

        offers = self._parse_banki24_offers(soup, category=category, page_url=url)
        for page_url, page_html in zip(extra_pages, extra_html, strict=False):
            offers.extend(
                self._parse_banki24_offers(
                    self.make_soup(page_html),
                    category=category,
                    page_url=page_url,
                )
            )

        if not offers:
            raise ProviderUnavailableError(f"На странице {url} не найдено предложений по кредитам.")
        return offers

    def _parse_banki24_offers(self, soup, category: str, page_url: str) -> list[CreditOffer]:
        offers: list[CreditOffer] = []
        for row in soup.select("table.table-paginate tbody tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 4:
                continue

            product_link = cells[0].select_one(".prod-info a[href]")
            bank_node = cells[0].select_one(".prod-text-sm")
            if product_link is None or bank_node is None:
                continue

            bank = self.normalize_space(bank_node.get_text(" ", strip=True))
            product = self.normalize_space(product_link.get_text(" ", strip=True))
            rate_parts = [self.normalize_space(part) for part in cells[1].stripped_strings]
            if not bank or not product or not rate_parts:
                continue

            rate_text = rate_parts[0]
            promo_rate_text = ", ".join(rate_parts[1:]) or None
            joined_rate_text = " ".join(rate_parts)
            amount_text = self.normalize_space(cells[2].get_text(" ", strip=True))
            term_text = self.normalize_space(cells[3].get_text(" ", strip=True))

            offers.append(
                CreditOffer(
                    bank=bank,
                    product=product,
                    category=category,
                    rate_text=rate_text,
                    min_rate=self.parse_min_percent(joined_rate_text),
                    promo_rate_text=promo_rate_text,
                    amount_text=amount_text or None,
                    term_text=term_text or None,
                    source_url=urljoin(page_url, product_link["href"]),
                )
            )
        return offers

    async def _fetch_real_estate(self, url: str, category: str) -> list[CreditOffer]:
        html = await self.fetch_html(url)
        soup = self.make_soup(html)

        offers: list[CreditOffer] = []
        for card in soup.select(".credits__item"):
            title_node = card.select_one("h4")
            link_node = card.select_one(".credits__item-link[href]")
            if title_node is None:
                continue

            terms: dict[str, str] = {}
            for term in card.select(".credits__item-terms-el"):
                name_node = term.select_one(".credits__item-terms-name")
                value_node = term.select_one(".credits__item-terms-val")
                if name_node is None or value_node is None:
                    continue
                name = self.normalize_space(name_node.get_text(" ", strip=True)).rstrip(":").lower()
                value = self.normalize_space(value_node.get_text(" ", strip=True))
                if name and value:
                    terms[name] = value

            rate_text = next((value for name, value in terms.items() if "процент" in name), None)
            term_text = next((value for name, value in terms.items() if "срок" in name), None)
            amount_text = next((value for name, value in terms.items() if "сумма" in name), None)
            product = self.normalize_space(title_node.get_text(" ", strip=True))
            if not product or not rate_text:
                continue

            offers.append(
                CreditOffer(
                    bank="Белагропромбанк",
                    product=product,
                    category=category,
                    rate_text=rate_text,
                    min_rate=self.parse_min_percent(rate_text),
                    amount_text=amount_text,
                    term_text=term_text,
                    source_url=urljoin(url, link_node["href"]) if link_node else url,
                )
            )

        if not offers:
            raise ProviderUnavailableError("На странице Белагропромбанка не найдено предложений по недвижимости.")
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

    @staticmethod
    def _category_label(category: str) -> str:
        return {
            "consumer": "потребительские кредиты",
            "real_estate": "кредиты на недвижимость",
            "auto": "автокредиты",
        }.get(category, category)
