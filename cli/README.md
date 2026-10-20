# Sherpa CLI

Upload a codebase from your machine to Sherpa AI and ask about it, from the terminal.

```bash
sherpa login
sherpa upload ./my-project
sherpa ask 90eb01fd184c "How does signup work?"
```

It is one Python file with no dependencies (Python 3.9+). It talks to the same API as the web app, so anything you upload appears in your Sherpa dashboard too.

---

## Install

**From your Sherpa server** (no repository access needed; the downloaded CLI is preset to that server, so `sherpa login` needs no `--api`). The web app shows these commands, filled in, under **Add repo → CLI** and on the **CLI** page:

```bash
# macOS / Linux
mkdir -p ~/.local/bin && curl -fsSL https://api.your-sherpa.app/cli/sherpa.py -o ~/.local/bin/sherpa && chmod +x ~/.local/bin/sherpa

# Windows (PowerShell): then run it as `python sherpa.py …`
curl.exe -fsSL https://api.your-sherpa.app/cli/sherpa.py -o sherpa.py
```

If `sherpa` isn't found afterwards, add `~/.local/bin` to your PATH (`export PATH="$HOME/.local/bin:$PATH"` in `~/.zshrc` or `~/.bashrc`).

**From a checkout of this repository**, pick one:

```bash
# isolated install, puts `sherpa` on your PATH
pipx install ./cli

# or into the current Python environment
pip install ./cli

# or run it without installing
python3 cli/sherpa_cli.py --help
```

Run these from the repository root. Check it worked:

```bash
sherpa --version        # sherpa 0.1.0
```

To remove it: `pipx uninstall sherpa-cli` or `pip uninstall sherpa-cli`.

---

## 1. Sign in

```bash
sherpa login --api https://api.your-sherpa.app
```

- `--api` is the Sherpa **API** address (not the web app). For local development it is `http://localhost:8000`, the default, so you can leave it out.
- You are asked for your email, and Sherpa emails you a 6-digit code. Type it in:

```
Email: you@example.com
We emailed a 6-digit code to you@example.com.
Code: 482913
Signed in as you@example.com on https://api.your-sherpa.app
```

- This works for every account, including ones created with Google sign-in (the code goes to the same email address).
- Have a password account? `sherpa login --password` asks for it instead of sending a code.
- Your account must exist first: sign up once in the web app.

The session is saved to `~/.config/sherpa/config.json` (readable only by you) and lasts as long as a web session (one day by default). When it expires, commands tell you to run `sherpa login` again.

```bash
sherpa whoami           # you@example.com on https://api.your-sherpa.app
sherpa logout           # forget the saved session on this machine
```

---

## 2. Upload a project

```bash
cd my-project
sherpa upload
```

or point it at a folder:

```bash
sherpa upload ~/code/my-project --name my-project
```

What happens:

1. **Packing.** The CLI collects the files to send.
   - Inside a git checkout it uses only files git tracks or would track, so your `.gitignore` is respected.
   - Otherwise it walks the folder.
   - Either way it leaves out dependencies and build output (`node_modules/`, `.git/`, `dist/`, `build/`, `.next/`, `vendor/`, `target/`, `coverage/` …), lockfiles, minified bundles, binaries and media, files over 400 KB, `.env` files and private keys. Symlinks are never followed.
2. **Uploading.** The files are zipped in memory and sent (100 MB limit).
3. **Review.** Sherpa shows what it will index, before doing any work:

   ```
     Project      my-project
     Files        214  ·  1.8 MB
     Type         Python, Docker
     Languages    Python (180), Markdown (12), YAML (9), Other (13)
     Entry points app/main.py

   Index it now? [Y/n]
   ```

   Answer `n` to discard the upload; nothing is stored.
4. **Indexing.** Runs on the server with a progress bar, then prints the repo id:

   ```
   ✓ my-project: 214 files indexed
     repo id 90eb01fd184c  ·  try: sherpa ask 90eb01fd184c "how does it start?"
   ```

### Options

| Option | What it does |
|---|---|
| `PATH` | Folder to upload. Default: the current folder. |
| `--name NAME` | Project name. Default: the folder's name. |
| `-y`, `--yes` | Skip the "Index it now?" question (for scripts and CI). |
| `--no-wait` | Return as soon as indexing starts; check later with `sherpa status`. |

### Updating a project

Upload again with the **same name**. Sherpa compares the files and re-indexes only what changed, which is much faster than the first upload:

