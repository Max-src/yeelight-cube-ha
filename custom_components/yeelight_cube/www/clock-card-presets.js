// The clock card's custom clock styles and color modes (shared presets): the
// gallery's rename and delete of a custom style, and a preset just saved from
// the Color Modes row. Mixed into YeelightCubeClockCard.
import {
  clockPresetLibrary,
  editClockPreset,
  clockColorPresetAction,
} from "./clock-preset-utils.js";

export const ClockPresetsMixin = (Base) => class extends Base {
  // A custom clock style of the gallery (key custom:<id>), or undefined.
  _presetOf(key) {
    const id = String(key).startsWith("custom:") ? key.slice(7) : null;
    return clockPresetLibrary(this._hass).find(
      (preset) => preset.id === id && (preset.kind || "style") === "style",
    );
  }

  // Custom clock styles are shared presets: renamed and deleted for every
  // card, at once (editClockPreset).
  async _renamePreset(key, name) {
    const preset = this._presetOf(key);
    if (!preset) return false;
    return editClockPreset(this._hass, "save_clock_preset", {
      preset_id: preset.id,
      name,
      color: preset.color,
      kind: "style",
    });
  }

  async _deletePreset(key) {
    const preset = this._presetOf(key);
    if (!preset) return false;
    return editClockPreset(this._hass, "delete_clock_preset", {
      preset_id: preset.id,
    });
  }

  _onPresetSaved({ kind, name, color }) {
    this._customDraft = null;
    if (kind === "color_mode") {
      this._selectedColorPresetId = null;
      this._selectedColorPresetName = name;
      this._customPresetColor = [...color];
      this._customMode = true;
      this._callSetClock(clockColorPresetAction({ color }));
      this.requestUpdate();
      return;
    }
    if (kind !== "style" || !name || !Array.isArray(color)) return;
    this._customPresetColor = null;
    this._customMode = false;
    this._revealSavedStyle = name;
    // That color is now owned by the new style, not the freeform Custom
    // slot — forget it so the next Custom pick doesn't reuse it, and mark it
    // pending so the mode reads Normal until the library echoes the preset.
    this._lastCustomHex = null;
    this._pendingStyleColor = [...color];
    this._callSetClock({
      style: "White",
      color_mode: "normal",
      color,
      activate: true,
    });
    this.requestUpdate();
  }
};
