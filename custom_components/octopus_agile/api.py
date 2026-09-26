"""Minimal async client for the public Octopus Energy REST API."""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from aiohttp import ClientError, ClientSession, ClientTimeout

from .models import AgileRate, parse_rates

_LOGGER = logging.getLogger(__name__)

API_BASE = "https://api.octopus.energy/v1"
REQUEST_TIMEOUT = ClientTimeout(total=30)


class OctopusAgileApiError(Exception):
    """Raised when the Octopus Energy API cannot be reached or returns errors."""


class OctopusAgileApiClient:
    """Fetch half-hourly unit rates for one Agile region.

    Intentionally free of Home Assistant imports so the parsing logic can be
    exercised standalone.
    """

    def __init__(self, session: ClientSession, product_code: str, region: str) -> None:
        self._session = session
        self.product_code = product_code
        self.region = region

    @property
    def tariff_code(self) -> str:
        """Region specific tariff code, e.g. E-1R-AGILE-24-10-01-C."""
        return f"E-1R-{self.product_code}-{self.region}"

    def _url(self, series: str) -> str:
        return (
            f"{API_BASE}/products/{self.product_code}"
            f"/electricity-tariffs/{self.tariff_code}/{series}/"
        )

    @staticmethod
    def _format_time(value: datetime) -> str:
        return value.strftime("%Y-%m-%dT%H:%M:%SZ")

    async def _get_paginated(self, series: str, period_from: datetime, period_to: datetime) -> list[dict[str, Any]]:
        """GET one of the tariff series, following pagination links."""
        params = {
            "period_from": self._format_time(period_from),
            "period_to": self._format_time(period_to),
        }
        url: str | None = self._url(series)
        results: list[dict[str, Any]] = []
        pages = 0
        while url is not None:
            pages += 1
            if pages > 10:  # Hard safety stop; a two-day window never needs this.
                _LOGGER.warning("Pagination limit hit while fetching %s", series)
                break
            try:
                async with self._session.get(url, params=params, timeout=REQUEST_TIMEOUT) as response:
                    if response.status >= 400:
                        body = (await response.text())[:200]
                        raise OctopusAgileApiError(
                            f"API error {response.status} for {series}: {body}"
                        )
                    payload = await response.json()
            except (ClientError, TimeoutError, ValueError) as err:
                raise OctopusAgileApiError(f"Error fetching {series}: {err}") from err
            results.extend(payload.get("results", []))
            url = payload.get("next")
            params = {}  # Fully qualified 'next' links already carry the query.
        return results

    async def async_get_unit_rates(self, period_from: datetime, period_to: datetime) -> list[AgileRate]:
        """Return half-hourly unit rates between two instants (sorted ascending)."""
        raw = await self._get_paginated("standard-unit-rates", period_from, period_to)
        return parse_rates({"results": raw})

    async def async_get_standing_charge(self, period_from: datetime, period_to: datetime) -> float | None:
        """Return the inc-VAT standing charge in p/day, if published."""
        raw = await self._get_paginated("standing-charges", period_from, period_to)
        if not raw:
            return None
        # The most recent published standing charge is the valid one for 'now'.
        latest = max(raw, key=lambda item: item["valid_from"])
        return float(latest["value_inc_vat"])

    async def async_test_connection(self, period_from: datetime, period_to: datetime) -> bool:
        """Return True when the tariff publishes rates for the given window."""
        rates = await self.async_get_unit_rates(period_from, period_to)
        return bool(rates)
