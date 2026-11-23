// The effect and clock galleries' order: the same default on both cards,
// and the sort toggle beside the family filter (Default, A → Z, By family).
// tests/test_effect_names.py checks the default against the lamp's catalogue.
import assert from "node:assert/strict";
import test from "node:test";
import { sortGalleryItems } from "../custom_components/yeelight_cube/www/card-config.js";
import { GallerySort } from "../custom_components/yeelight_cube/www/effect-families.js";
import { clockStylesWithPresets } from "../custom_components/yeelight_cube/www/clock-preset-utils.js";
import { getClockStyles } from "../custom_components/yeelight_cube/www/clock-preview-utils.js";

const items = [
  { name: "Waves", family: "waves" },
  { name: "Fire", family: "glow" },
  { name: "Aurora", family: "glow" },
  { name: "Starry Sky", family: "sparkles" },
  { name: "Breathing", family: "waves" },
];
const names = (list) => list.map((item) => item.name);

test("a gallery sorts by name, by family in the card's order, or not at all", () => {
  const byName = (item) => item.name;
  assert.deepEqual(names(sortGalleryItems({}, items, byName)), names(items));
  assert.deepEqual(
    names(sortGalleryItems({}, items, byName, "name")),
    ["Aurora", "Breathing", "Fire", "Starry Sky", "Waves"],
  );
  // As the family filter lists them; within one, as the card does.
  assert.deepEqual(
    names(sortGalleryItems({}, items, byName, "family")),
    ["Waves", "Breathing", "Fire", "Aurora", "Starry Sky"],
  );
  // The card's Order, when none is picked on the card.
  assert.deepEqual(
    names(sortGalleryItems({ gallery_sort: "name" }, items, byName)),
    names(sortGalleryItems({}, items, byName, "name")),
  );
});

test("the sort toggle follows the card's Order until one is picked", () => {
  const host = { config: { gallery_sort: "name" }, requestUpdate() {} };
  const sort = new GallerySort(host, "yeelight_cube_test_sort");
  assert.equal(sort.value(), "name");
  host.config = { gallery_sort: "manual" };
  assert.equal(sort.value(), "manual");
  sort.gallery().onChange("family");
  assert.equal(sort.value(), "family");
  assert.equal(sort.gallery().value, "family");
  // Hidden: the card's Order again.
  host.config = { gallery_sort: "name", show_sort: false };
  assert.equal(sort.value(), "name");
  assert.equal(sort.gallery().hidden, true);
});

test("the clock card lists its effect styles first, then the colours and custom styles", () => {
  const styles = clockStylesWithPresets(getClockStyles(), [
    { id: "p1", name: "My orange", color: [255, 120, 0] },
  ]);
  // The clocks over an effect, as on the effect card.
  assert.deepEqual(
    styles.slice(0, 5).map((style) => style.name),
    ["Ribbon", "Starry Sky", "Spectrum", "Waves", "Rainbow"],
  );
  const solid = styles.map((style) => style.solid);
  assert.deepEqual(solid, [...solid].sort((a, b) => a - b));
  assert.equal(styles.at(-1).name, "My orange");
});

// A confirmed rename or delete acts on the item its bar showed, even when
// another device changed the list meanwhile (collection-gallery _runManage).
test("rename and delete follow the item the bar showed", async () => {
  const { manageTargetKey } = await import(
    "../custom_components/yeelight_cube/www/gallery-display-utils.js"
  );
  const item = (dataMode, name, editable = true) => ({ dataMode, name, editable });
  const list = [item("palette:0", "Sea"), item("palette:1", "Sun"), item("palette:2", "Sky")];
  assert.equal(manageTargetKey(list, "palette:1", "Sun"), "palette:1");
  // "Sea" deleted elsewhere: "Sun" is now the first.
  const after = [item("palette:0", "Sun"), item("palette:1", "Sky")];
  assert.equal(manageTargetKey(after, "palette:1", "Sun"), "palette:0");
  // Gone, or two of that name: none (the bar asks to pick it again).
  assert.equal(manageTargetKey(after, "palette:2", "Sea"), null);
  const twins = [item("palette:0", "Sky"), item("palette:1", "Sky")];
  assert.equal(manageTargetKey(twins, "palette:2", "Sky"), null);
  // Only the user's own items.
  assert.equal(manageTargetKey([item("builtin:x", "Sun", false)], "palette:1", "Sun"), null);
});
