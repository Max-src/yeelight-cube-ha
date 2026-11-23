// The native effects card's Color Modes: whether its lamps take a color,
// the modes offered and the one shown, and applying a mode or a picked
// color (with an effect that shows it on every lamp). Mixed into
// YeelightCubeNativeEffectsCard.
import { previewOnly } from "./offline-preview-state.js";
import { everyAvailable } from "./service-call-utils.js";

export const NativeEffectColorsMixin = (Base) => class extends Base {
  _supportsCustomColor() {
    if (previewOnly(this)) return true;
    return everyAvailable(this._hass, this.config, (entity, state) =>
      Object.hasOwn(state.attributes || {}, "native_effect_color"),
    );
  }

  // The saved colors and Add only where every lamp takes a color.
  _colorOptions() {
    return this._colors.options(this._supportsCustomColor());
  }

  // A clicked color mode shows at once (color-mode-controller.js).
  _currentColorSelection() {
    return this._colors.selection(this._lampColorSelection());
  }

  // The color mode the lamp shows (or the color being drafted).
  _lampColorSelection() {
    const attrs = this._attrs();
    if (this._customDraft && this._supportsCustomColor())
      return "__draft__";
    if (
      attrs.native_effect_color_mode &&
      attrs.native_effect_color_mode !== "normal"
    )
      return attrs.native_effect_color_mode;
    if (
      attrs.native_effect_color_mode === "normal" &&
      attrs.native_effect_color &&
      this._supportsCustomColor()
    ) {
      const matches = this._colors.presets().filter((preset) =>
        preset.color.every(
          (channel, index) => channel === attrs.native_effect_color[index],
        ),
      );
      const preset =
        matches.find((preset) => preset.id === this._selectedColorPresetId) ||
        matches[0];
      return preset ? `custom:${preset.id}` : "__draft__";
    }
    return "normal";
  }

  // Normalized color-mode key for favourites: "normal", a palette mode, or
  // "custom" (covers both a draft and a saved custom color preset).
  _colorModeKey() {
    const selection = this._currentColorSelection();
    if (selection === "normal") return "normal";
    if (selection === "__draft__" || selection.startsWith("custom:"))
      return "custom";
    return selection;
  }

  // RGB tuple recorded alongside a "custom" favourite.
  _currentCustomColor() {
    const attrs = this._attrs();
    const selection = this._currentColorSelection();
    if (selection === "__draft__")
      return this._customDraft || attrs.native_effect_color || null;
    if (selection.startsWith("custom:"))
      return this._colors.preset(selection)?.color || attrs.native_effect_color || null;
    return null;
  }

  async _applyCustomColor(color) {
    if (!this._supportsCustomColor()) return false;
    const effect = this._effectForColor("normal", color);
    if (!effect) {
      this._error =
        "No configured effect supports this color on all selected lamps.";
      return false;
    }
    const context = this._context;
    const version = this._nextSelection?.();
    this._colors.drop();
    const success = await this._command("set_native_effect", {
      effect,
      color_mode: "normal",
      color,
    });
    if (
      success &&
      context === this._context &&
      this._selectionVersion === version
    ) {
      this._customDraft = [...color];
      this._selectedColorPresetId = null;
      this._selected = effect;
    }
    return success;
  }

  async _applyColorMode(value) {
    if (value === "__pick__") {
      if (!this._supportsCustomColor()) return;
      // The picker at the row's Add (color-mode-ui).
      this._colors.openPicker(
        this._customDraft || this._attrs().native_effect_color,
        (rgb) => this._applyCustomColor(rgb),
      );
      return;
    }
    const preset = value.startsWith("custom:") ? this._colors.preset(value) : null;
    if (
      value.startsWith("custom:") &&
      (!preset || !this._supportsCustomColor())
    )
      return;
    const mode = preset ? "normal" : value;
    const effect = this._effectForColor(mode, preset?.color);
    if (!effect) {
      this._error =
        "No configured effect supports this color on all selected lamps.";
      return;
    }
    const context = this._context;
    const version = this._nextSelection?.();
    // Shown at once; kept once sent until the lamp reports it.
    const shown = this._colors.show(
      value,
      this._command("set_native_effect", {
        effect,
        color_mode: mode,
        ...(preset
          ? { color: [...preset.color] }
          : Object.hasOwn(this._attrs(), "native_effect_color")
            ? { color: "clear" }
            : {}),
      }),
    );
    this.requestUpdate();
    const success = await shown;
    if (
      success &&
      context === this._context &&
      this._selectionVersion === version
    ) {
      this._customDraft = null;
      this._selectedColorPresetId = preset?.id;
      this._selected = effect;
    }
  }
};
