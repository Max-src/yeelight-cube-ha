/**
 * angle-wheel-utils.js
 * Shared utility functions for angle wheel / rotary controls.
 * Used by both yeelight-cube-gradient-card.js and yeelight-cube-color-list-editor-card.js
 */

// Debounce time for angle updates (ms)
import {
  callServiceOnTargetEntities,
  getTargetEntities,
} from "./service-call-utils.js";
import { rgbToHex } from "./color-utils.js";
import { CALL_TIMEOUT_MS, withCallTimeout } from "./card-command-controller.js";

const ANGLE_UPDATE_DEBOUNCE_MS = 150;

export class AngleCommandController {
  constructor(onApplied = () => {}, onError = () => {}, timeoutMs = CALL_TIMEOUT_MS) {
    this.onApplied = onApplied;
    this.onError = onError;
    this.timeoutMs = timeoutMs;
    this.context = 0;
    this.timer = null;
    this.pending = null;
    this.sending = false;
  }

  schedule(hass, config, value, immediate = false) {
    const angle = Number.parseFloat(value);
    const targets = getTargetEntities(config);
    if (!hass || !targets.length || !Number.isFinite(angle)) return false;
    this.pending = {
      hass,
      config: { target_entities: [...targets] },
      angle: ((angle % 360) + 360) % 360,
      context: this.context,
    };
    clearTimeout(this.timer);
    this.timer = null;
    if (immediate) this.flush();
    else this.timer = setTimeout(() => this.flush(), ANGLE_UPDATE_DEBOUNCE_MS);
    return true;
  }

  async flush() {
    clearTimeout(this.timer);
    this.timer = null;
    if (this.sending) return;
    this.sending = true;
    try {
      while (this.pending && this.timer === null) {
        const command = this.pending;
        this.pending = null;
        if (command.context !== this.context) continue;
        try {
          // One unanswered call must not keep `sending` set and drop
          // every later angle.
          await withCallTimeout(
            callServiceOnTargetEntities(
              command.hass,
              command.config,
              "set_angle",
              { angle: command.angle },
            ),
            "set_angle",
            this.timeoutMs,
          );
          if (command.context === this.context) this.onApplied(command.angle);
        } catch (error) {
          if (command.context === this.context) this.onError(error);
        }
      }
    } finally {
      this.sending = false;
    }
  }

  reset() {
    this.context++;
    clearTimeout(this.timer);
    this.timer = null;
    this.pending = null;
  }
}

/**
 * Create SVG linear gradient stops for a wheel-style display.
 * @param {Array<Array<number>>} colors - Array of [r,g,b] arrays
 * @returns {string} SVG stop elements markup
 */
export function createWheelGradientStops(colors) {
  if (!colors || colors.length === 0) {
    return '<stop offset="0%" style="stop-color:#ff0000"/><stop offset="100%" style="stop-color:#ff0000"/>';
  }

  if (colors.length === 1) {
    const hex = rgbToHex(colors[0]);
    return `<stop offset="0%" style="stop-color:${hex}"/><stop offset="100%" style="stop-color:${hex}"/>`;
  }

  const stops = [];

  for (let i = 0; i < colors.length; i++) {
    const offset = (i / (colors.length - 1)) * 100;
    const hex = rgbToHex(colors[i]);
    stops.push(`<stop offset="${offset}%" style="stop-color:${hex}"/>`);
  }

  return stops.join("\n                  ");
}

