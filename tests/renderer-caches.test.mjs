// The renderers' caches: a palette music mode's run follows its whole
// palette (timelineFor), as in Python (test_palette_timeline.py).
import assert from "node:assert/strict";
import test from "node:test";
import { lampSettings, timelineFor } from "../custom_components/yeelight_cube/www/lamp-renderers.js";

const RED = [255, 0, 0], GREEN = [0, 255, 0], BLUE = [0, 0, 255], WHITE = [255, 255, 255];
const gather = (palette) => lampSettings("Music Gather", "Right", 128, null, "palette", null, 128, palette);

test("a later palette colour starts its own run", () => {
  const first = gather([RED, GREEN, BLUE, BLUE, BLUE]);
  const second = gather([RED, GREEN, BLUE, BLUE, WHITE]);
  assert.notDeepEqual(first.palette, second.palette);
  assert.notEqual(timelineFor(first), timelineFor(second));
  assert.equal(timelineFor(first), timelineFor({ ...first }));
});

// lamp-core.js keeps its maps and tables within a limit (lamp_core.py's
// _MAPS_LIMIT, _TABLES_LIMIT): what they give reads the same past it.
import { blendGrid, fadeTowards, pixelMap } from "../custom_components/yeelight_cube/www/lamp-core.js";

test("lamp-core's tables read the same once started again", () => {
  const blend = () => blendGrid(Uint8Array.from([10, 120, 250]), 7, 1, 1, [200, 30, 90]);
  const towardsOf = () => fadeTowards(Uint8Array.from({ length: 300 }, (_, i) => i & 255), 40, 180, 100);
  const map = () => Array.from(pixelMap(1));
  const before = [blend(), towardsOf(), map()].map((value) => Array.from(value));
  for (let amount = 0; amount < 256; amount += 1) {
    blendGrid(new Uint8Array(3), amount, 1, 1, [amount, 255 - amount, amount >> 1]);
    for (let target = 0; target < 256; target += 8) fadeTowards(new Uint8Array(300), amount, target, 100);
  }
  for (let length = 1; length < 300; length += 1) pixelMap(0, undefined, length);
  assert.deepEqual([blend(), towardsOf(), map()].map((value) => Array.from(value)), before);
});
