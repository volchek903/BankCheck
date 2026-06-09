from __future__ import annotations

from app.models import CurrencyRateRow
from app.providers.base import BaseHttpProvider, CurrencyRatesProvider, ProviderUnavailableError


class SelectCurrencyProvider(BaseHttpProvider, CurrencyRatesProvider):
    source_name = "select.by"
    source_url = "https://select.by/kurs/"

    async def fetch_rates(self) -> list[CurrencyRateRow]:
        html = await self.fetch_html(self.source_url)
        soup = self.make_soup(html)
        table = soup.select_one("table.courses-main tbody")
        if table is None:
            raise ProviderUnavailableError("Не удалось найти таблицу курсов на select.by.")

        rows: list[CurrencyRateRow] = []
        for row in table.select("tr.tablesorter-hasChildRow"):
            cells = row.find_all("td", recursive=False)
            if len(cells) < 7:
                continue

            bank = self.normalize_space(cells[0].get_text(" ", strip=True))
            if not bank:
                continue

            rows.append(
                CurrencyRateRow(
                    bank=bank,
                    buy_usd=self.parse_money_value(cells[1].get_text(" ", strip=True)),
                    sell_usd=self.parse_money_value(cells[2].get_text(" ", strip=True)),
                    buy_eur=self.parse_money_value(cells[3].get_text(" ", strip=True)),
                    sell_eur=self.parse_money_value(cells[4].get_text(" ", strip=True)),
                    buy_rub=self.parse_money_value(cells[5].get_text(" ", strip=True)),
                    sell_rub=self.parse_money_value(cells[6].get_text(" ", strip=True)),
                    source_url=self.source_url,
                )
            )

        if not rows:
            raise ProviderUnavailableError("На select.by не найдено ни одной строки с банковскими курсами.")
        return rows
