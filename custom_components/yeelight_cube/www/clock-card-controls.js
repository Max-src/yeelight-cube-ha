// The clock card's controls below the gallery: the Content and Format
// toggles, the Color Modes row and the lamp sliders (speed, intensity,
// brightness). Mixed into YeelightCubeClockCard.
import { html, unsafeHTML } from "./lib/lit-all.js";
import {
  DEFAULT_BUTTON_STYLE,
  DEFAULT_BUTTON_CONTENT_MODE,
} from "./action-button-utils.js";
import { renderActionButtonGroup } from "./action-button-ui.js";
import { colorModeRow } from "./color-mode-ui.js";
import { matchingColorOption } from "./color-mode-selector-utils.js";
import {
  renderSliderGroup,
  stableSliderMarkup,
  brightnessPctToRaw,
  brightnessRawToPct,
  speedRawToPct,
  intensityRawToPct,
  sliderWhenUsed,
} from "./slider-control-utils.js";
import { clockStyleTakes } from "./clock-preview-utils.js";
import { chosenIntensity, chosenSpeed } from "./lamp-renderers.js";

const CONTENT_OPTIONS = [
  { value: "time", label: "Time", icon: "mdi:clock-outline" },
  { value: "time_date", label: "Time & Date", icon: "mdi:calendar-clock" },
  { value: "date", label: "Date", icon: "mdi:calendar" },
];

export const ClockControlsMixin = (Base) => class extends Base {
  _controlGroup(options, onChange) {
    return renderActionButtonGroup(
      {
        buttonStyle: this.config.buttons_style || DEFAULT_BUTTON_STYLE,
        contentMode:
          this.config.buttons_content_mode || DEFAULT_BUTTON_CONTENT_MODE,
        ...options,
      },
      onChange,
    );
  }

  _toggleFormat(value) {
    const a = this._attrs();
    this._applyFormat(
      value === "twelve"
        ? { twelve_hour: !a.clock_12_hour }
        : { colon_blink: !a.clock_colon_blink },
    );
  }

  _renderContentToggle(a) {
    const cur = a.clock_content || (a.clock_show_date ? "time_date" : "time");
    return html`<div class="section">
      <div data-clock-control="content">
        ${this._controlGroup(
          { label: "Content", items: CONTENT_OPTIONS, value: cur },
          (value) => this._applyContent(value),
        )}
      </div>
    </div>`;
  }

  _renderFormatToggles(a) {
    const twelve = !!a.clock_12_hour;
    const blink = !!a.clock_colon_blink;
    return html`<div
      class="section"
      style="--ctl-accent: color-mix(in srgb, var(--primary-color, #1976d2) 58%, #12a594);"
    >
      <div
        data-clock-control="format"
        style="--primary-color: var(--ctl-accent); --primary-color-dark: color-mix(in srgb, var(--ctl-accent) 74%, #000);"
      >
        ${this._controlGroup(
          {
            label: "Format",
            multiple: true,
            items: [
              {
                value: "twelve",
                label: "12-hour",
                icon: "mdi:hours-12",
                selected: twelve,
                states: {
                  on: {
                    label: "12-hour",
                    icon: "mdi:hours-12",
                    title: "12-hour. Switch to 24-hour",
                  },
                  off: {
                    label: "24-hour",
                    icon: "mdi:hours-24",
                    title: "24-hour. Switch to 12-hour",
                  },
                },
              },
              {
                value: "colon",
                label: "Colon blinks",
                icon: "mdi:animation-outline",
                selected: blink,
                states: {
                  on: {
                    label: "Colon blinks",
                    icon: "mdi:animation-play-outline",
                    title: "Colon blinks. Switch to steady",
                  },
                  off: {
                    label: "Colon steady",
                    icon: "mdi:pause-circle-outline",
                    title: "Colon steady. Enable blinking",
                  },
                },
              },
            ],
          },
          (value) => this._toggleFormat(value),
        )}
      </div>
    </div>`;
  }

  _renderColorMode(a) {
    const mode = this._currentColorMode(a);
    const options = this._colors.options();
    const saved =
      mode === "custom" && !this._customDraft
        ? matchingColorOption(
            options,
            this._customPresetColor,
            this._selectedColorPresetId,
            this._selectedColorPresetName,
          )
        : null;
    return html` <div
      class="section"
      style="--ctl-accent: color-mix(in srgb, var(--primary-color, #1976d2) 58%, #7c5cbf);"
    >
      ${colorModeRow(this, {
        options,
        lamp: mode === "custom" ? saved?.value : mode,
        draft: this._customMode && this._customDraft,
        saveKinds: this._saveKinds(),
        previewAttrs: this._previewAttrs(this._currentStyle()),
        onSaved: (detail) => this._onPresetSaved(detail),
      })}
    </div>`;
  }

  _renderSliders(a) {
    // Speed and intensity only while the clock's background reads them;
    // otherwise hidden or greyed out (sliderWhenUsed).
    const style = this._lampStyle();
    const showBrightness = this.config.show_brightness === true;
    const showSpeed = this.config.show_animation_speed !== false;
    const showIntensity = this.config.show_intensity !== false;

    const controls = [];
    if (showBrightness) {
      const briRaw =
        this._brightnessPreview != null
          ? brightnessPctToRaw(this._brightnessPreview)
          : Number(this._attrs().brightness) || 0;
      const briPct =
        this._brightnessPreview != null
          ? this._brightnessPreview
          : brightnessRawToPct(briRaw);
      controls.push({
        label: "Brightness",
        gc: { ...this._brightnessGc(), rawValue: briRaw },
        value: briPct,
        ns: "brightness",
      });
    }
    if (showSpeed) {
      const raw = chosenSpeed(a);
      controls.push(sliderWhenUsed(this.config, clockStyleTakes(style, "speed"), {
        label: "Speed",
        gc: { ...this._speedGc(), rawValue: this._speedPreview ?? raw },
        value: this._lampSliders.value("speed") ?? speedRawToPct(raw),
        ns: "speed",
      }));
    }
    if (showIntensity) {
      const raw = chosenIntensity(a);
      controls.push(sliderWhenUsed(this.config, clockStyleTakes(style, "intensity"), {
        label: "Intensity",
        gc: { ...this._intensityGc(), rawValue: this._intensityPreview ?? raw },
        value: this._lampSliders.value("intensity") ?? intensityRawToPct(raw),
        ns: "intensity",
      }));
    }
    if (!controls.some(Boolean)) return "";
    // The shared slider renderer emits an HTML string naming this card's
    // `_sl*` handlers in data-on-* attributes (see host-events.js).
    return html`<div class="section section-sliders">
      ${unsafeHTML(
        stableSliderMarkup(this, "sliders", renderSliderGroup(controls)),
      )}
    </div>`;
  }
};
