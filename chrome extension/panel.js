// The side panel: Sherpa (the live site, so every feature is here) plus the repository on your screen.
const SITE = "https://sherpa-ai.tech";

const $ = (id) => document.getElementById(id);
const app = $("app");
let loaded = null; // the repo URL the panel last opened
let onScreen = null; // the repo in the active tab

const ICONS = {
  github:
    '<svg viewBox="0 0 24 24"><path d="M12 .5a11.5 11.5 0 0 0-3.6 22.4c.6.1.8-.3.8-.6v-2c-3.2.7-3.9-1.5-3.9-1.5-.5-1.3-1.3-1.7-1.3-1.7-1-.7.1-.7.1-.7 1.2.1 1.8 1.2 1.8 1.2 1 1.8 2.8 1.3 3.5 1 .1-.8.4-1.3.8-1.6-2.6-.3-5.3-1.3-5.3-5.7 0-1.3.4-2.3 1.2-3.1-.1-.3-.5-1.5.1-3.1 0 0 1-.3 3.2 1.2a11 11 0 0 1 5.8 0C17.3 4.6 18.3 5 18.3 5c.6 1.6.2 2.8.1 3.1.8.8 1.2 1.8 1.2 3.1 0 4.4-2.7 5.4-5.3 5.7.4.4.8 1.1.8 2.2v3.2c0 .3.2.7.8.6A11.5 11.5 0 0 0 12 .5z"/></svg>',
  gitlab:
    '<svg viewBox="0 0 24 24"><path d="m23.6 9.6-.03-.09-3.2-8.4a.84.84 0 0 0-1.6.06l-2.2 6.6H7.4L5.2 1.2a.84.84 0 0 0-1.6-.06L.4 9.5l-.03.09a5.9 5.9 0 0 0 2 6.8l.01.01 4.9 3.6 2.4 1.8 1.5 1.1a1 1 0 0 0 1.2 0l1.5-1.1 2.4-1.8 4.9-3.7a5.9 5.9 0 0 0 2-6.8z"/></svg>',
  bitbucket:
    '<svg viewBox="0 0 24 24"><path d="M.8 1.2a.77.77 0 0 0-.77.9l3.26 19.8c.08.5.51.87 1.02.88h15.6a.77.77 0 0 0 .77-.65L23.97 2.1a.77.77 0 0 0-.77-.9zM14.5 15.5H9.5l-1.35-7.07h7.56z"/></svg>',
};

// first path segments that are GitHub/GitLab pages, not owners
const NOT_OWNERS = new Set([
  "settings", "orgs", "organizations", "marketplace", "explore", "notifications", "topics", "features", "pulls",
  "issues", "login", "logout", "signup", "join", "sponsors", "about", "enterprise", "pricing", "collections",
  "trending", "new", "codespaces", "search", "apps", "account", "dashboard", "users", "help", "admin", "-",
  "groups", "projects", "snippets", "site", "security", "customer-stories", "readme", "events", "watching", "stars",
]);

/** "https://github.com/o/r/tree/main/src" → {host: "github", url: "https://github.com/o/r", slug: "o/r"} */
function repoOf(href) {
  let u;
  try {
    u = new URL(href);
  } catch {
    return null;
  }
  const host = { "github.com": "github", "gitlab.com": "gitlab", "bitbucket.org": "bitbucket" }[u.hostname];
  if (!host) return null;
  let parts = u.pathname.split("/").filter(Boolean);
  if (host === "gitlab") {
    const dash = parts.indexOf("-"); // gitlab.com/group/sub/project/-/tree/main
    if (dash > 0) parts = parts.slice(0, dash);
  } else {
    parts = parts.slice(0, 2);
  }
  if (parts.length < 2 || NOT_OWNERS.has(parts[0].toLowerCase())) return null;
  const path = parts.map((p) => p.replace(/\.git$/, "")).join("/");
  return { host, url: `https://${u.hostname}/${path}`, slug: path };
}

function same(a, b) {
  return !!a && !!b && a.toLowerCase() === b.toLowerCase();
}

function load(url) {
  $("loading").hidden = false;
  loaded = url;
  app.src = url ? `${SITE}/dashboard?repo=${encodeURIComponent(url)}` : `${SITE}/dashboard`;
  render();
}

function render() {
  const repo = onScreen;
  $("repo").hidden = !repo;
  $("hint").hidden = !!repo || !!loaded;
  if (!repo) return;
  $("host").innerHTML = ICONS[repo.host];
  $("slug").textContent = repo.slug;
  $("slug").title = repo.url;
  const open = $("open");
  open.disabled = same(loaded, repo.url);
  open.textContent = open.disabled ? "Opened" : "Open in Sherpa";
}

async function lookAtTab() {
  const [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true }).catch(() => []);
  onScreen = tab?.url ? repoOf(tab.url) : null;
  render();
}

// ---- the session: shared between the panel's frame and sherpa-ai.tech tabs ----
async function storedToken() {
  const { token } = await chrome.storage.local.get("token");
  return token || null;
}

function send(token) {
  app.contentWindow?.postMessage({ type: "sherpa:token", token }, SITE);
}

window.addEventListener("message", async (e) => {
  if (e.origin !== SITE || e.source !== app.contentWindow) return;
  const { type, token } = e.data || {};
  if (type === "sherpa:ready") {
    // the page loaded: hand it the latest session, or keep the one it has
    $("loading").hidden = true;
    const stored = await storedToken();
    if (stored && stored !== token) send(stored);
    else if (!stored && token) chrome.storage.local.set({ token });
  } else if (type === "sherpa:token") {
    chrome.storage.local.set({ token: token || null }); // signed in or out inside the panel
  }
});

chrome.storage.onChanged.addListener((changes, area) => {
  // signed in or out on a sherpa-ai.tech tab
  if (area === "local" && "token" in changes) send(changes.token.newValue || null);
});

app.addEventListener("load", () => setTimeout(() => ($("loading").hidden = true), 1500));

$("open").addEventListener("click", () => onScreen && load(onScreen.url));
$("reload").addEventListener("click", () => load(loaded));
$("tab").addEventListener("click", () => {
  chrome.tabs.create({ url: loaded ? `${SITE}/dashboard?repo=${encodeURIComponent(loaded)}` : `${SITE}/dashboard` });
});

chrome.tabs.onActivated.addListener(lookAtTab);
chrome.tabs.onUpdated.addListener((_id, info, tab) => {
  if (tab.active && info.url) lookAtTab();
});
chrome.windows.onFocusChanged.addListener(lookAtTab);

// opening the panel opens the repo on screen straight away
lookAtTab().then(() => load(onScreen ? onScreen.url : null));
