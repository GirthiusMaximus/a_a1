"""Data models and pure helpers for the Octopus Agile integration."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from statistics import fmean
from typing import Any
from zoneinfo import ZoneInfo

from .const import (
    PRICE_CAP_SCHEDULE,
    PRICE_CAP_SOURCE_ESTIMATED,
    PRICE_CAP_SOURCE_OFGEM,
)


def parse_api_datetime(value: str) -> datetime:
    """Parse an ISO-8601 timestamp from the Octopus API into aware UTC."""
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class AgileRate:
    """A single half-hourly unit rate."""

    valid_from: datetime
    valid_to: datetime
    value_exc_vat: float
    value_inc_vat: float

    def local_date(self, tz: ZoneInfo) -> date:
        """Calendar date of the slot in the given timezone."""
        return self.valid_from.astimezone(tz).date()

    def as_dict(self, tz: ZoneInfo) -> dict[str, Any]:
        """Serializable summary used for sensor attributes and the card."""
        start = self.valid_from.astimezone(tz)
        end = self.valid_to.astimezone(tz)
        return {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "price": round(self.value_inc_vat, 3),
            "price_exc_vat": round(self.value_exc_vat, 3),
        }


def parse_rates(payload: dict[str, Any]) -> list[AgileRate]:
    """Build AgileRate objects from an API response body."""
    rates: list[AgileRate] = []
    for item in payload.get("results", []):
        rates.append(
            AgileRate(
                valid_from=parse_api_datetime(item["valid_from"]),
                valid_to=parse_api_datetime(item["valid_to"]),
                value_exc_vat=float(item["value_exc_vat"]),
                value_inc_vat=float(item["value_inc_vat"]),
            )
        )
    rates.sort(key=lambda rate: rate.valid_from)
    return rates


def split_by_local_day(
    rates: list[AgileRate], tz: ZoneInfo, today: date
) -> tuple[list[AgileRate], list[AgileRate]]:
    """Split sorted rates into the 'today' and 'tomorrow' buckets."""
    tomorrow = today + timedelta(days=1)
    day_rates = [rate for rate in rates if rate.local_date(tz) == today]
    tomorrow_rates = [rate for rate in rates if rate.local_date(tz) == tomorrow]
    return day_rates, tomorrow_rates


def summarise(rates: list[AgileRate]) -> dict[str, float | None]:
    """Return min/max/mean of inc-VAT prices for a list of rates."""
    if not rates:
        return {"min": None, "max": None, "average": None}
    prices = [rate.value_inc_vat for rate in rates]
    return {
        "min": round(min(prices), 2),
        "max": round(max(prices), 2),
        "average": round(fmean(prices), 2),
    }


def find_current(rates: list[AgileRate], now: datetime) -> AgileRate | None:
    """Return the rate covering 'now', if any."""
    for rate in rates:
        if rate.valid_from <= now < rate.valid_to:
            return rate
    return None


def find_next(rates: list[AgileRate], now: datetime) -> AgileRate | None:
    """Return the first rate starting after 'now', if any."""
    for rate in rates:
        if rate.valid_from > now:
            return rate
    return None


def find_cheapest(rates: list[AgileRate]) -> AgileRate | None:
    """Return the cheapest rate of the list (earliest wins on ties)."""
    if not rates:
        return None
    return min(rates, key=lambda rate: (rate.value_inc_vat, rate.valid_from))


def price_cap_for_date(day: date) -> tuple[float, str]:
    """Return (cap p/kWh, source) for the given date.

    Uses the built-in schedule of Ofgem average electricity unit rates.  For
    dates after the last scheduled period the newest value is carried forward
    and flagged as estimated.
    """
    for period_from, period_to, rate in PRICE_CAP_SCHEDULE:
        if period_from <= day <= period_to:
            return rate, PRICE_CAP_SOURCE_OFGEM
    if day > PRICE_CAP_SCHEDULE[-1][1]:
        return PRICE_CAP_SCHEDULE[-1][2], PRICE_CAP_SOURCE_ESTIMATED
    return PRICE_CAP_SCHEDULE[0][2], PRICE_CAP_SOURCE_ESTIMATED


def window_for_days(tz: ZoneInfo, today: date) -> tuple[datetime, datetime]:
    """API query window covering 'today' and 'tomorrow' in local time.

    Local midnight instants are built from wall-clock dates so the window is
    correct across BST transitions regardless of their length (46/48/49 hours).
    """
    day_after = today + timedelta(days=2)
    period_from = datetime(today.year, today.month, today.day, tzinfo=tz)
    period_to = datetime(day_after.year, day_after.month, day_after.day, tzinfo=tz)
    return period_from.astimezone(timezone.utc), period_to.astimezone(timezone.utc)
