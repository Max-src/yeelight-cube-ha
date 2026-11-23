// How long the cards wait before asking Home Assistant again for something
// it did not have (ms). Home Assistant pushes new states several times a
// second: without these waits a missing sensor or a failed request would be
// looked for again on every update.

/** A collection sensor (palettes, pixel arts) not found on a card: the next
 * scan of every entity for it (sensor-lookup.js findCollectionSensor). A
 * sensor added later is still found. */
export const COLLECTION_SENSOR_RETRY_MS = 30000;

/** A sensor looked for by its attributes (clock presets, the clock font)
 * and not found: the next scan, unless an entity is added before
 * (sensor-lookup.js missStillValid). */
export const SENSOR_RETRY_MS = 10000;

/** A lamp's native effect catalogue after a failed request
 * (native-effect-catalog.js). */
export const NATIVE_EFFECT_CATALOG_RETRY_MS = 10000;

/** The official pixel arts after a failed request (pixel-art-utils.js
 * loadBuiltinPixelArts). */
export const BUILTIN_PIXEL_ARTS_RETRY_MS = 30000;
