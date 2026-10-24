// GitHub sign-in, browser side: send the user to GitHub, then finish on /auth/github/callback.
import { api } from "./api";

const STATE_KEY = "sherpa.github.state";
const NEXT_KEY = "sherpa.github.next";
export const callbackUrl = () => `${window.location.origin}/auth/github/callback`;

/** Go to GitHub. `link` connects GitHub to the signed-in account; `next` is where to land afterwards. */
export async function startGitHub({ link = false, next = "/dashboard" } = {}) {
  const { url, state } = await api.githubStart(callbackUrl(), link);
  // the callback only accepts a state this tab started, so a link from someone else can't sign you in
  sessionStorage.setItem(STATE_KEY, state);
  sessionStorage.setItem(NEXT_KEY, next);
  window.location.assign(url);
}

/** The state this tab started with (consumed), and where to go next. */
export function takeGitHubState() {
  const state = sessionStorage.getItem(STATE_KEY);
  const next = sessionStorage.getItem(NEXT_KEY) || "/dashboard";
  sessionStorage.removeItem(STATE_KEY);
  sessionStorage.removeItem(NEXT_KEY);
  return { state, next: next.startsWith("/") && !next.startsWith("//") ? next : "/dashboard" };
}
