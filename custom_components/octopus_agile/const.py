"""Constants for the Octopus Agile integration."""
from __future__ import annotations

from datetime import date
from typing import Final

DOMAIN: Final = "octopus_agile"
MANUFACTURER: Final = "Octopus Energy"
DEFAULT_PRODUCT_CODE: Final = "AGILE-24-10-01"
DEFAULT_NAME: Final = "Octopus Agile"

# UK electricity distribution network (MPAN GSP group) region letters used in
# Octopus tariff codes, e.g. E-1R-AGILE-24-10-01-C is the London tariff.
REGIONS: Final[dict[str, str]] = {
    "A": "Eastern England",
    "B": "East Midlands",
    "C": "London",
    "D": "Merseyside & North Wales",
    "E": "West Midlands",
    "F": "North East England",
    "G": "North West England",
    "H": "Southern England",
    "J": "South East England",
    "K": "South Wales",
    "L": "South West England",
    "M": "Yorkshire",
    "N": "Southern Scotland",
    "P": "Northern Scotland",
}

CONF_REGION: Final = "region"
CONF_PRODUCT_CODE: Final = "product_code"
CONF_PRICE_CAP: Final = "price_cap"

ATTR_TODAY: Final = "today"
ATTR_TOMORROW: Final = "tomorrow"
ATTR_PRICE_CAP: Final = "price_cap"
ATTR_PRICE_CAP_SOURCE: Final = "price_cap_source"
ATTR_REGION: Final = "region"
ATTR_REGION_CODE: Final = "region_code"
ATTR_PRODUCT_CODE: Final = "product_code"
ATTR_TARIFF_CODE: Final = "tariff_code"
ATTR_STANDING_CHARGE: Final = "standing_charge"
ATTR_TIMEZONE: Final = "timezone"
ATTR_VALID_FROM: Final = "valid_from"
ATTR_VALID_TO: Final = "valid_to"
ATTR_NEXT_PRICE: Final = "next_price"

UK_TIMEZONE: Final = "Europe/London"

# Ofgem ("price cap" – often misremembered as Ofcom) average electricity unit
# rate for Direct Debit standard-credit customers, in p/kWh including VAT at
# the rate applying in each cap period.  The cap is reviewed every three
# months (January, April, July and October).  Rates after the last entry are
# carried forward from the newest known value and can be overridden per
# installation in the integration options.
PRICE_CAP_SCHEDULE: Final[list[tuple[date, date, float]]] = [
    (date(2024, 10, 1), date(2024, 12, 31), 24.50),
    (date(2025, 1, 1), date(2025, 3, 31), 24.50),
    (date(2025, 4, 1), date(2025, 6, 30), 24.50),
    (date(2025, 7, 1), date(2025, 9, 30), 22.36),
    (date(2025, 10, 1), date(2025, 12, 31), 24.50),
    (date(2026, 1, 1), date(2026, 3, 31), 27.69),
    (date(2026, 4, 1), date(2026, 6, 30), 24.67),
    (date(2026, 7, 1), date(2026, 9, 30), 26.11),
    (date(2026, 10, 1), date(2026, 12, 31), 26.32),
]

PRICE_CAP_SOURCE_OFGEM: Final = "ofgem"
PRICE_CAP_SOURCE_OVERRIDE: Final = "override"
PRICE_CAP_SOURCE_ESTIMATED: Final = "estimated"

# The next-day prices are published at approximately 16:00 UK time.  A refresh
# is scheduled shortly after to pick them up as soon as they appear.
DAILY_PUBLISH_HOUR: Final = 16
DAILY_PUBLISH_MINUTE: Final = 5

# Safety-net polling interval; precise refreshes are scheduled at each 30
# minute slot boundary and at the daily publish time.
FALLBACK_SCAN_INTERVAL_MINUTES: Final = 30

PLATFORMS: Final[list[str]] = ["sensor"]

# The bundled Lovelace card is served and registered with the frontend so it
# can be used as custom:octopus-agile-card without manual resource setup.
CARD_FILENAME: Final = "octopus-agile-card.js"
CARD_URL: Final = "/octopus_agile/static/octopus-agile-card.js"
