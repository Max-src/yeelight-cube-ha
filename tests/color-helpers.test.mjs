// The shared color helpers (color-utils.js clampByte / scaleChannel /
// scalePixel / hexToRgb, color-adjustments.js hsvToRgb) against the inline
// code they replaced, over dense input grids: not one pixel may differ.
import test from "node:test";
import assert from "node:assert/strict";

import {
  clampByte,
  hexToRgb,
  rgbToCss,
  rgbToHex,
  scaleChannel,
  scalePixel,
} from "../custom_components/yeelight_cube/www/color-utils.js";
import { hsvToRgb } from "../custom_components/yeelight_cube/www/color-adjustments.js";
import { PALETTE_SOURCES } from "../custom_components/yeelight_cube/www/lamp-core.js";
import { renderNativeEffect } from "../custom_components/yeelight_cube/www/native-effect-preview.js";

// The former native-effect-preview.js clamp and hsv.
const formerClamp = (value) => Math.max(0, Math.min(255, Math.round(value)));
function formerHsv(hue, saturation = 1.0, value = 1.0) {
  hue = ((hue % 1) + 1) % 1;
  const i = Math.floor(hue * 6);
  const f = hue * 6 - i;
  const p = value * (1 - saturation);
  const q = value * (1 - f * saturation);
  const t = value * (1 - (1 - f) * saturation);
  const [r, g, b] = [
    [value, t, p],
    [q, value, p],
    [p, value, t],
    [p, q, value],
    [t, p, value],
    [value, p, q],
  ][i % 6];
  return [formerClamp(r * 255), formerClamp(g * 255), formerClamp(b * 255)];
}
// What native-effect-preview.js hsv does now.
function sharedHsv(hue, saturation = 1.0, value = 1.0) {
  const [r, g, b] = hsvToRgb(((hue % 1) + 1) % 1, saturation, value);
  return [clampByte(r * 255), clampByte(g * 255), clampByte(b * 255)];
}

// A small deterministic generator, so a failure is reproducible.
function random(seed) {
  let state = seed >>> 0;
  return () => {
    state = (Math.imul(state, 1664525) + 1013904223) >>> 0;
    return state / 2 ** 32;
  };
}

test("clampByte is the former native-effect-preview clamp", () => {
  for (let value = -300; value <= 600; value += 0.03125) assert.equal(clampByte(value), formerClamp(value));
  for (const value of [NaN, Infinity, -Infinity, -0, 0.5, 1.5, 254.5, 255.5, 0.49999999999999994])
    assert.equal(Object.is(clampByte(value), formerClamp(value)), true, String(value));
});

test("hsvToRgb with the hue wrapped is the former native-effect-preview hsv", () => {
  const steps = 96;
  for (let h = -2 * steps; h <= 3 * steps; h++)
    for (let s = 0; s <= steps; s += 4)
      for (let v = 0; v <= steps; v += 4) {
        const args = [h / steps, s / steps, v / steps];
        assert.deepEqual(sharedHsv(...args), formerHsv(...args), args.join());
      }
  const next = random(71);
  for (let n = 0; n < 200000; n++) {
    const args = [next() * 40 - 20, next(), 0.35 + 0.65 * next()];
    assert.deepEqual(sharedHsv(...args), formerHsv(...args), args.join());
  }
  for (const hue of [1 - 2 ** -53, -(2 ** -60), 1e-17, -1e-17, 5 / 6, 1 / 6, 0.5])
    assert.deepEqual(sharedHsv(hue, 0.8, 1), formerHsv(hue, 0.8, 1), String(hue));
});

test("the slot 71 gradient is unchanged", () => {
  // Every pixel through the former hsv, as renderGradient drew it.
  for (const direction of ["Up", "Down", "Left", "Right"])
    for (const columns of [null, 30, 40])
      for (let phase = 0; phase < 60; phase += 0.37) {
        const frame = renderNativeEffect("Not a lamp effect", phase, direction, null, null, 50, null, null, null, null, null, null, columns);
        const width = frame.length / 5;
        frame.forEach((pixel, index) => {
          const x = (index % width) / (width - 1);
          const y = Math.floor(index / width) / 4;
          const along = direction === "Down" ? 1 - y : direction === "Left" ? 1 - x : direction === "Right" ? x : y;
          const wave = (Math.sin((along * 2 - phase) * Math.PI * 2) + 1) / 2;
          assert.deepEqual(pixel, formerHsv(x + phase * 0.05, 0.8, 0.35 + 0.65 * wave));
        });
      }
});

test("scaleChannel / scalePixel are the former brightness scaling", () => {
  const former = (channel, scale) => Math.min(255, Math.round(channel * scale));
  for (let scale = 0; scale <= 4; scale += 1 / 64)
    for (let channel = 0; channel <= 255; channel++)
      assert.equal(scaleChannel(channel, scale), former(channel, scale));
  const next = random(5);
  for (let n = 0; n < 100000; n++) {
    const pixel = [next() * 300 - 20, next() * 255, Math.floor(next() * 256)];
    const scale = next() * 3;
    assert.deepEqual(scalePixel(pixel, scale), pixel.map((channel) => former(channel, scale)));
  }
});

test("rgbToCss / rgbToHex keep their channel coercion", () => {
  const formerChannel = (value) => Math.max(0, Math.min(255, Math.round(Number(value)) || 0));
  const formerHexChannel = (value) => Math.max(0, Math.min(255, Math.round(Number(value) || 0)));
  const values = [NaN, undefined, null, "", "12", "abc", "7.5", Infinity, -Infinity, -0, -0.4, -0.5, -0.6, true, [], [3]];
  for (let value = -40; value <= 300; value += 0.25) values.push(value);
  for (const value of values) {
    const rgb = [value, 0, value];
    assert.equal(rgbToCss(rgb), `rgb(${formerChannel(value)},${formerChannel(0)},${formerChannel(value)})`, String(value));
    assert.equal(
      rgbToHex(rgb),
      `#${[value, 0, value].map((channel) => formerHexChannel(channel).toString(16).padStart(2, "0")).join("")}`,
      String(value),
    );
  }
});

test("hexToRgb reads the lamp's palettes and the picker's #rrggbb as before", () => {
  const former = (text) => [0, 2, 4].map((at) => parseInt(text.slice(at, at + 2), 16));
  for (const source of Object.values(PALETTE_SOURCES))
    for (const text of source.split(" ")) assert.deepEqual(hexToRgb(text), former(text), text);
  const picker = (hex) => [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16));
  for (let value = 0; value < 0x1000000; value += 0x10101 + 7) {
    const hex = `#${value.toString(16).padStart(6, "0")}`;
    assert.deepEqual(hexToRgb(hex), picker(hex));
    assert.deepEqual(hexToRgb(hex.toUpperCase()), picker(hex.toUpperCase()));
  }
});
