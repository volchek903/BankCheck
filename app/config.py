from __future__ import annotations

import os

from dotenv import load_dotenv
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Settings(BaseModel):
    model_config = ConfigDict(populate_by_name=True, str_strip_whitespace=True)

    bot_token: str = Field(alias="BOT_TOKEN")
    telegram_user_id: int = Field(alias="TELEGRAM_USER_ID")
    timezone: str = Field(default="Europe/Minsk", alias="TIMEZONE")
    enable_currency: bool = Field(default=True, alias="ENABLE_CURRENCY")
    enable_deposits: bool = Field(default=True, alias="ENABLE_DEPOSITS")
    enable_credits: bool = Field(default=True, alias="ENABLE_CREDITS")
    enable_leasing: bool = Field(default=True, alias="ENABLE_LEASING")
    enable_summary: bool = Field(default=True, alias="ENABLE_SUMMARY")
    request_timeout_seconds: float = 15.0
    request_retries: int = 2
    currency_change_threshold_pct: float = 0.5
    schedule_hours: tuple[int, ...] = (7, 12, 18)


def load_settings() -> Settings:
    load_dotenv()
    raw = {
        "BOT_TOKEN": os.getenv("BOT_TOKEN"),
        "TELEGRAM_USER_ID": os.getenv("TELEGRAM_USER_ID"),
        "TIMEZONE": os.getenv("TIMEZONE", "Europe/Minsk"),
        "ENABLE_CURRENCY": os.getenv("ENABLE_CURRENCY", "true"),
        "ENABLE_DEPOSITS": os.getenv("ENABLE_DEPOSITS", "true"),
        "ENABLE_CREDITS": os.getenv("ENABLE_CREDITS", "true"),
        "ENABLE_LEASING": os.getenv("ENABLE_LEASING", "true"),
        "ENABLE_SUMMARY": os.getenv("ENABLE_SUMMARY", "true"),
    }
    try:
        return Settings.model_validate(raw)
    except ValidationError as exc:
        raise RuntimeError(f"Invalid configuration: {exc}") from exc
