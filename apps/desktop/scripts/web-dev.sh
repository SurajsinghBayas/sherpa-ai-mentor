#!/bin/sh
# `tauri dev` points the window at the web app's dev server. Reuse one that's already running
# (e.g. `make web`); otherwise start it.
if curl -fsS -o /dev/null http://localhost:3000; then
  echo "Using the web dev server already running on http://localhost:3000"
  exit 0
fi
exec npm --prefix ../web run dev -- -p 3000
