const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const catalogue = require("./card-docs-catalogue.json");

const root = path.resolve(__dirname, "..");
const escape = (text) =>
  String(text).replace(
    /[&<>"']/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[
        character
      ],
  );

// The files whose galleries are generated, from the repository root: the
// README holds each card's galleries; the others hold named galleries only.
const DOCUMENTS = ["README.md", "docs/DISPLAY_MODES.md"];

// One gallery block: its markers must be there once each, in order.
function replaceBlock(source, name, content) {
  const start = `<!-- card-docs:${name}:start -->`;
  const end = `<!-- card-docs:${name}:end -->`;
  assert.equal(
    source.split(start).length,
    2,
    `Missing or duplicate gallery start: ${name}`,
  );
  assert.equal(
    source.split(end).length,
    2,
    `Missing or duplicate gallery end: ${name}`,
  );
  const begin = source.indexOf(start) + start.length;
  const finish = source.indexOf(end);
  assert.ok(finish > begin, `Reversed gallery markers: ${name}`);
  return source.slice(0, begin) + content + source.slice(finish);
}

// A catalogue entry with `gallery` goes to that named gallery
// (<!-- card-docs:gallery:NAME:start -->, in any of DOCUMENTS) instead of
// its card's.
function galleryCells(definitions, exists, pending, base) {
  const galleries = new Map();
  for (const [kind, definition] of Object.entries(definitions)) {
    for (const group of ["variations", "editors"]) {
      for (const [name, options] of Object.entries(definition[group])) {
        const target =
          (typeof options === "object" && options.gallery) ||
          `${kind}:${group}`;
        const file = `images/Cards/generated/${kind}-${group === "editors" ? "editor-" : ""}${name}.png`;
        if (!galleries.has(target)) galleries.set(target, []);
        const cells = galleries.get(target);
        if (pending && !exists(file)) {
          pending.push(file);
          continue;
        }
        assert.ok(exists(file), `Missing screenshot: ${file}`);
        const title = typeof options === "string" ? options : options.title;
        const width =
          (typeof options === "object" && options.galleryWidth) ||
          (group === "editors" ? 220 : 280);
        cells.push(
          `    <td valign="top"><img src="${base}${file}" alt="${escape(definition.title)} - ${escape(title)}" width="${width}"><br>${escape(title)}</td>`,
        );
      }
    }
  }
  return galleries;
}

function table(cells, newline) {
  const rows = [];
  for (let index = 0; index < cells.length; index += 3)
    rows.push("  <tr>", ...cells.slice(index, index + 3), "  </tr>");
  return ["", "<table>", ...rows, "</table>", ""].join(newline);
}

// `pending` (an array) accepts catalogue entries whose screenshot does not
// exist yet: they are left out of the gallery and listed there instead of
// failing. The Documentation Screenshots workflow captures them and then
// refreshes the galleries strictly.
// `cards` (the README): every card's own galleries must be in `source`;
// named galleries are filled wherever their markers are. `base`: the path
// from `source`'s folder to the repository root.
function updateGalleries(
  source,
  definitions = catalogue,
  exists = (file) => fs.existsSync(path.join(root, file)),
  { pending, cards = true, base = "" } = {},
) {
  const newline = source.includes("\r\n") ? "\r\n" : "\n";
  const galleries = galleryCells(definitions, exists, pending, base);
  for (const [target, cells] of galleries) {
    const named = target.startsWith("gallery:");
    if (named ? !source.includes(`<!-- card-docs:${target}:start -->`) : !cards)
      continue;
    source = replaceBlock(source, target, table(cells, newline));
  }
  return source;
}

// The named galleries each document holds (each must be in exactly one).
function namedGalleries(source) {
  return [...source.matchAll(/<!-- card-docs:(gallery:[\w-]+):start -->/g)].map(
    (match) => match[1],
  );
}

if (require.main === module) {
  const check = process.argv.includes("--check");
  // A check accepts new scenarios not captured yet (see updateGalleries).
  const pending = check ? [] : undefined;
  const placed = new Map();
  for (const document of DOCUMENTS) {
    const file = path.join(root, document);
    const before = fs.readFileSync(file, "utf8");
    for (const name of namedGalleries(before)) {
      assert.ok(!placed.has(name), `Gallery ${name} is in ${placed.get(name)} and ${document}`);
      placed.set(name, document);
    }
    const depth = document.split("/").length - 1;
    const after = updateGalleries(before, catalogue, undefined, {
      pending,
      cards: document === "README.md",
      base: "../".repeat(depth),
    });
    if (check)
      assert.equal(after, before, `${document} galleries are stale; run npm run docs:readme`);
    else if (after !== before) fs.writeFileSync(file, after);
  }
  // Every named gallery of the catalogue has its place.
  for (const definition of Object.values(catalogue))
    for (const group of ["variations", "editors"])
      for (const options of Object.values(definition[group]))
        if (typeof options === "object" && options.gallery)
          assert.ok(placed.has(options.gallery), `No document holds ${options.gallery}`);
  if (check)
    for (const file of new Set(pending))
      console.log(`pending capture (Documentation Screenshots workflow): ${file}`);
}

module.exports = { updateGalleries, DOCUMENTS };
