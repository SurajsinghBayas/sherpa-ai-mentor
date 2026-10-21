# Deploying Sherpa AI on an Ubuntu server

For an Ubuntu server you already have, such as AWS EC2: install, clone, add `.env`, run. Run these in the server's terminal.

## 1. Install

```bash
sudo apt update && sudo apt install -y git python3-venv python3-pip
```

## 2. Clone

The repository is private, so put your GitHub username and a token in the URL. Use a fine-grained token with read-only **Contents** access to this repository.

```bash
git clone https://YOUR_GITHUB_USERNAME:YOUR_TOKEN@github.com/SurajsinghBayas/sherpa-ai-mentor.git
cd sherpa-ai-mentor
```

## 3. Settings

```bash
nano .env
```

Paste your settings (the same as your local `.env`), then save with `Ctrl+O`, `Enter`, `Ctrl+X`. Add the address the web app is served from, so the browser is allowed to call the API:

```bash
ALLOWED_ORIGINS=http://YOUR_SERVER_IP:3000
```

The API reads `.env` from the repo root automatically. [`configuration.md`](configuration.md) lists every setting.

## 4. Run the backend

```bash
python3 -m venv .venv
.venv/bin/pip install -r services/api/requirements.txt
cd services/api
nohup ../../.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8000 > ~/sherpa-api.log 2>&1 &
```

It keeps running after you close the terminal. The database tables are created on first start.

Open port **8000** in the instance's security group, then check:

```bash
curl http://localhost:8000/health
```

## 5. Run the frontend (optional)

Skip this if the web app is hosted elsewhere, such as Vercel. Otherwise:

```bash
curl -fsSL https://deb.nodesource.com/setup_20.x | sudo -E bash - && sudo apt install -y nodejs
cd ~/sherpa-ai-mentor/apps/web
npm install
NEXT_PUBLIC_API_URL=http://YOUR_SERVER_IP:8000 npm run build
nohup npm start -- -H 0.0.0.0 -p 3000 > ~/sherpa-web.log 2>&1 &
```

Open port **3000** in the security group, then visit `http://YOUR_SERVER_IP:3000`.

## Everyday commands

| To | Run |
|---|---|
| See the backend log | `tail -f ~/sherpa-api.log` |
| Stop the backend | `pkill -f "uvicorn app.main"` |
| Stop the frontend | `pkill -f "next start"` |
| Update to the latest code | `cd ~/sherpa-ai-mentor && git pull`, stop, then run step 4 (and step 5 for the frontend) again |

## Good to know

- **HTTPS:** browsers only allow the microphone (voice mode) on HTTPS pages. Over plain `http://IP`, everything else works. For HTTPS, put the server behind a domain with a certificate, then set `ENVIRONMENT=production` and use `https://` addresses in `ALLOWED_ORIGINS` and `NEXT_PUBLIC_API_URL`.
- **Memory:** building the frontend needs about 2 GB of RAM, so use at least a `t3.small`, preferably a `t3.medium`.
- **Token:** the token you clone with is saved in `.git/config` on the server, which is what lets `git pull` work. Don't use it anywhere else, and never commit it.
- **Database:** to use Amazon RDS, put its `DATABASE_URL` in `.env` and allow port 5432 from this server in the RDS security group. See [`rds_setup.md`](rds_setup.md).
