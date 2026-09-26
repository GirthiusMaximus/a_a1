"""Sensor platform for the Octopus Agile integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from zoneinfo import ZoneInfo

from homeassistant.components.sensor import (
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import (
    ATTR_NEXT_PRICE,
    ATTR_PRICE_CAP,
    ATTR_PRICE_CAP_SOURCE,
    ATTR_PRODUCT_CODE,
    ATTR_REGION,
    ATTR_REGION_CODE,
    ATTR_STANDING_CHARGE,
    ATTR_TARIFF_CODE,
    ATTR_TODAY,
    ATTR_TOMORROW,
    ATTR_VALID_FROM,
    ATTR_VALID_TO,
    DOMAIN,
    MANUFACTURER,
    UK_TIMEZONE,
)
from .coordinator import AgileData, AgileDataUpdateCoordinator
from .models import find_cheapest

UNIT = "p/kWh"


def _round2(value: float | None) -> float | None:
    return None if value is None else round(value, 2)


@dataclass(frozen=True, kw_only=True)
class AgileSensorDescription(SensorEntityDescription):
    """Description with value/attribute extraction helpers."""

    value_fn: Callable[[AgileData], float | None]
    attrs_fn: Callable[[AgileData], dict[str, Any]] = lambda data: {}


def _uk_tz() -> ZoneInfo:
    return ZoneInfo(UK_TIMEZONE)


def _current_price_attrs(data: AgileData) -> dict[str, Any]:
    series = data.series_attributes(_uk_tz())
    attrs: dict[str, Any] = {
        ATTR_TODAY: series[ATTR_TODAY],
        ATTR_TOMORROW: series[ATTR_TOMORROW],
        ATTR_PRICE_CAP: data.price_cap,
        ATTR_PRICE_CAP_SOURCE: data.price_cap_source,
        ATTR_STANDING_CHARGE: data.standing_charge,
        "today_min": series["today_min"],
        "today_max": series["today_max"],
        "today_average": series["today_average"],
        "tomorrow_min": series["tomorrow_min"],
        "tomorrow_max": series["tomorrow_max"],
        "tomorrow_average": series["tomorrow_average"],
    }
    if data.current is not None:
        attrs[ATTR_VALID_FROM] = data.current.valid_from.isoformat()
        attrs[ATTR_VALID_TO] = data.current.valid_to.isoformat()
    if data.next_rate is not None:
        attrs[ATTR_NEXT_PRICE] = round(data.next_rate.value_inc_vat, 2)
    return attrs


def _next_price_attrs(data: AgileData) -> dict[str, Any]:
    if data.next_rate is None:
        return {}
    return {
        ATTR_VALID_FROM: data.next_rate.valid_from.isoformat(),
        ATTR_VALID_TO: data.next_rate.valid_to.isoformat(),
    }


def _cheapest_value(data: AgileData) -> float | None:
    slot = find_cheapest(data.rates_today)
    return _round2(slot.value_inc_vat) if slot else None


def _cheapest_attrs(data: AgileData) -> dict[str, Any]:
    slot = find_cheapest(data.rates_today)
    if slot is None:
        return {}
    now = datetime.now(timezone.utc)
    tz = _uk_tz()
    return {
        ATTR_VALID_FROM: slot.valid_from.astimezone(tz).isoformat(),
        ATTR_VALID_TO: slot.valid_to.astimezone(tz).isoformat(),
        "is_past": slot.valid_to <= now,
    }


def _tomorrow_attrs(data: AgileData) -> dict[str, Any]:
    stats = data.stats_tomorrow
    return {"tomorrow_min": stats["min"], "tomorrow_max": stats["max"]}


SENSORS: tuple[AgileSensorDescription, ...] = (
    AgileSensorDescription(
        key="current_price",
        name="Current price",
        icon="mdi:currency-gbp",
        native_unit_of_measurement=UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _round2(data.current.value_inc_vat) if data.current else None,
        attrs_fn=_current_price_attrs,
    ),
    AgileSensorDescription(
        key="next_price",
        name="Next price",
        icon="mdi:currency-gbp",
        native_unit_of_measurement=UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _round2(data.next_rate.value_inc_vat) if data.next_rate else None,
        attrs_fn=_next_price_attrs,
    ),
    AgileSensorDescription(
        key="today_min",
        name="Today minimum price",
        icon="mdi:arrow-down-bold-circle-outline",
        native_unit_of_measurement=UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.stats_today["min"],
    ),
    AgileSensorDescription(
        key="today_max",
        name="Today maximum price",
        icon="mdi:arrow-up-bold-circle-outline",
        native_unit_of_measurement=UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.stats_today["max"],
    ),
    AgileSensorDescription(
        key="today_average",
        name="Today average price",
        icon="mdi:chart-bell-curve",
        native_unit_of_measurement=UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.stats_today["average"],
    ),
    AgileSensorDescription(
        key="tomorrow_average",
        name="Tomorrow average price",
        icon="mdi:chart-bell-curve-cumulative",
        native_unit_of_measurement=UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: data.stats_tomorrow["average"],
        attrs_fn=_tomorrow_attrs,
    ),
    AgileSensorDescription(
        key="cheapest_slot_today",
        name="Cheapest slot today",
        icon="mdi:leaf",
        native_unit_of_measurement=UNIT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda data: _cheapest_value(data),
        attrs_fn=_cheapest_attrs,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Agile sensors from a config entry."""
    coordinator: AgileDataUpdateCoordinator = hass.data[DOMAIN][entry.entry_id]
    async_add_entities(
        AgileSensor(coordinator, description) for description in SENSORS
    )


class AgileSensor(CoordinatorEntity[AgileDataUpdateCoordinator], SensorEntity):
    """Sensor backed by the Agile price coordinator."""

    entity_description: AgileSensorDescription
    _attr_has_entity_name = True

    def __init__(
        self,
        coordinator: AgileDataUpdateCoordinator,
        description: AgileSensorDescription,
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        self._attr_unique_id = (
            f"{coordinator.product_code}-{coordinator.region_code}-{description.key}"
        )
        self._attr_device_info = DeviceInfo(
            identifiers={
                (DOMAIN, f"{coordinator.product_code}-{coordinator.region_code}")
            },
            name=f"Octopus Agile ({coordinator.region_name})",
            manufacturer=MANUFACTURER,
            model=coordinator.product_code,
            entry_type=DeviceEntryType.SERVICE,
        )

    @property
    def native_value(self) -> float | None:
        data = self.coordinator.data
        if data is None:
            return None
        return self.entity_description.value_fn(data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        attrs: dict[str, Any] = {
            ATTR_REGION: self.coordinator.region_name,
            ATTR_REGION_CODE: self.coordinator.region_code,
            ATTR_PRODUCT_CODE: self.coordinator.product_code,
            ATTR_TARIFF_CODE: self.coordinator.client.tariff_code,
        }
        if data is not None:
            attrs.update(self.entity_description.attrs_fn(data))
        return attrs
