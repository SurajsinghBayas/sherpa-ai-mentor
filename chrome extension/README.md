# Sherpa AI for Chrome

Open the GitHub, GitLab or Bitbucket repository on your screen in Sherpa, in Chrome's side panel. The
panel runs the live app (https://sherpa-ai.tech), so every feature is there: Ask, Map, Machine, City,
Tours, Tasks, Docs, Skills, voice and the stack tree.

## Install

1. Open `chrome://extensions` and turn on **Developer mode** (top right).
2. Click **Load unpacked** and pick this `chrome extension` folder.
3. Pin Sherpa AI from the puzzle-piece menu.

## Use

- On a repository page, click the Sherpa icon (or press **Alt+Shift+S**). The panel opens that repo:
  straight into it if you've indexed it, or into the importer with its URL filled in.
- Switch tabs to another repository and press **Open in Sherpa** in the panel's bar.
- Sign in with email inside the panel. **Google or GitHub** sign-in opens sherpa-ai.tech in a tab
  (they don't run inside a frame); once you're signed in there, the panel signs in too. Signing out
  in either place signs out of both.
- ↻ reloads the panel, ↗ opens the same view in a full tab.

## How it fits together

- `panel.html/js/css`: the side panel. It reads the active tab's URL (only on github.com, gitlab.com and
  bitbucket.org, the hosts it has permission for) and frames `sherpa-ai.tech/dashboard?repo=<url>`.
- `session.js`: runs on sherpa-ai.tech tabs and hands their session to the panel.
- `manifest.json` carries a public `key`, which fixes the extension ID at
  `fdkgmkljfocklogkbofnibealpjflcho`. The site allows only that ID to frame it
  (`frame-ancestors` in `apps/web/next.config.js`, `EXTENSION_ORIGIN` in `apps/web/lib/extension.ts`);
  change all three together.
