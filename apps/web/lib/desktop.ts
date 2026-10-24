/* Which shell the web app runs in. Only call these in effects or event handlers: they read `window`. */

/** True inside the Sherpa desktop app (Tauri). */
export function isDesktop(): boolean {
  return typeof window !== "undefined" && "__TAURI_INTERNALS__" in window;
}

/** True inside the Sherpa Android or iOS app (Capacitor). */
export function isMobileApp(): boolean {
  if (typeof window === "undefined") return false;
  const cap = (window as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor;
  return !!cap?.isNativePlatform?.();
}

/** True in either app. Google and GitHub sign-in only return to web origins, so the apps sign in by email. */
export function isNativeApp(): boolean {
  return isDesktop() || isMobileApp();
}
