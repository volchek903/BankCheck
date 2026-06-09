from __future__ import annotations

import re
from urllib.parse import urljoin

from app.models import LeasingOffer
from app.providers.base import BaseHttpProvider, LeasingProvider, ProviderUnavailableError


class OfficialLeasingProvider(BaseHttpProvider, LeasingProvider):
    source_name = "agroleasing.by, asbleasing.by, pal.by"
    source_url = "https://agroleasing.by/"

    def __init__(self, settings) -> None:
        super().__init__(settings)
        self.last_warnings: list[str] = []
        self._agroleasing_url = "https://agroleasing.by/"
        self._asb_url = "https://asbleasing.by/leasing-dlya-fizicheskih-lic/avtomobili/"
        self._pal_url = "https://pal.by/programmy-lizinga/partnerskaa-programma-s_250529408"

    async def fetch_offers(self) -> list[LeasingOffer]:
        self.last_warnings = []
        offers: list[LeasingOffer] = []

        for label, handler in (
            ("Агролизинг", self._fetch_agroleasing),
            ("АСБ Лизинг", self._fetch_asb),
            ("Промагролизинг", self._fetch_pal),
        ):
            try:
                offers.extend(await handler())
            except ProviderUnavailableError as exc:
                self.last_warnings.append(f"{label}: {exc}")

        if not offers:
            reason = "; ".join(self.last_warnings) if self.last_warnings else "Нет доступных данных по лизингу."
            raise ProviderUnavailableError(reason)
        return offers

    async def _fetch_agroleasing(self) -> list[LeasingOffer]:
        html = await self.fetch_html(self._agroleasing_url)
        soup = self.make_soup(html)
        table = soup.select_one("#main_trblocks_mini_menu_2 table")
        if table is None:
            raise ProviderUnavailableError("Не удалось найти таблицу лизинговых программ на agroleasing.by.")

        offers: list[LeasingOffer] = []
        for row in table.select("tr"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 3:
                continue

            title_link = cells[0].find("a", href=True)
            product = self.normalize_space(cells[0].get_text(" ", strip=True))
            rate_text = self.normalize_space(cells[1].get_text(" ", strip=True))
            term_text = self.normalize_space(cells[2].get_text(" ", strip=True))
            if not product or not rate_text or not term_text:
                continue

            offers.append(
                LeasingOffer(
                    company="Агролизинг",
                    product=product,
                    interest_rate_text=rate_text,
                    interest_rate=self.parse_min_percent(rate_text),
                    max_term_text=term_text,
                    max_term_months=self.parse_max_term_months(term_text),
                    source_url=urljoin(self._agroleasing_url, title_link["href"]) if title_link else self._agroleasing_url,
                )
            )

        if not offers:
            raise ProviderUnavailableError("На agroleasing.by не найдено предложений с лизинговыми ставками.")
        return offers

    async def _fetch_asb(self) -> list[LeasingOffer]:
        html = await self.fetch_html(self._asb_url)
        soup = self.make_soup(html)
        cards = soup.select(".lizing-card")
        if not cards:
            raise ProviderUnavailableError("Не удалось найти карточки лизинга на asbleasing.by.")

        rate_text = self._extract_asb_rate_text(soup)
        if not rate_text:
            raise ProviderUnavailableError("На asbleasing.by не найдена явная ставка по программе для физлиц.")

        representative = None
        for card in cards:
            title_node = card.select_one(".lizing-card__title h5")
            if title_node is None:
                continue
            title = self.normalize_space(title_node.get_text(" ", strip=True))
            if "belgee" in title.lower() or "geely" in title.lower():
                representative = card
                break
        if representative is None:
            representative = cards[0]

        title_node = representative.select_one(".lizing-card__title h5")
        if title_node is None:
            raise ProviderUnavailableError("На asbleasing.by не удалось определить название лизинговой программы.")

        product = self.normalize_space(title_node.get_text(" ", strip=True))
        desc_node = representative.select_one(".lizing-card__desc")
        if desc_node is not None:
            desc = self.normalize_space(desc_node.get_text(" ", strip=True))
            if desc:
                product = f"{product} ({desc})"

        advance_text = None
        term_text = None
        for item in representative.select(".lizing-card__info li"):
            text = self.normalize_space(item.get_text(" ", strip=True))
            lowered = text.lower()
            if "авансов" in lowered:
                advance_text = text
            elif "срок" in lowered:
                term_text = text

        return [
            LeasingOffer(
                company="АСБ Лизинг",
                product=product,
                interest_rate_text=rate_text,
                interest_rate=self.parse_min_percent(rate_text),
                advance_text=advance_text,
                advance_percent=self.parse_min_percent(advance_text),
                max_term_text=term_text,
                max_term_months=self.parse_max_term_months(term_text),
                source_url=self._asb_url,
            )
        ]

    async def _fetch_pal(self) -> list[LeasingOffer]:
        html = await self.fetch_html(self._pal_url)
        soup = self.make_soup(html)
        page_text = self.normalize_space(soup.get_text(" ", strip=True))

        rate_match = re.search(r"ставк[аи]\s+от\s+(\d+(?:[.,]\d+)?)%", page_text, re.IGNORECASE)
        advance_match = re.search(r"аванс[^\d]*(\d+(?:[.,]\d+)?)%", page_text, re.IGNORECASE)
        term_match = re.search(r"срок лизинга[^\d]*(до\s+\d+\s+месяц\w*)", page_text, re.IGNORECASE)

        if rate_match is None:
            raise ProviderUnavailableError("На pal.by не найдена лизинговая ставка.")

        rate_text = f"от {rate_match.group(1).replace('.', ',')}%"
        advance_text = (
            f"аванс от {advance_match.group(1).replace('.', ',')}%"
            if advance_match is not None
            else None
        )
        term_text = term_match.group(1) if term_match is not None else None

        title_node = soup.select_one("h1")
        product = (
            self.normalize_space(title_node.get_text(" ", strip=True))
            if title_node is not None
            else "Партнерская программа для физических лиц"
        )

        return [
            LeasingOffer(
                company="Промагролизинг",
                product=product,
                interest_rate_text=rate_text,
                interest_rate=self.parse_min_percent(rate_text),
                advance_text=advance_text,
                advance_percent=self.parse_min_percent(advance_text),
                max_term_text=term_text,
                max_term_months=self.parse_max_term_months(term_text),
                source_url=self._pal_url,
            )
        ]

    def _extract_asb_rate_text(self, soup) -> str | None:
        for node in soup.find_all(string=re.compile(r"ставка\s+от\s+4[.,]5%", re.IGNORECASE)):
            text = self.normalize_space(str(node))
            match = re.search(r"ставка\s+от\s+(\d+(?:[.,]\d+)?)%", text, re.IGNORECASE)
            if match is not None:
                return f"от {match.group(1).replace('.', ',')}%"
        return None
