// Export / import of a card's collection as a JSON file, shared by the
// palette card and the draw card (pixel arts): the download, picking and
// reading a file (with a size limit), and the import button's status shown
// for a moment. Each card checks and normalises its own data.

/** Raised by readJsonFile for a file over its size limit. */
export class JsonFileTooLargeError extends Error {
  constructor(size, maxBytes) {
    super(`File too large to import (${size} bytes, at most ${maxBytes})`);
    this.name = "JsonFileTooLargeError";
  }
}

/** Download `data` as the JSON file `fileName` (indented, like the stored
 * collections). */
export function downloadJson(data, fileName) {
  const json = JSON.stringify(data, null, 2);
  const blob = new Blob([json], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = fileName;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => {
    a.remove();
    URL.revokeObjectURL(url);
  }, 100);
}

/** Open the browser's file picker for a JSON file; `onFile(file)` is called
 * with the file chosen (not at all when the picker is cancelled). */
export function pickJsonFile(onFile) {
  const input = document.createElement("input");
  input.type = "file";
  input.accept = ".json,application/json";
  input.addEventListener("change", () => {
    const file = input.files && input.files[0];
    if (file) onFile(file);
  });
  input.click();
}

/** The parsed content of the JSON file `file`. Rejects with a
 * JsonFileTooLargeError when it is over `maxBytes` (it is not read), or a
 * SyntaxError when it is not JSON. */
export async function readJsonFile(file, maxBytes) {
  if (file.size > maxBytes) throw new JsonFileTooLargeError(file.size, maxBytes);
  return JSON.parse(await file.text());
}

/**
 * The import button's status ("success", "error" or null: what
 * renderExportImportRow shows), set for a moment then back to null. A newer
 * status replaces the older one and its delay; the card leaving the page
 * clears it (a Lit reactive controller of `host`).
 */
export class ImportStatus {
  constructor(host) {
    this._host = host;
    this.value = null;
    this._timer = null;
    host.addController(this);
  }

  /** Show `value`; back to null after `resetAfter` ms (when given). */
  set(value, resetAfter) {
    clearTimeout(this._timer);
    this._timer = null;
    this.value = value;
    this._host.requestUpdate();
    if (resetAfter) this._timer = setTimeout(() => this.set(null), resetAfter);
  }

  hostDisconnected() {
    clearTimeout(this._timer);
    this._timer = null;
    this.value = null;
  }
}
