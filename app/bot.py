from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from aiogram import Bot, Dispatcher
from aiogram.filters import Command
from aiogram.types import BotCommand, Message

from app.config import Settings
from app.formatters.credits import format_credits_report
from app.formatters.currency import format_currency_report
from app.formatters.deposits import format_deposits_report
from app.formatters.html import bold, html_escape
from app.formatters.leasing import format_leasing_report
from app.formatters.summary import format_summary_report
from app.models import AppState, CreditsReport, CurrencyReport, DepositsReport, LeasingReport
from app.providers.base import BaseHttpProvider
from app.providers.banki24_credits import Banki24CreditsProvider
from app.providers.banki24_deposits import Banki24DepositsProvider
from app.providers.official_leasing import OfficialLeasingProvider
from app.providers.select_currency import SelectCurrencyProvider
from app.services.credits_service import CreditsService
from app.services.currency_service import CurrencyService
from app.services.deposits_service import DepositsService
from app.services.leasing_service import LeasingService
from app.services.summary_service import SummaryService
from app.storage.storage import JsonStateStorage

logger = logging.getLogger(__name__)


class FinanceBotApp:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.timezone = ZoneInfo(settings.timezone)
        self.bot = Bot(settings.bot_token)
        self.dispatcher = Dispatcher()
        self.storage = JsonStateStorage(Path(__file__).resolve().parent / "storage" / "state.json")

        self.currency_provider = SelectCurrencyProvider(settings)
        self.deposits_provider = Banki24DepositsProvider(settings)
        self.credits_provider = Banki24CreditsProvider(settings)
        self.leasing_provider = OfficialLeasingProvider(settings)
        self._providers: list[BaseHttpProvider] = [
            self.currency_provider,
            self.deposits_provider,
            self.credits_provider,
            self.leasing_provider,
        ]

        self.currency_service = CurrencyService(settings, self.currency_provider)
        self.deposits_service = DepositsService(settings, self.deposits_provider)
        self.credits_service = CreditsService(settings, self.credits_provider)
        self.leasing_service = LeasingService(settings, self.leasing_provider)
        self.summary_service = SummaryService(settings)

        self._register_handlers()

    async def set_commands(self) -> None:
        commands = [
            BotCommand(command="start", description="Проверить, что бот работает"),
            BotCommand(command="now", description="Отправить все отчеты прямо сейчас"),
            BotCommand(command="currency", description="Только курсы валют"),
            BotCommand(command="deposits", description="Только вклады"),
            BotCommand(command="credits", description="Только кредиты"),
            BotCommand(command="leasing", description="Только лизинг"),
            BotCommand(command="summary", description="Краткая сводка"),
            BotCommand(command="help", description="Список команд"),
        ]
        await self.bot.set_my_commands(commands)

    async def run_polling(self) -> None:
        await self.dispatcher.start_polling(
            self.bot,
            allowed_updates=self.dispatcher.resolve_used_update_types(),
        )

    async def close(self) -> None:
        await asyncio.gather(*(provider.aclose() for provider in self._providers), return_exceptions=True)
        await self.bot.session.close()

    async def send_scheduled_reports(self) -> None:
        logger.info("Sending scheduled reports")
        await self.send_all_reports(chat_id=self.settings.telegram_user_id)

    async def send_all_reports(self, chat_id: int | None = None) -> None:
        target_chat_id = chat_id or self.settings.telegram_user_id
        logger.info("Preparing reports for chat_id=%s", target_chat_id)
        state = await self.storage.load()
        reports = await self._build_core_reports(state)

        messages: list[str] = []
        currency = reports.get("currency")
        deposits = reports.get("deposits")
        credits = reports.get("credits")
        leasing = reports.get("leasing")

        if isinstance(currency, CurrencyReport):
            messages.append(format_currency_report(currency))
        if isinstance(deposits, DepositsReport):
            messages.append(format_deposits_report(deposits))
        if isinstance(credits, CreditsReport):
            messages.append(format_credits_report(credits))
        if isinstance(leasing, LeasingReport):
            messages.append(format_leasing_report(leasing))

        if self.settings.enable_summary:
            summary = self.summary_service.build_report(currency, deposits, credits, leasing)
            messages.append(format_summary_report(summary))

        for message in messages:
            await self._send_text(target_chat_id, message)

        await self._persist_state(state, currency, deposits, credits, leasing)
        logger.info("Report delivery finished for chat_id=%s", target_chat_id)

    async def send_currency_report(self, chat_id: int) -> None:
        if not self.settings.enable_currency:
            await self._send_text(chat_id, "Раздел курсов валют отключен в конфигурации.")
            return
        state = await self.storage.load()
        report = await self.currency_service.build_report(state)
        await self._send_text(chat_id, format_currency_report(report))
        await self._persist_state(state, report, None, None, None)

    async def send_deposits_report(self, chat_id: int) -> None:
        if not self.settings.enable_deposits:
            await self._send_text(chat_id, "Раздел вкладов отключен в конфигурации.")
            return
        state = await self.storage.load()
        report = await self.deposits_service.build_report(state)
        await self._send_text(chat_id, format_deposits_report(report))
        await self._persist_state(state, None, report, None, None)

    async def send_credits_report(self, chat_id: int) -> None:
        if not self.settings.enable_credits:
            await self._send_text(chat_id, "Раздел кредитов отключен в конфигурации.")
            return
        state = await self.storage.load()
        report = await self.credits_service.build_report(state)
        await self._send_text(chat_id, format_credits_report(report))
        await self._persist_state(state, None, None, report, None)

    async def send_leasing_report(self, chat_id: int) -> None:
        if not self.settings.enable_leasing:
            await self._send_text(chat_id, "Раздел лизинга отключен в конфигурации.")
            return
        state = await self.storage.load()
        report = await self.leasing_service.build_report(state)
        await self._send_text(chat_id, format_leasing_report(report))
        await self._persist_state(state, None, None, None, report)

    async def send_summary_report(self, chat_id: int) -> None:
        if not self.settings.enable_summary:
            await self._send_text(chat_id, "Краткая сводка отключена в конфигурации.")
            return
        state = await self.storage.load()
        reports = await self._build_core_reports(state)
        summary = self.summary_service.build_report(
            reports.get("currency"),
            reports.get("deposits"),
            reports.get("credits"),
            reports.get("leasing"),
        )
        await self._send_text(chat_id, format_summary_report(summary))
        await self._persist_state(
            state,
            reports.get("currency"),
            reports.get("deposits"),
            reports.get("credits"),
            reports.get("leasing"),
        )

    async def _build_core_reports(
        self,
        state: AppState,
    ) -> dict[str, CurrencyReport | DepositsReport | CreditsReport | LeasingReport]:
        tasks: list[asyncio.Future] = []
        names: list[str] = []

        if self.settings.enable_currency:
            names.append("currency")
            logger.info("Building currency report")
            tasks.append(asyncio.create_task(self.currency_service.build_report(state)))
        if self.settings.enable_deposits:
            names.append("deposits")
            logger.info("Building deposits report")
            tasks.append(asyncio.create_task(self.deposits_service.build_report(state)))
        if self.settings.enable_credits:
            names.append("credits")
            logger.info("Building credits report")
            tasks.append(asyncio.create_task(self.credits_service.build_report(state)))
        if self.settings.enable_leasing:
            names.append("leasing")
            logger.info("Building leasing report")
            tasks.append(asyncio.create_task(self.leasing_service.build_report(state)))

        if not tasks:
            return {}

        results = await asyncio.gather(*tasks)
        return dict(zip(names, results, strict=False))

    async def _persist_state(
        self,
        state: AppState,
        currency: CurrencyReport | None,
        deposits: DepositsReport | None,
        credits: CreditsReport | None,
        leasing: LeasingReport | None,
    ) -> None:
        next_state = state.model_copy(deep=True)
        next_state.updated_at = datetime.now(self.timezone)

        if currency and currency.snapshot:
            next_state.currency = currency.snapshot
        if deposits and deposits.snapshot:
            next_state.deposits = deposits.snapshot
        if credits and credits.snapshot:
            next_state.credits = credits.snapshot
        if leasing and leasing.snapshot:
            next_state.leasing = leasing.snapshot

        await self.storage.save(next_state)

    async def _send_text(self, chat_id: int, text: str) -> None:
        for chunk in _split_message(text):
            if chunk.strip():
                await self.bot.send_message(chat_id=chat_id, text=chunk, parse_mode="HTML")

    def _register_handlers(self) -> None:
        self.dispatcher.message.register(self._handle_start, Command("start"))
        self.dispatcher.message.register(self._handle_now, Command("now"))
        self.dispatcher.message.register(self._handle_currency, Command("currency"))
        self.dispatcher.message.register(self._handle_deposits, Command("deposits"))
        self.dispatcher.message.register(self._handle_credits, Command("credits"))
        self.dispatcher.message.register(self._handle_leasing, Command("leasing"))
        self.dispatcher.message.register(self._handle_summary, Command("summary"))
        self.dispatcher.message.register(self._handle_help, Command("help"))
        self.dispatcher.message.register(self._handle_fallback)

    async def _handle_start(self, message: Message) -> None:
        if not await self._ensure_access(message):
            return
        hours = ", ".join(f"{hour:02d}:00" for hour in self.settings.schedule_hours)
        await message.answer(
            f"{bold('Бот запущен.')}\n\n"
            f"{bold('Расписание:')} {html_escape(hours)} ({html_escape(self.settings.timezone)}).\n\n"
            f"Команда {bold('/now')} отправляет отчеты сразу.",
            parse_mode="HTML",
        )

    async def _handle_help(self, message: Message) -> None:
        if not await self._ensure_access(message):
            return
        await message.answer(
            f"{bold('Команды')}\n\n"
            f"  {bold('/start')} — проверить, что бот работает\n"
            f"  {bold('/now')} — отправить все отчеты прямо сейчас\n"
            f"  {bold('/currency')} — только курсы валют\n"
            f"  {bold('/deposits')} — только вклады\n"
            f"  {bold('/credits')} — только кредиты\n"
            f"  {bold('/leasing')} — только лизинг\n"
            f"  {bold('/summary')} — краткая сводка\n"
            f"  {bold('/help')} — список команд",
            parse_mode="HTML",
        )

    async def _handle_now(self, message: Message) -> None:
        if not await self._ensure_access(message):
            return
        await self.send_all_reports(chat_id=message.chat.id)

    async def _handle_currency(self, message: Message) -> None:
        if not await self._ensure_access(message):
            return
        await self.send_currency_report(message.chat.id)

    async def _handle_deposits(self, message: Message) -> None:
        if not await self._ensure_access(message):
            return
        await self.send_deposits_report(message.chat.id)

    async def _handle_credits(self, message: Message) -> None:
        if not await self._ensure_access(message):
            return
        await self.send_credits_report(message.chat.id)

    async def _handle_leasing(self, message: Message) -> None:
        if not await self._ensure_access(message):
            return
        await self.send_leasing_report(message.chat.id)

    async def _handle_summary(self, message: Message) -> None:
        if not await self._ensure_access(message):
            return
        await self.send_summary_report(message.chat.id)

    async def _handle_fallback(self, message: Message) -> None:
        if not self._is_authorized_message(message):
            await message.answer("⛔ Доступ запрещен")
            return
        await message.answer("Используйте /help для списка команд.")

    async def _ensure_access(self, message: Message) -> bool:
        if not self._is_authorized_message(message):
            await message.answer("⛔ Доступ запрещен")
            return False
        return True

    def _is_authorized_message(self, message: Message) -> bool:
        if not message.from_user or message.from_user.id != self.settings.telegram_user_id:
            return False
        return message.chat.type == "private" and message.chat.id == self.settings.telegram_user_id


def _split_message(text: str, limit: int = 4000) -> list[str]:
    if len(text) <= limit:
        return [text]

    parts: list[str] = []
    current = ""
    for paragraph in text.split("\n\n"):
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= limit:
            current = candidate
            continue
        if current:
            parts.append(current)
        current = paragraph

    if current:
        parts.append(current)

    normalized: list[str] = []
    for part in parts:
        if len(part) <= limit:
            normalized.append(part)
            continue
        for offset in range(0, len(part), limit):
            normalized.append(part[offset : offset + limit])
    return normalized
