# Sherpa AI for desktop

A native macOS and Windows app for Sherpa AI, built with [Tauri 2](https://tauri.app). It is the same React + TypeScript + Tailwind app as `apps/web`, not a copy:

```
            apps/web (React + TypeScript + Tailwind, Next.js)
                 │  static export (npm run build:desktop)
                 ▼
            apps/desktop (Tauri 2: native window + bundler)
                 │
        ┌────────┴─────────┐
   macOS build        Windows build (CI)
 Sherpa AI.app/.dmg    Sherpa AI.exe/.msi
        └────────┬─────────┘
                 ▼
     Sherpa API (services/api) → Postgres + Bedrock
```

The window shows the bundled web app, which calls the API over HTTP exactly as the browser does. The Rust side only hosts the window and opens external links in your browser; all product logic stays in `apps/web` and the API. A change to the web app ships to both after a rebuild.

## Requirements

- macOS 11 or later, Apple silicon or Intel
- Xcode command-line tools: `xcode-select --install`
- Rust: `curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh` (the Makefile targets look in `~/.cargo/bin`)
- Node 18+ and `npm install` in both `apps/web` and `apps/desktop`

## Run it

Start the API first (`make api`); the app talks to `http://localhost:8000` for now.

```bash
make desktop          # dev: a native window on the web dev server, with hot reload
make desktop-build    # release: the .app and a .dmg installer
```

`make desktop` reuses a web dev server already running on port 3000 (`make web`), or starts one.

The release build ends up in `apps/desktop/src-tauri/target/release/bundle/`:

| File | Use |
|---|---|
| `macos/Sherpa AI.app` | Drag to Applications, or run it in place |
| `dmg/Sherpa AI_0.1.0_aarch64.dmg` | Installer to share |

The build is not signed yet, so the first time you open it macOS says it can't verify the developer. Right-click the app → **Open** → **Open**. For builds you share, see the production checklist below.

To build for Intel Macs as well: `rustup target add x86_64-apple-darwin`, then `npx tauri build --target universal-apple-darwin`.

## How it differs from the website

| | Website | Desktop app |
|---|---|---|
| Start page | Landing page | Goes straight to the workspace |
| Sign in | Email code, password, Google | Email code and password. Google sign-in only accepts web origins, so it is hidden |
| Links to other sites | Same tab | Open in your default browser |
| Drag and drop | Browser | Same: files dropped on the ZIP area upload as in the browser |

The app knows it is the desktop app at runtime (`lib/desktop.ts` checks for Tauri), so the web build is unchanged.

## Pointing it at a different API

The API address is baked in when the web app is exported:

```bash
SHERPA_API_URL=https://api.your-sherpa.app make desktop-build
```

The API must allow the app's origin. It does by default through `DESKTOP_ORIGINS` (`tauri://localhost` on macOS, `http(s)://tauri.localhost` on Windows), separate from the web's `ALLOWED_ORIGINS`.

## Production checklist (when you switch)

1. Build with `SHERPA_API_URL` set to the deployed API (https).
2. Sign and notarize: join the Apple Developer Program, then set `APPLE_SIGNING_IDENTITY`, `APPLE_ID`, `APPLE_PASSWORD` (app-specific) and `APPLE_TEAM_ID` before `tauri build`. Tauri signs and notarizes automatically; see the [Tauri macOS signing guide](https://tauri.app/distribute/sign/macos/).
3. Turn on a Content Security Policy: `app.security.csp` in `src-tauri/tauri.conf.json` is `null` while the API is local. Set it to allow `connect-src` only for the API.
4. Bump `version` in `src-tauri/tauri.conf.json` and `package.json` for each release. Add the updater plugin if you want in-app updates.

## Windows

Windows installers are built on GitHub Actions (`.github/workflows/desktop.yml`), on a real Windows runner, so no Windows machine is needed. It runs on every push to `main` that touches `apps/web` or `apps/desktop`, on `v*` tags, and on demand (Actions → desktop → Run workflow). Each run uploads:

| Artifact | Contents |
|---|---|
| `sherpa-ai-windows` | `Sherpa AI_0.1.0_x64_en-US.msi` and `Sherpa AI_0.1.0_x64-setup.exe` |
| `sherpa-ai-macos-arm64` | `Sherpa AI_0.1.0_aarch64.dmg` |

Set the repository variable `SHERPA_API_URL` to the deployed API; without it the apps call `http://localhost:8000`. The Windows installer is unsigned, so SmartScreen warns on first run (**More info → Run anyway**) until a code-signing certificate is added. The installer fetches the WebView2 runtime if Windows doesn't already have it.

To build on a Windows machine instead: install Rust and Node, run `npm install` in `apps/web` and `apps/desktop`, then `npx tauri build --bundles msi,nsis` in `apps/desktop`.

## Files

```
apps/desktop/
  package.json               Tauri CLI and scripts (dev, build, icons)
  scripts/web-dev.sh         starts or reuses the web dev server for `tauri dev`
  icons/app-icon.svg|png     source for the app icon (Sherpa's head on Sherpa blue)
  src-tauri/
    tauri.conf.json          window, bundle and build settings
    capabilities/default.json what the web app may ask the native side for (open links only)
    src/lib.rs               the app: one window + the opener plugin
    icons/                   generated by `npm run icons`
```
