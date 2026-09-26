"""Data update coordinator for the Octopus Agile integration."""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Any
from zoneinfo import ZoneInfo

from aiohttp import ClientSession
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import async_track_point_in_utc_time
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import OctopusAgileApiClient, OctopusAgileApiError
from .const import (
    ATTR_PRICE_CAP,
    ATTR_PRICE_CAP_SOURCE,
    ATTR_STANDING_CHARGE,
    ATTR_TIMEZONE,
    ATTR_TODAY,
    ATTR_TOMORROW,
    CONF_PRICE_CAP,
    CONF_PRODUCT_CODE,
    CONF_REGION,
    DAILY_PUBLISH_HOUR,
    DAILY_PUBLISH_MINUTE,
    DEFAULT_PRODUCT_CODE,
    DOMAIN,
    FALLBACK_SCAN_INTERVAL_MINUTES,
    PRICE_CAP_SOURCE_OVERRIDE,
    REGIONS,
    UK_TIMEZONE,
)
from .models import (
    AgileRate,
    find_current,
    find_next,
    price_cap_for_date,
    split_by_local_day,
    summarise,
    window_for_days,
)

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class AgileData:
    """Snapshot of the published Agile prices."""

    today: date
    rates_today: list[AgileRate] = field(default_factory=list)
    rates_tomorrow: list[AgileRate] = field(default_factory=list)
    current: AgileRate | None = None
    next_rate: AgileRate | None = None
    standing_charge: float | None = None
    price_cap: float | None = None
    price_cap_source: str | None = None

    @property
    def stats_today(self) -> dict[str, float | None]:
        return summarise(self.rates_today)

    @property
    def stats_tomorrow(self) -> dict[str, float | None]:
        return summarise(self.rates_tomorrow)

    def series_attributes(self, tz: ZoneInfo) -> dict[str, Any]:
        """Attribute payload used by sensors and the bundled Lovelace card."""
        stats_today = self.stats_today
        stats_tomorrow = self.stats_tomorrow
        return {
            ATTR_TODAY: [rate.as_dict(tz) for rate in self.rates_today],
            ATTR_TOMORROW: [rate.as_dict(tz) for rate in self.rates_tomorrow],
            "today_min": stats_today["min"],
            "today_max": stats_today["max"],
            "today_average": stats_today["average"],
            "tomorrow_min": stats_tomorrow["min"],
            "tomorrow_max": stats_tomorrow["max"],
            "tomorrow_average": stats_tomorrow["average"],
            ATTR_PRICE_CAP: self.price_cap,
            ATTR_PRICE_CAP_SOURCE: self.price_cap_source,
            ATTR_STANDING_CHARGE: self.standing_charge,
            ATTR_TIMEZONE: str(tz),
        }


class AgileDataUpdateCoordinator(DataUpdateCoordinator[AgileData]):
    """Coordinates price updates.

    Refreshes are scheduled precisely at:
    * each 30 minute slot boundary (plus a small delay), so the "current
      price" sensor rolls over with the tariff, and
    * shortly after 16:00 UK time, when Octopus publish the next day's rates.

    A slower fallback poll backs these timers up.
    """

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry, session: ClientSession) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN}_{entry.data[CONF_REGION]}",
            update_interval=timedelta(minutes=FALLBACK_SCAN_INTERVAL_MINUTES),
        )
        self.region_code: str = entry.data[CONF_REGION]
        self.region_name: str = REGIONS[self.region_code]
        self.product_code: str = (
            entry.options.get(CONF_PRODUCT_CODE)
            or entry.data.get(CONF_PRODUCT_CODE)
            or DEFAULT_PRODUCT_CODE
        )
        self._price_cap_override: float | None = (
            entry.options.get(CONF_PRICE_CAP, entry.data.get(CONF_PRICE_CAP))
        )
        self._tz = ZoneInfo(UK_TIMEZONE)
        self.client = OctopusAgileApiClient(session, self.product_code, self.region_code)
        self._unsub_schedule: CALLBACK_TYPE | None = None

    # ------------------------------------------------------------------
    # Fetching
    # ------------------------------------------------------------------
    async def _async_update_data(self) -> AgileData:
        now = datetime.now(timezone.utc)
        today = now.astimezone(self._tz).date()
        period_from, period_to = window_for_days(self._tz, today)

        try:
            rates = await self.client.async_get_unit_rates(period_from, period_to)
            standing_charge = await self.client.async_get_standing_charge(period_from, period_to)
        except OctopusAgileApiError as err:
            raise UpdateFailed(str(err)) from err

        rates_today, rates_tomorrow = split_by_local_day(rates, self._tz, today)

        cap, source = self._resolve_price_cap(today)
        data = AgileData(
            today=today,
            rates_today=rates_today,
            rates_tomorrow=rates_tomorrow,
            current=find_current(rates, now),
            next_rate=find_next(rates, now),
            standing_charge=standing_charge,
            price_cap=cap,
            price_cap_source=source,
        )
        _LOGGER.debug(
            "Agile %s (%s): %d slots today, %d tomorrow, cap=%s (%s)",
            self.region_name,
            self.product_code,
            len(rates_today),
            len(rates_tomorrow),
            cap,
            source,
        )
        return data

    def _resolve_price_cap(self, today: date) -> tuple[float, str]:
        if self._price_cap_override is not None:
            return float(self._price_cap_override), PRICE_CAP_SOURCE_OVERRIDE
        return price_cap_for_date(today)

    # ------------------------------------------------------------------
    # Precise refresh scheduling
    # ------------------------------------------------------------------
    async def async_start_scheduling(self) -> None:
        """Arm the first point-in-time refresh."""
        self._schedule_next_refresh()

    @callback
    def _schedule_next_refresh(self) -> None:
        if self._unsub_schedule is not None:
            self._unsub_schedule()
            self._unsub_schedule = None

        point = min(self._next_slot_boundary(), self._next_publish_time())
        self._unsub_schedule = async_track_point_in_utc_time(
            self.hass, self._handle_scheduled_refresh, point
        )
        _LOGGER.debug("Next Agile refresh scheduled for %s", point.isoformat())

    @callback
    def _handle_scheduled_refresh(self, _hass: HomeAssistant, _now: datetime) -> None:
        self._unsub_schedule = None
        self.hass.async_create_task(self.async_request_refresh())
        self._schedule_next_refresh()

    @staticmethod
    def _next_slot_boundary(now: datetime | None = None) -> datetime:
        """First instant after the next half-hour boundary (+30s settle time)."""
        now = now or datetime.now(timezone.utc)
        minute = 30 if now.minute < 30 else 0
        if minute == 0:
            boundary = now.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        else:
            boundary = now.replace(minute=30, second=0, microsecond=0)
        return boundary + timedelta(seconds=30)

    def _next_publish_time(self, now: datetime | None = None) -> datetime:
        """First instant after 16:05 UK time (next-day rates go live ~16:00)."""
        now = now or datetime.now(timezone.utc)
        now_uk = now.astimezone(self._tz)
        target_uk = now_uk.replace(
            hour=DAILY_PUBLISH_HOUR, minute=DAILY_PUBLISH_MINUTE, second=0, microsecond=0
        )
        if target_uk <= now_uk:
            target_uk += timedelta(days=1)
        return target_uk.astimezone(timezone.utc)

    async def async_shutdown(self) -> None:
        """Stop scheduled refreshes."""
        if self._unsub_schedule is not None:
            self._unsub_schedule()
            self._unsub_schedule = None
        shutdown = getattr(super(), "async_shutdown", None)
        if shutdown is not None:
            await shutdown()
