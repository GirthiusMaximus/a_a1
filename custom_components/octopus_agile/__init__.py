"""The Octopus Agile Tariff integration."""
from __future__ import annotations

import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import CARD_FILENAME, CARD_URL, DOMAIN, PLATFORMS
from .coordinator import AgileDataUpdateCoordinator

_LOGGER = logging.getLogger(__name__)

CARD_PATH = Path(__file__).parent / "www" / CARD_FILENAME


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Set up the integration-wide pieces (bundled Lovelace card)."""
    await _async_register_frontend(hass)
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve and auto-register the bundled price-chart card.

    The card is a single self-contained JS file, so it can also be installed
    manually as a Lovelace resource if auto-registration is unavailable.
    """
    if not CARD_PATH.exists():
        _LOGGER.warning("Bundled card %s is missing; skip frontend registration", CARD_PATH)
        return

    registered = hass.data.setdefault(DOMAIN, {}).setdefault("frontend_registered", False)
    if registered:
        return

    try:
        try:
            from homeassistant.components.http import StaticPathConfig

            await hass.http.async_register_static_paths(
                [StaticPathConfig(CARD_URL, str(CARD_PATH), False)]
            )
        except (ImportError, AttributeError):
            hass.http.register_static_path(CARD_URL, str(CARD_PATH), False)
    except Exception:  # noqa: BLE001 - never block integration setup
        _LOGGER.exception("Could not serve %s", CARD_URL)
        return

    try:
        from homeassistant.components.frontend import add_extra_js_url

        add_extra_js_url(hass, CARD_URL)
        hass.data[DOMAIN]["frontend_registered"] = True
        _LOGGER.debug("Registered Lovelace card at %s", CARD_URL)
    except Exception:  # noqa: BLE001
        _LOGGER.warning(
            "Could not auto-register the Agile card; add %s as a Lovelace "
            "manual resource instead",
            CARD_URL,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Octopus Agile from a config entry."""
    coordinator = AgileDataUpdateCoordinator(hass, entry, async_get_clientsession(hass))
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await coordinator.async_start_scheduling()

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options change."""
    await hass.config_entries.async_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        coordinator: AgileDataUpdateCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
        await coordinator.async_shutdown()
    return unload_ok
