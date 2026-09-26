# Octopus Agile Tariff for Home Assistant

A Home Assistant (HACS-compatible) integration for the UK **Octopus Energy Agile** tariff.
It pulls the half-hourly unit prices straight from the
[public Octopus Energy API](https://developer.octopus.energy/docs/api/) and presents them
as a compact 30-minute breakdown — including a line chart of the day's prices against the
current **Ofgem energy price cap** — that works beautifully on a phone.

> Note: the energy price cap is set by **Ofgem** (the energy regulator), not Ofcom.

![Agile card example](https://img.shields.io/badge/Agile-30_minute_breakdown-e06900)

## Features

- **30-minute price breakdown** – every published half-hour slot for today and tomorrow,
  in p/kWh including VAT.
- **Automatic updates** – prices are refreshed at every 30-minute slot boundary and at
  **~16:05 UK time** each day, which is when Octopus publish the next day's rates.
  A slower 30-minute fallback poll keeps things safe.
- **Ofgem price cap comparison** – a dashed reference line on the chart shows the current
  price cap unit rate (built-in quarterly schedule, overridable per region).
- **Compact Lovelace card** (`custom:octopus-agile-card`) – responsive SVG line chart with
  today/tomorrow tabs, now marker, min/avg/max/cap chips and tap/hover tooltips.
  Sized for mobile dashboards (~210px tall, full width).
- **Sensor entities** for automations: current price, next price, today's min/max/average,
  tomorrow's average and today's cheapest slot.
- **All 14 UK regions**, no API key required.

## Installation

### HACS (recommended)

1. In HACS, go to **Integrations → Custom repositories**.
2. Add `https://github.com/GirthiusMaximus/a_a1` as an **Integration**.
3. Install **Octopus Agile Tariff**, then restart Home Assistant.

### Manual

1. Copy `custom_components/octopus_agile` into your Home Assistant `config/custom_components/`
   directory.
2. Restart Home Assistant.

## Configuration

1. Go to **Settings → Devices & Services → Add Integration → Octopus Agile Tariff**.
2. Choose your **region** (the GSP group letter shown on your electricity bill):

   | Code | Region | Code | Region |
   |------|--------|------|--------|
   | A | Eastern England | J | South East England |
   | B | East Midlands | K | South Wales |
   | C | London | L | South West England |
   | D | Merseyside & North Wales | M | Yorkshire |
   | E | West Midlands | N | Southern Scotland |
   | F | North East England | P | Northern Scotland |
   | G | North West England | H | Southern England |

3. Optionally override the **product code** (defaults to the current `AGILE-24-10-01`) and
   the **price cap** in p/kWh.

The tariff code used is `E-1R-<product>-<region>`, e.g. `E-1R-AGILE-24-10-01-C` for London.

### Price cap (Ofgem)

The cap line uses the built-in schedule of Ofgem's **average electricity unit rate**
(Great Britain, Direct Debit, including the VAT rate applying in each cap period):

| Cap period | Unit rate | Cap period | Unit rate |
|------------|-----------|------------|-----------|
| Jul–Sep 2025 | 22.36p | Jan–Mar 2026 | 27.69p |
| Oct–Dec 2025 | 24.50p | Apr–Jun 2026 | 24.67p |
| Jul–Sep 2026 | 26.11p | **Oct–Dec 2026** | **26.32p** |

Regional caps differ by up to ~2.5p/kWh (e.g. East Midlands is cheapest, Merseyside &
North Wales dearest). For an exact match, set the **price cap override** in the integration
options to your regional rate from your bill or Ofgem's tables. After the last scheduled
period the newest value is carried forward and flagged as `estimated` until the integration
is updated.

## Sensors

| Entity | State | Notes |
|--------|-------|-------|
| `current_price` | p/kWh of the live half-hour slot | Attributes include the full `today`/`tomorrow` 30-minute breakdown, `price_cap`, `standing_charge`, tariff details |
| `next_price` | p/kWh of the next slot | |
| `today_min` | cheapest slot price today | |
| `today_max` | dearest slot price today | |
| `today_average` | mean price today | |
| `tomorrow_average` | mean price tomorrow | `tomorrow_min` / `tomorrow_max` as attributes |
| `cheapest_slot_today` | price of today's cheapest slot | `valid_from` / `valid_to` / `is_past` attributes |

All price sensors use `p/kWh` and `state_class: measurement`, so they work with Home
Assistant statistics and history graphs out of the box.

## The chart card

The integration bundles a Lovelace card and registers it automatically (no manual
resource needed). If auto-registration is unavailable on your setup, add a manual
resource pointing at `/octopus_agile/static/octopus-agile-card.js` (or copy the file to
`config/www/` and use `/local/octopus-agile-card.js`).

```yaml
type: custom:octopus-agile-card
entity: sensor.octopus_agile_london_current_price
title: Agile · London      # optional, defaults to "Octopus Agile · <region>"
height: 210                # optional, chart height in px (compact on phones)
show_cap: true             # dashed Ofgem cap reference line
show_now: true             # vertical marker on the live slot
tabs: true                 # Today / Tomorrow switch (auto-hidden if no data)
```

The card shows, top to bottom: the region title and live price, Min/Avg/Max/Cap chips,
and the price line chart with the cap line. Tap or hover the chart for the exact
half-hour price. Everything scales to the card width, so a single-column phone dashboard
just works.

### Mobile dashboard example

```yaml
type: vertical
cards:
  - type: custom:octopus-agile-card
    entity: sensor.octopus_agile_london_current_price
  - type: entities
    entities:
      - entity: sensor.octopus_agile_london_current_price
        name: Now
      - entity: sensor.octopus_agile_london_next_price
        name: Next
      - entity: sensor.octopus_agile_london_cheapest_slot_today
        name: Cheapest today
```

## How the 30-minute data works

- Each half-hour slot has `start`, `end` (ISO timestamps in UK local time), `price`
  (p/kWh inc VAT) and `price_exc_vat`.
- Slots are grouped into `today` and `tomorrow` by UK calendar day (DST-safe).
- Octopus publish tomorrow's 48 slots at approximately **16:00 UK time**; the integration
  refreshes at **16:05** and the card's *Tomorrow* tab fills in automatically.
- Agile prices can go **negative** — the chart handles this and marks the zero line.

## Automations ideas

- Run the washing machine during the cheapest slot:
  trigger on `sensor.octopus_agile_london_cheapest_slot_today`'s `valid_from` attribute.
- Alert when tomorrow's average is unusually low:
  `sensor.octopus_agile_london_tomorrow_average` below a threshold.

## FAQ

**Why is there no data for tomorrow?**
Octopus release the next day's rates at ~16:00 UK time. Before that, tomorrow's list is
empty and the card shows a hint instead.

**Which price is shown – with or without VAT?**
Prices are shown **including VAT** (`value_inc_vat`), matching what you actually pay.
From October 2026 electricity VAT is 0%, and the API values follow that automatically.

**My regional cap isn't exactly right.**
The cap line is the GB average. Set your regional unit rate via
*Configure → price cap override* for an exact comparison.

**Can I track several regions?**
Yes — add the integration once per region (e.g. home and holiday home).

## Credits & data source

- Price data: [Octopus Energy REST API](https://developer.octopus.energy/docs/api/)
  (public, no key needed).
- Price cap: [Ofgem energy price cap](https://www.ofgem.gov.uk/information-consumers/energy-advice-households/energy-price-cap-unit-rates-and-standing-charges).
