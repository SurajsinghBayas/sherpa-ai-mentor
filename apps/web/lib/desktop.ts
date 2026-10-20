/** True inside the Sherpa desktop app (Tauri). Only call it in effects or event handlers: it reads `window`. */
export function isDesktop(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}