```bash
sherpa upload --name my-project -y
# ✓ my-project: 214 files indexed · 3 changed
```

A different `--name` creates a separate project.

---

## 3. Ask questions

```bash
sherpa repos                                   # find the repo id
sherpa ask 90eb01fd184c "Where are passwords hashed?"
```

The answer is printed as Markdown, followed by the exact file and line ranges it is based on:

```
Passwords are hashed with bcrypt in `hash_password` … [app/security.py:24-26]

Sources:
  app/security.py:24-26
```

Each question counts toward your daily AI quota, the same as in the web app.

---

## 4. Check on uploads

```bash
sherpa status
```

```
62a12e785ee042d0  2026-10-21 01:20  ready      100%  my-project  214 files indexed
1f0c9a2b7d3e4c55  2026-10-21 00:58  failed       0%  big-repo    indexing failed unexpectedly; retry it
```

If an upload failed, retry it. The files are kept on the server for 24 hours, so nothing is uploaded again:

```bash
sherpa retry 1f0c9a2b7d3e4c55
```

---

## Command reference

| Command | Purpose |
|---|---|
| `sherpa login [--api URL] [--email E] [--password]` | Sign in and save the session |
| `sherpa logout` | Forget the saved session |
| `sherpa whoami` | Show the signed-in account and API |
| `sherpa upload [PATH] [--name N] [-y] [--no-wait]` | Upload, review and index a folder |
| `sherpa status` | Your 20 most recent uploads |
| `sherpa retry JOB_ID` | Retry a failed upload without re-uploading |
| `sherpa repos` | Your indexed repositories and their ids |
| `sherpa ask REPO_ID "QUESTION"` | Ask a question and get a cited answer |
| `sherpa --version` · `sherpa COMMAND --help` | Version · help for a command |

Exit codes: `0` success, `1` an error (printed as `sherpa: …`), `130` interrupted with Ctrl-C.

---

## Configuration

| Setting | Where | Notes |
|---|---|---|
| API address | `sherpa login --api URL`, or `SHERPA_API_URL` | The environment variable wins over the saved value |
| Session token | saved by `sherpa login`, or `SHERPA_TOKEN` | Use the variable in CI instead of logging in |
| Config folder | `$XDG_CONFIG_HOME/sherpa/` or `~/.config/sherpa/` | Holds `config.json` (mode 600) |

### In CI

Upload on every push to `main` so the Sherpa index follows your code:

```bash
export SHERPA_API_URL=https://api.your-sherpa.app
export SHERPA_TOKEN=${{ secrets.SHERPA_TOKEN }}   # a token from `sherpa login`, stored as a CI secret
python3 cli/sherpa_cli.py upload . --name my-project --yes
```

Tokens expire after a day by default (`ACCESS_TOKEN_EXPIRE_MINUTES` on the server), so a long-lived CI setup needs that raised or a fresh token each run.

---

## Limits

| Limit | Value |
|---|---|
| Packed upload size | 100 MB |
| Text indexed per project | 50 MB, up to 1,500 files |
| Single file | 400 KB (larger files are skipped) |
| Uploads indexing at once | 1 per account |
| Projects per account | 15 (delete one in the web app to add more) |
| Imports per day | 30 (uploads, re-uploads and retries each count) |

Server operators can change these; see `MAX_UPLOAD_MB`, `MAX_UPLOAD_SOURCE_MB`, `MAX_REPOS_PER_USER` and `DAILY_INGESTS` in `.env.example`.

---

## Troubleshooting

| Message | What to do |
|---|---|
| `can't reach the Sherpa API at …` | Check the address with `sherpa whoami`; it must be the API, not the web app. Locally, start it with `make api`. |
| `not signed in` / `your session expired` | Run `sherpa login`. |
| `no account with this email — sign up first` | Create the account in the web app, then log in. |
| `the packed project is … MB; the limit is 100 MB` | Upload a subfolder, or make sure generated files are in `.gitignore`. |
| `no source files to upload` | Everything was filtered out (dependencies, binaries, build output). Check you're in the right folder. |
| `another upload is still indexing` | Wait for it (`sherpa status`), then try again. |
| `daily ingest limit reached` | Try again tomorrow (UTC). |
| `repo limit reached` | Delete a project in the web app. |
| `indexing failed … Run sherpa retry …` | Run the printed `sherpa retry` command. |
| `too many requests; try again in Ns` | Wait that long; uploads are limited to 10 a minute. |
