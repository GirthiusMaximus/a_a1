"""Config flow for the Octopus Agile integration."""
from __future__ import annotations

import contextlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    OptionsFlow,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
)

try:  # ConfigFlowResult is newer; fall back for older cores.
    from homeassistant.config_entries import ConfigFlowResult
except ImportError:  # pragma: no cover - depends on HA version
    from homeassistant.data_entry_flow import FlowResult as ConfigFlowResult

from .api import OctopusAgileApiClient, OctopusAgileApiError
from .const import (
    CONF_PRICE_CAP,
    CONF_PRODUCT_CODE,
    CONF_REGION,
    DEFAULT_PRODUCT_CODE,
    DOMAIN,
    REGIONS,
)

_LOGGER = logging.getLogger(__name__)

REGION_OPTIONS = [
    SelectOptionDict(value=code, label=f"{code} — {name}")
    for code, name in REGIONS.items()
]


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    defaults = defaults or {}
    schema: dict[Any, Any] = {
        vol.Required(
            CONF_REGION,
            default=defaults.get(CONF_REGION, "A"),
        ): SelectSelector(
            SelectSelectorConfig(
                options=REGION_OPTIONS,
                mode=SelectSelectorMode.DROPDOWN,
            )
        ),
        vol.Optional(
            CONF_PRODUCT_CODE,
            default=defaults.get(CONF_PRODUCT_CODE, DEFAULT_PRODUCT_CODE),
        ): TextSelector(),
    }
    cap = defaults.get(CONF_PRICE_CAP)
    cap_key = (
        vol.Optional(CONF_PRICE_CAP, default=cap) if cap is not None else vol.Optional(CONF_PRICE_CAP)
    )
    schema[cap_key] = NumberSelector(
        NumberSelectorConfig(
            min=0,
            max=200,
            step=0.01,
            mode=NumberSelectorMode.BOX,
            unit_of_measurement="p/kWh",
        )
    )
    return vol.Schema(schema)


async def _validate_input(hass: HomeAssistant, data: dict[str, Any]) -> None:
    """Check the region/product pair publishes Agile rates.

    Raises OctopusAgileApiError on connection problems; returns normally even
    when no rates are found (the caller decides what to do).
    """
    session = async_get_clientsession(hass)
    client = OctopusAgileApiClient(
        session, data.get(CONF_PRODUCT_CODE, DEFAULT_PRODUCT_CODE), data[CONF_REGION]
    )
    now = datetime.now(timezone.utc)
    period_from = now - timedelta(hours=6)
    has_rates = await client.async_test_connection(period_from, now)
    if not has_rates:
        raise ValueError("no_rates")


class AgileConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the initial configuration."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            unique_id = (
                f"{user_input.get(CONF_PRODUCT_CODE, DEFAULT_PRODUCT_CODE)}"
                f"-{user_input[CONF_REGION]}"
            )
            await self.async_set_unique_id(unique_id)
            self._abort_if_unique_id_configured()

            try:
                await _validate_input(self.hass, user_input)
            except ValueError as err:
                if str(err) == "no_rates":
                    errors["base"] = "no_rates"
                else:
                    errors["base"] = "unknown"
            except OctopusAgileApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001 - config flow must never explode
                _LOGGER.exception("Unexpected exception validating Agile input")
                errors["base"] = "unknown"
            else:
                title = f"Octopus Agile ({REGIONS[user_input[CONF_REGION]]})"
                return self.async_create_entry(title=title, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_user_schema(user_input),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return AgileOptionsFlow(config_entry)


class AgileOptionsFlow(OptionsFlow):
    """Allow the product code and price cap to be adjusted later."""

    def __init__(self, config_entry: ConfigEntry | None = None) -> None:
        # Works on both older cores (attribute) and newer cores (property).
        if config_entry is not None:
            with contextlib.suppress(Exception):
                self.config_entry = config_entry

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            to_check = {
                CONF_REGION: self.config_entry.data[CONF_REGION],
                CONF_PRODUCT_CODE: user_input.get(CONF_PRODUCT_CODE, DEFAULT_PRODUCT_CODE),
            }
            try:
                await _validate_input(self.hass, to_check)
            except ValueError as err:
                if str(err) == "no_rates":
                    errors["base"] = "no_rates"
                else:
                    errors["base"] = "unknown"
            except OctopusAgileApiError:
                errors["base"] = "cannot_connect"
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Unexpected exception validating Agile options")
                errors["base"] = "unknown"
            else:
                options = {
                    CONF_PRODUCT_CODE: to_check[CONF_PRODUCT_CODE],
                    # Explicit None means "use the automatic Ofgem cap".
                    CONF_PRICE_CAP: user_input.get(CONF_PRICE_CAP),
                }
                return self.async_create_entry(title="", data=options)

        defaults = {
            **self.config_entry.data,
            **self.config_entry.options,
        }
        cap = defaults.get(CONF_PRICE_CAP)
        schema_dict: dict[Any, Any] = {
            vol.Optional(
                CONF_PRODUCT_CODE,
                default=defaults.get(CONF_PRODUCT_CODE, DEFAULT_PRODUCT_CODE),
            ): TextSelector(),
        }
        if cap is not None:
            schema_dict[
                vol.Optional(CONF_PRICE_CAP, default=cap)
            ] = NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=200,
                    step=0.01,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="p/kWh",
                )
            )
        else:
            schema_dict[vol.Optional(CONF_PRICE_CAP)] = NumberSelector(
                NumberSelectorConfig(
                    min=0,
                    max=200,
                    step=0.01,
                    mode=NumberSelectorMode.BOX,
                    unit_of_measurement="p/kWh",
                )
            )
        return self.async_show_form(
            step_id="init", data_schema=vol.Schema(schema_dict), errors=errors
        )
