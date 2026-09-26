/*
  octopus-agile-card.js
  Lovelace card for the Octopus Agile Tariff integration.

  Draws the half-hourly price series (today / tomorrow) as a compact line
  chart with the Ofgem price cap as a dashed reference line. No external
  dependencies - it is a plain custom element that renders SVG.

  Usage:
    type: custom:octopus-agile-card
    entity: sensor.octopus_agile_london_current_price
*/
(() => {
  "use strict";

  const CARD_TYPE = "octopus-agile-card";
  const CARD_VERSION = "1.0.0";

  const formatPrice = (value) => {
    if (value === null || value === undefined || Number.isNaN(value)) return "—";
    return `${Number(value).toFixed(2)}p`;
  };

  const formatTime = (iso, timeZone) => {
    if (!iso) return "--:--";
    const date = new Date(iso);
    if (Number.isNaN(date.getTime())) return "--:--";
    try {
      return date.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
        timeZone,
      });
    } catch (err) {
      return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", hour12: false });
    }
  };

  const niceStep = (range) => {
    const rough = range / 3;
    const pow = Math.pow(10, Math.floor(Math.log10(rough || 1)));
    const frac = rough / pow;
    const nice = frac <= 1 ? 1 : frac <= 2 ? 2 : frac <= 5 ? 5 : 10;
    return nice * pow;
  };

  class OctopusAgileCard extends HTMLElement {
    constructor() {
      super();
      this.attachShadow({ mode: "open" });
      this._config = {};
      this._hass = null;
      this._entity = null;
      this._view = "today";
      this._stamp = null;
      this._uid = `oa-${Math.random().toString(36).slice(2, 9)}`;
      this._ro = null;
    }

    static getStubConfig() {
      return { entity: "sensor.octopus_agile_london_current_price", height: 210 };
    }

    getCardSize() {
      return Math.round(((this._config.height || 210) + 88) / 50);
    }

    setConfig(config) {
      if (!config) throw new Error("Invalid configuration");
      this._config = {
        title: "",
        height: 210,
        show_cap: true,
        show_now: true,
        tabs: true,
        ...config,
      };
      if (!this._entity && config.entity) this._entity = config.entity;
    }

    set hass(hass) {
      this._hass = hass;
      const entity = this._findEntity();
      const state = entity ? hass.states[entity] : null;
      const width = this._measure();
      const stamp = state
        ? `${entity}|${state.state}|${state.last_updated}|${this._view}|${width}|${JSON.stringify(this._config)}`
        : `missing|${entity}|${width}`;
      if (stamp === this._stamp) return;
      this._stamp = stamp;
      this._render(entity, state, width);
    }

    connectedCallback() {
      if (typeof ResizeObserver !== "undefined" && !this._ro) {
        this._ro = new ResizeObserver(() => {
          const width = this._measure();
          if (Math.abs(width - (this._lastWidth || 0)) > 4) {
            this._stamp = null;
            if (this._hass) this.hass = this._hass;
          }
        });
        this._ro.observe(this);
      }
      if (this._hass && !this._stamp) this.hass = this._hass;
    }

    disconnectedCallback() {
      if (this._ro) {
        this._ro.disconnect();
        this._ro = null;
      }
    }

    _measure() {
      const width = this.clientWidth || 360;
      this._lastWidth = width;
      return Math.max(width, 240);
    }

    _findEntity() {
      if (this._hass === null) return null;
      if (this._config.entity) return this._config.entity;
      if (this._entity && this._hass.states[this._entity]) return this._entity;
      // Auto-detect: first sensor exposing the Agile price series.
      const candidates = Object.keys(this._hass.states).filter((id) => {
        const state = this._hass.states[id];
        return (
          id.startsWith("sensor.") &&
          state.attributes &&
          Array.isArray(state.attributes.today) &&
          "price_cap" in state.attributes
        );
      });
      candidates.sort();
      this._entity = candidates.length ? candidates[0] : null;
      return this._entity;
    }

    /* ------------------------------------------------------------------ */
    /* Rendering                                                           */
    /* ------------------------------------------------------------------ */

    _render(entity, state, width) {
      const cfg = this._config;
      const attrs = (state && state.attributes) || {};
      const tz = attrs.timezone || undefined;
      const today = Array.isArray(attrs.today) ? attrs.today : [];
      const tomorrow = Array.isArray(attrs.tomorrow) ? attrs.tomorrow : [];
      const hasTabs = cfg.tabs && today.length > 0 && tomorrow.length > 0;
      if (!hasTabs && this._view !== "today") this._view = "today";
      const series = this._view === "tomorrow" ? tomorrow : today;
      const cap = cfg.show_cap && typeof attrs.price_cap === "number" ? attrs.price_cap : null;
      const region = attrs.region || "";
      const title = cfg.title || (region ? `Octopus Agile · ${region}` : "Octopus Agile");
      const nowPrice = state && !Number.isNaN(parseFloat(state.state)) ? parseFloat(state.state) : null;

      const height = Math.max(cfg.height || 210, 140);
      const geom = this._geometry(series, cap, width, height);

      const chips = this._chipsHtml(
        series,
        cap,
        tz,
        this._view,
        this._view === "today" && tomorrow.length === 0
      );
      const chart = series.length
        ? this._chartHtml(series, cap, tz, geom, attrs)
        : `<div class="empty">${
            this._view === "tomorrow"
              ? "No prices published yet. Tomorrow's rates appear around 16:00 UK time."
              : "No prices published yet. Rates for the next day appear around 16:00 UK time."
          }</div>`;

      const tabsHtml = hasTabs
        ? `<div class="tabs">
             <button class="tab${this._view === "today" ? " active" : ""}" data-view="today">Today</button>
             <button class="tab${this._view === "tomorrow" ? " active" : ""}" data-view="tomorrow">Tomorrow</button>
           </div>`
        : "";

      this.shadowRoot.innerHTML = `
        <style>${this._styles()}</style>
        <ha-card>
          <div class="wrap">
            <div class="head">
              <div class="head-left">
                <div class="title">${title}</div>
                <div class="sub">${attrs.tariff_code ? attrs.tariff_code : ""}</div>
              </div>
              <div class="head-right">
                <div class="now">${nowPrice !== null ? formatPrice(nowPrice) : "—"}</div>
                <div class="now-sub">now</div>
              </div>
              ${tabsHtml}
            </div>
            ${chips}
            ${chart}
            <div class="tip" style="display:none"></div>
          </div>
        </ha-card>
      `;

      const tabs = this.shadowRoot.querySelectorAll(".tab");
      tabs.forEach((button) => {
        button.addEventListener("click", () => {
          this._view = button.dataset.view;
          this._stamp = null;
          this.hass = this._hass;
        });
      });

      if (series.length) this._bindPointer(series, tz, geom);
    }

    _geometry(series, cap, width, height) {
      const padL = 36;
      const padR = 14;
      const padT = 12;
      const padB = 20;
      const plotW = Math.max(width - padL - padR, 10);
      const plotH = Math.max(height - padT - padB, 40);
      if (!series.length) {
        return { width, height, padL, padR, padT, padB, plotW, plotH, yMin: 0, yMax: 1 };
      }
      const prices = series.map((p) => p.price);
      let yMin = Math.min(...prices);
      let yMax = Math.max(...prices);
      if (cap !== null && cap !== undefined) {
        yMin = Math.min(yMin, cap);
        yMax = Math.max(yMax, cap);
      }
      const span = yMax - yMin || Math.max(Math.abs(yMax) * 0.2, 1);
      yMax += span * 0.14;
      yMin -= span * 0.14;
      if (Math.min(...prices) >= 0 && (cap === null || cap >= 0)) {
        yMin = Math.max(0, yMin);
      }
      return { width, height, padL, padR, padT, padB, plotW, plotH, yMin, yMax };
    }

    _xAt(geom, index, count) {
      if (count <= 1) return geom.padL + geom.plotW / 2;
      return geom.padL + (geom.plotW * (index + 0.5)) / count;
    }

    _yAt(geom, price) {
      const range = geom.yMax - geom.yMin || 1;
      return geom.padT + geom.plotH * (1 - (price - geom.yMin) / range);
    }

    _chipsHtml(series, cap, tz, view, hintTomorrow) {
      if (!series.length) return "";
      const prices = series.map((p) => p.price);
      const min = Math.min(...prices);
      const max = Math.max(...prices);
      const avg = prices.reduce((a, b) => a + b, 0) / prices.length;
      const capChip =
        cap !== null && cap !== undefined ? `<span class="chip cap">Cap ${formatPrice(cap)}</span>` : "";
      const hintChip = hintTomorrow
        ? `<span class="chip hint">Tomorrow · after ~16:00</span>`
        : "";
      return `
        <div class="chips">
          <span class="chip">Min ${formatPrice(min)}</span>
          <span class="chip">Avg ${formatPrice(avg)}</span>
          <span class="chip">Max ${formatPrice(max)}</span>
          ${capChip}
          ${hintChip}
        </div>
      `;
    }

    _chartHtml(series, cap, tz, geom, attrs) {
      const { width, height, padL, padT, padR, padB, plotW, plotH } = geom;
      const count = series.length;

      // Line + area paths through slot centres.
      const points = series.map((p, i) => [this._xAt(geom, i, count), this._yAt(geom, p.price)]);
      const linePath = points
        .map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`)
        .join(" ");
      const baseline = padT + plotH;
      const areaPath = `${linePath} L${points[points.length - 1][0].toFixed(1)},${baseline.toFixed(1)} L${points[0][0].toFixed(1)},${baseline.toFixed(1)} Z`;

      // Y grid + labels.
      const step = niceStep(geom.yMax - geom.yMin);
      const ticks = [];
      for (let v = Math.ceil(geom.yMin / step) * step; v <= geom.yMax + 1e-9; v += step) {
        ticks.push(v);
      }
      const grid = ticks
        .map((v) => {
          const y = this._yAt(geom, v);
          return `
            <line class="grid" x1="${padL}" y1="${y.toFixed(1)}" x2="${(padL + plotW).toFixed(1)}" y2="${y.toFixed(1)}"/>
            <text class="axis" x="${padL - 6}" y="${(y + 3).toFixed(1)}" text-anchor="end">${v.toFixed(step < 1 ? 1 : 0)}p</text>
          `;
        })
        .join("");

      // Zero line when negative prices exist.
      const zeroLine =
        geom.yMin < 0 && geom.yMax > 0
          ? `<line class="zero" x1="${padL}" y1="${this._yAt(geom, 0).toFixed(1)}" x2="${(padL + plotW).toFixed(1)}" y2="${this._yAt(geom, 0).toFixed(1)}"/>`
          : "";

      // X labels every 3h (6 slots); every 6h on narrow screens.
      const everyN = width < 360 ? 12 : 6;
      const xLabels = series
        .map((p, i) => {
          if (i % everyN !== 0) return "";
          const x = this._xAt(geom, i, count);
          return `<text class="axis" x="${x.toFixed(1)}" y="${(height - 6).toFixed(1)}" text-anchor="middle">${formatTime(p.start, tz)}</text>`;
        })
        .join("");

      // Cap reference line.
      let capLine = "";
      if (cap !== null && cap !== undefined) {
        const y = this._yAt(geom, cap);
        capLine = `
          <line class="cap" x1="${padL}" y1="${y.toFixed(1)}" x2="${(padL + plotW).toFixed(1)}" y2="${y.toFixed(1)}"/>
          <text class="cap-label" x="${(padL + plotW).toFixed(1)}" y="${Math.max(y - 5, padT + 8).toFixed(1)}" text-anchor="end">Cap ${formatPrice(cap)}</text>
        `;
      }

      // "Now" marker on today's chart.
      let nowLine = "";
      if (this._config.show_now && this._view === "today") {
        const now = Date.now();
        const idx = series.findIndex((p) => {
          const s = new Date(p.start).getTime();
          const e = new Date(p.end).getTime();
          return now >= s && now < e;
        });
        if (idx >= 0) {
          const x = this._xAt(geom, idx, count);
          nowLine = `
            <line class="now" x1="${x.toFixed(1)}" y1="${padT}" x2="${x.toFixed(1)}" y2="${(padT + plotH).toFixed(1)}"/>
            <text class="now-label" x="${x.toFixed(1)}" y="${padT - 2}" text-anchor="middle">now</text>
          `;
        }
      }

      return `
        <div class="chart-wrap">
          <svg class="chart" width="${width}" height="${height}" viewBox="0 0 ${width} ${height}">
            <defs>
              <linearGradient id="${this._uid}" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" class="fill-top"/>
                <stop offset="100%" class="fill-bottom"/>
              </linearGradient>
            </defs>
            ${grid}
            ${zeroLine}
            <path class="area" d="${areaPath}" fill="url(#${this._uid})"/>
            <path class="line" d="${linePath}"/>
            ${capLine}
            ${nowLine}
            ${xLabels}
            <line class="hoverline" x1="0" y1="${padT}" x2="0" y2="${(padT + plotH).toFixed(1)}" style="display:none"/>
            <circle class="hoverdot" r="4" cx="0" cy="0" style="display:none"/>
          </svg>
        </div>
      `;
    }

    _bindPointer(series, tz, geom) {
      const wrap = this.shadowRoot.querySelector(".chart-wrap");
      const tip = this.shadowRoot.querySelector(".tip");
      const hoverline = this.shadowRoot.querySelector(".hoverline");
      const hoverdot = this.shadowRoot.querySelector(".hoverdot");
      if (!wrap || !tip) return;

      const cap = this._config.show_cap ? this._capValue() : null;

      const move = (event) => {
        const rect = wrap.getBoundingClientRect();
        const x = event.clientX - rect.left;
        const count = series.length;
        let idx = Math.round(((x - geom.padL) / geom.plotW) * count - 0.5);
        idx = Math.max(0, Math.min(count - 1, idx));
        const point = series[idx];
        const px = this._xAt(geom, idx, count);
        const py = this._yAt(geom, point.price);

        hoverline.setAttribute("x1", px.toFixed(1));
        hoverline.setAttribute("x2", px.toFixed(1));
        hoverline.style.display = "";
        hoverdot.setAttribute("cx", px.toFixed(1));
        hoverdot.setAttribute("cy", py.toFixed(1));
        hoverdot.style.display = "";

        const above = cap !== null && cap !== undefined && point.price > cap;
        tip.innerHTML = `
          <div class="tip-time">${formatTime(point.start, tz)} – ${formatTime(point.end, tz)}</div>
          <div class="tip-price${above ? " above" : ""}">${formatPrice(point.price)}</div>
        `;
        tip.style.display = "block";
        const tipWidth = 110;
        const left = Math.max(4, Math.min(px - tipWidth / 2, geom.width - tipWidth - 4));
        tip.style.left = `${left}px`;
        tip.style.top = `${Math.max(4, py - 52)}px`;
      };

      const leave = () => {
        tip.style.display = "none";
        hoverline.style.display = "none";
        hoverdot.style.display = "none";
      };

      wrap.addEventListener("pointermove", move);
      wrap.addEventListener("pointerdown", move);
      wrap.addEventListener("pointerleave", leave);
    }

    _capValue() {
      const attrs =
        (this._hass && this._entity && this._hass.states[this._entity]?.attributes) || {};
      return typeof attrs.price_cap === "number" ? attrs.price_cap : null;
    }

    _styles() {
      return `
        :host { display: block; }
        ha-card {
          padding: 12px 12px 8px 12px;
          overflow: hidden;
          background: var(--card-background-color, var(--paper-card-background-color, #fff));
          border-radius: var(--ha-card-border-radius, 12px);
        }
        .wrap { position: relative; }
        .head {
          display: flex;
          align-items: flex-start;
          justify-content: space-between;
          gap: 8px;
          flex-wrap: wrap;
        }
        .title {
          font-weight: 600;
          font-size: 14px;
          color: var(--primary-text-color, #212121);
          line-height: 1.3;
        }
        .sub {
          font-size: 10px;
          color: var(--secondary-text-color, #9e9e9e);
          margin-top: 1px;
        }
        .head-right { text-align: right; }
        .now {
          font-size: 20px;
          font-weight: 700;
          color: var(--primary-color, #03a9f4);
          line-height: 1.1;
        }
        .now-sub {
          font-size: 9px;
          text-transform: uppercase;
          letter-spacing: 0.08em;
          color: var(--secondary-text-color, #9e9e9e);
        }
        .tabs {
          display: flex;
          gap: 4px;
          margin-left: auto;
          align-self: center;
        }
        .tab {
          border: 1px solid var(--divider-color, #e0e0e0);
          background: transparent;
          color: var(--secondary-text-color, #9e9e9e);
          border-radius: 999px;
          font-size: 11px;
          padding: 3px 10px;
          cursor: pointer;
        }
        .tab.active {
          background: var(--primary-color, #03a9f4);
          border-color: var(--primary-color, #03a9f4);
          color: var(--text-primary-color, #fff);
        }
        .chips {
          display: flex;
          flex-wrap: wrap;
          gap: 6px;
          margin: 8px 0 2px 0;
        }
        .chip {
          font-size: 11px;
          color: var(--secondary-text-color, #9e9e9e);
          background: var(--secondary-background-color, rgba(127,127,127,0.08));
          border-radius: 6px;
          padding: 2px 7px;
          white-space: nowrap;
        }
        .chip.cap { color: var(--warning-color, #ff9800); }
        .chip.hint { color: var(--primary-color, #03a9f4); font-style: italic; }
        .chart-wrap {
          position: relative;
          touch-action: pan-y;
          margin-top: 2px;
        }
        .chart { display: block; }
        .grid { stroke: var(--divider-color, #e0e0e0); stroke-width: 1; }
        .zero { stroke: var(--divider-color, #e0e0e0); stroke-width: 1; stroke-dasharray: 1 3; }
        .axis {
          fill: var(--secondary-text-color, #9e9e9e);
          font-size: 9px;
          font-family: var(--ha-card-header-font-family, inherit);
        }
        .line {
          fill: none;
          stroke: var(--primary-color, #03a9f4);
          stroke-width: 2;
          stroke-linejoin: round;
          stroke-linecap: round;
        }
        .fill-top { stop-color: var(--primary-color, #03a9f4); stop-opacity: 0.30; }
        .fill-bottom { stop-color: var(--primary-color, #03a9f4); stop-opacity: 0.02; }
        .cap {
          stroke: var(--warning-color, #ff9800);
          stroke-width: 1.5;
          stroke-dasharray: 6 4;
        }
        .cap-label {
          fill: var(--warning-color, #ff9800);
          font-size: 9px;
          font-weight: 600;
          font-family: var(--ha-card-header-font-family, inherit);
        }
        .now {
          stroke: var(--primary-color, #03a9f4);
          stroke-width: 1;
          stroke-dasharray: 2 3;
          opacity: 0.7;
        }
        .now-label {
          fill: var(--primary-color, #03a9f4);
          font-size: 8px;
          font-weight: 600;
          font-family: var(--ha-card-header-font-family, inherit);
        }
        .hoverline {
          stroke: var(--secondary-text-color, #9e9e9e);
          stroke-width: 1;
          stroke-dasharray: 2 2;
        }
        .hoverdot {
          fill: var(--card-background-color, #fff);
          stroke: var(--primary-color, #03a9f4);
          stroke-width: 2;
        }
        .empty {
          color: var(--secondary-text-color, #9e9e9e);
          font-size: 12px;
          text-align: center;
          padding: 28px 8px 32px 8px;
        }
        .tip {
          position: absolute;
          pointer-events: none;
          background: var(--card-background-color, #fff);
          border: 1px solid var(--divider-color, #e0e0e0);
          border-radius: 8px;
          box-shadow: 0 2px 8px rgba(0,0,0,0.18);
          padding: 5px 9px;
          min-width: 92px;
          z-index: 2;
        }
        .tip-time {
          font-size: 10px;
          color: var(--secondary-text-color, #9e9e9e);
          white-space: nowrap;
        }
        .tip-price {
          font-size: 13px;
          font-weight: 700;
          color: var(--primary-text-color, #212121);
        }
        .tip-price.above { color: var(--error-color, #f44336); }
      `;
    }
  }

  if (!customElements.get(CARD_TYPE)) {
    customElements.define(CARD_TYPE, OctopusAgileCard);
  }

  window.customCards = window.customCards || [];
  window.customCards.push({
    type: CARD_TYPE,
    name: "Octopus Agile Card",
    description: "Half-hourly Octopus Agile prices versus the Ofgem price cap.",
    preview: true,
    documentationURL: "https://github.com/GirthiusMaximus/a_a1",
  });

  console.info(
    `%c OCTOPUS-AGILE-CARD %c v${CARD_VERSION} `,
    "color:#fff;background:#e06900;font-weight:bold",
    "color:#e06900;background:#fff;font-weight:bold"
  );
})();
