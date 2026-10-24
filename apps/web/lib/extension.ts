// The Chrome extension ("chrome extension/" at the repo root) shows this site in its side panel.
// Its ID is fixed by the "key" in its manifest, so only it may frame the site (next.config.js).
export const EXTENSION_ORIGIN = "chrome-extension://fdkgmkljfocklogkbofnibealpjflcho";

/** True inside the extension's side panel. */
export function inExtension(): boolean {
  if (typeof window === "undefined" || window.parent === window) return false;
  const ancestors = window.location.ancestorOrigins;
  return !!ancestors && ancestors.length > 0 && ancestors[0] === EXTENSION_ORIGIN;
}

/** Tell the panel the session changed, so it survives the panel closing and follows sign-out. */
export function shareToken(token: string | null) {
  if (inExtension()) window.parent.postMessage({ type: "sherpa:token", token }, EXTENSION_ORIGIN);
}

/**
 * Sessions started outside the panel (Google and GitHub sign-in run in a normal tab, since they can't
 * run in a frame) arrive from the extension; take one and reload signed in.
 */
export function listenForToken(current: () => string | null, take: (token: string | null) => void) {
  if (!inExtension()) return () => {};
  const onMessage = (e: MessageEvent) => {
    if (e.origin !== EXTENSION_ORIGIN || e.data?.type !== "sherpa:token") return;
    const token = typeof e.data.token === "string" ? e.data.token : null;
    if (token === current()) return;
    take(token);
    // signed in from a sign-in page: go on to the app, as signing in there would
    if (token && /^\/(login|signup)\/?$/.test(window.location.pathname)) window.location.replace("/dashboard");
    else window.location.reload();
  };
  window.addEventListener("message", onMessage);
  window.parent.postMessage({ type: "sherpa:ready", token: current() }, EXTENSION_ORIGIN);
  return () => window.removeEventListener("message", onMessage);
}
