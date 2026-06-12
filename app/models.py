from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CurrencyRateRow(BaseModel):
    bank: str
    buy_usd: float | None = None
    sell_usd: float | None = None
    buy_eur: float | None = None
    sell_eur: float | None = None
    buy_rub: float | None = None
    sell_rub: float | None = None
    source_url: str


class CurrencyDirection(BaseModel):
    bank: str
    banks: list[str] = Field(default_factory=list)
    rate: float


class CurrencyPairBest(BaseModel):
    code: str
    buy: CurrencyDirection | None = None
    sell: CurrencyDirection | None = None


class CurrencyStateEntry(BaseModel):
    buy_bank: str
    buy_rate: float
    sell_bank: str
    sell_rate: float


class CurrencyReport(BaseModel):
    generated_at: datetime
    pairs: dict[str, CurrencyPairBest] = Field(default_factory=dict)
    alerts: list[str] = Field(default_factory=list)
    source: str = ""
    source_url: str
    unavailable_reason: str | None = None
    snapshot: dict[str, CurrencyStateEntry] = Field(default_factory=dict)


class DepositOffer(BaseModel):
    bank: str
    product: str
    currency: str
    rate_text: str
    max_rate: float | None
    term_text: str | None = None
    max_term_months: float | None = None
    revocable: bool | None = None
    features: list[str] = Field(default_factory=list)
    source_url: str


class DepositBucket(BaseModel):
    currency: str
    revocable: bool
    offers: list[DepositOffer] = Field(default_factory=list)


class LeaderSnapshot(BaseModel):
    bank: str
    title: str
    metric: float | None = None


class DepositsReport(BaseModel):
    generated_at: datetime
    buckets: list[DepositBucket] = Field(default_factory=list)
    short_term: list[DepositOffer] = Field(default_factory=list)
    long_term: list[DepositOffer] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source: str = ""
    unavailable_reason: str | None = None
    snapshot: dict[str, LeaderSnapshot] = Field(default_factory=dict)


class CreditOffer(BaseModel):
    bank: str
    product: str
    category: str
    rate_text: str
    min_rate: float | None
    promo_rate_text: str | None = None
    amount_text: str | None = None
    term_text: str | None = None
    down_payment_text: str | None = None
    features: list[str] = Field(default_factory=list)
    source_url: str


class CreditCategory(BaseModel):
    category: str
    offers: list[CreditOffer] = Field(default_factory=list)


class CreditsReport(BaseModel):
    generated_at: datetime
    categories: list[CreditCategory] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source: str = ""
    unavailable_reason: str | None = None
    snapshot: dict[str, LeaderSnapshot] = Field(default_factory=dict)


class LeasingOffer(BaseModel):
    company: str
    product: str
    monthly_payment_text: str | None = None
    monthly_payment_value: float | None = None
    max_term_text: str | None = None
    max_term_months: float | None = None
    advance_text: str | None = None
    advance_percent: float | None = None
    interest_rate_text: str | None = None
    interest_rate: float | None = None
    features: list[str] = Field(default_factory=list)
    source_url: str


class LeasingReport(BaseModel):
    generated_at: datetime
    offers: list[LeasingOffer] = Field(default_factory=list)
    alerts: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    source: str = ""
    unavailable_reason: str | None = None
    snapshot: dict[str, LeaderSnapshot] = Field(default_factory=dict)


class SummaryReport(BaseModel):
    generated_at: datetime
    text: str
    source: str = ""


class AppState(BaseModel):
    updated_at: datetime | None = None
    last_scheduled_slot: str | None = None
    currency: dict[str, CurrencyStateEntry] = Field(default_factory=dict)
    deposits: dict[str, LeaderSnapshot] = Field(default_factory=dict)
    credits: dict[str, LeaderSnapshot] = Field(default_factory=dict)
    leasing: dict[str, LeaderSnapshot] = Field(default_factory=dict)
