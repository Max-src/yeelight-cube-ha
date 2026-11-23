import assert from "node:assert/strict";
import test from "node:test";

// The draw card's strokes (draw_card_events.js): one Undo step per stroke,
// and a stroke ends when the press is released anywhere on the page.
globalThis.window = new EventTarget();

const { drawPixel, startDraw, drawMove, erasePixel, endDraw } = await import(
  "../custom_components/yeelight_cube/www/draw_card_events.js"
);

function card(mode = "pencil") {
  const painted = [];
  const c = {
    pencilMode: mode === "pencil",
    eraserMode: mode === "eraser",
    areaFillMode: mode === "fill",
    _drawingActive: false,
    isDrawing: false,
    history: 0,
    painted,
    _pushMatrixHistory() {
      c.history += 1;
    },
    _setPixel(idx) {
      painted.push(idx);
    },
    matrixOperations: { erasePixel: (_e, idx) => painted.push(-idx) },
    _drawingView: () => ({ cols: 2, rows: 1, source: [0, 1] }),
    shadowRoot: {
      querySelector: () => ({
        getBoundingClientRect: () => ({ left: 0, top: 0, width: 20, height: 10 }),
      }),
    },
  };
  return c;
}

const press = (button = 0) => ({ button, preventDefault() {} });

// A press on a pixel reaches the pixel, then the grid it bubbles to.
function pressPixel(c, idx, button = 0) {
  drawPixel(c, press(button), idx);
  startDraw(c, press(button));
}

test("a stroke saves one Undo step", () => {
  const c = card();
  pressPixel(c, 0);
  drawMove(c, { clientX: 15, clientY: 5, buttons: 1 });
  globalThis.window.dispatchEvent(new Event("mouseup"));
  assert.equal(c.history, 1);
  assert.deepEqual(c.painted, [0, 1]);
  assert.equal(c._drawingActive, false);
});

test("a release outside the grid ends the stroke", () => {
  const c = card("eraser");
  pressPixel(c, 1);
  globalThis.window.dispatchEvent(new Event("mouseup")); // released outside the grid
  drawMove(c, { clientX: 5, clientY: 5, buttons: 0 });
  assert.deepEqual(c.painted, [-1]);
  assert.equal(c.isDrawing, false);
});

test("moving with no button held ends a stroke the page missed the end of", () => {
  const c = card();
  pressPixel(c, 0);
  drawMove(c, { clientX: 15, clientY: 5, buttons: 0 });
  assert.deepEqual(c.painted, [0]);
  assert.equal(c._drawingActive, false);
  endDraw(c); // no listener left behind
});

test("a right press is the eraser's menu: one step, no stroke", () => {
  const c = card();
  pressPixel(c, 0, 2);
  erasePixel(c, press(2), 0);
  assert.equal(c.history, 1);
  assert.deepEqual(c.painted, [-0]);
  assert.equal(c._drawingActive, false);
});

test("a press in fill mode saves no step of its own (the fill does)", () => {
  const c = card("fill");
  pressPixel(c, 0);
  assert.equal(c.history, 0);
  assert.equal(c._drawingActive, false);
});

test("a touch starts a stroke on the grid", () => {
  const c = card();
  startDraw(c, { touches: [{}] });
  drawMove(c, { touches: [{ clientX: 5, clientY: 5 }] });
  globalThis.window.dispatchEvent(new Event("touchend"));
  assert.equal(c.history, 1);
  assert.deepEqual(c.painted, [0]);
  assert.equal(c._drawingActive, false);
});
