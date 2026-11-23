// Event handler functions for Yeelight Cube Draw Card
// Each function should be exported and receive the card instance as first argument if needed

// A stroke (pencil or eraser) saves one Undo step when it starts, wherever
// the press lands (a pixel, then the grid it bubbles to), and ends when the
// press is released anywhere: outside the grid too, so moving back over it
// with no button held paints nothing.
const STROKE_ENDS = ["mouseup", "touchend", "touchcancel", "pointercancel"];

function beginStroke(card, e) {
  // A right press is the eraser's context menu (erasePixel), not a stroke.
  if (e && typeof e.button === "number" && e.button !== 0) return false;
  if (!card.pencilMode && !card.eraserMode) return false;
  if (card._drawingActive) return true;
  card._pushMatrixHistory();
  card._drawingActive = true;
  card.isDrawing = true;
  const end = () => endDraw(card);
  card._strokeEnd = end;
  for (const type of STROKE_ENDS) window.addEventListener(type, end);
  return true;
}

export function drawPixel(card, e, idx) {
  e.preventDefault();
  if (!beginStroke(card, e)) return;
  if (card.pencilMode) {
    card._setPixel(idx);
  } else {
    card.matrixOperations.erasePixel(null, idx);
  }
}

export function startDraw(card, e) {
  beginStroke(card, e);
}

export function endDraw(card, e) {
  card.isDrawing = false;
  card._drawingActive = false;
  const end = card._strokeEnd;
  card._strokeEnd = null;
  if (end) for (const type of STROKE_ENDS) window.removeEventListener(type, end);
}

export function drawMove(card, e) {
  if (!card._drawingActive) return;
  // Released where no mouseup reached the page (another window).
  if (!e.touches && e.buttons === 0) {
    endDraw(card);
    return;
  }
  let clientX, clientY;
  if (e.touches && e.touches.length) {
    clientX = e.touches[0].clientX;
    clientY = e.touches[0].clientY;
  } else {
    clientX = e.clientX;
    clientY = e.clientY;
  }
  const container = card.shadowRoot.querySelector(".matrix");
  if (!container) return;
  const rect = container.getBoundingClientRect();
  // The cell under the pointer in the area's view, and the pixel it shows.
  const view = card._drawingView();
  const x = Math.floor((clientX - rect.left) / (rect.width / view.cols));
  const y = Math.floor((clientY - rect.top) / (rect.height / view.rows));
  if (x >= 0 && x < view.cols && y >= 0 && y < view.rows) {
    const idx = view.source[y * view.cols + x];
    if (card.pencilMode) {
      card._setPixel(idx);
    } else if (card.eraserMode) {
      card.matrixOperations.erasePixel(null, idx);
    }
  }
}

export function onMatrixClick(card, idx) {
  // ...existing logic, call card._onMatrixClick(idx) or refactor logic here...
  card._onMatrixClick(idx);
}

export function erasePixel(card, e, idx) {
  e.preventDefault();
  // For single pixel erase (not drag), push history here
  if (!card._drawingActive) card._pushMatrixHistory();
  card.matrixOperations.erasePixel(null, idx);
}

export function onMatrixMouseOver(card, idx) {
  card._onMatrixMouseOver(idx);
}

export function onMatrixMouseLeave(card) {
  card._onMatrixMouseLeave();
}
