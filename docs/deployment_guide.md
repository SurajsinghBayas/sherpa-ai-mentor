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
npm run build
SHERPA_API_URL=http://YOUR_SERVER_IP:8000 nohup npm start -- -H 0.0.0.0 -p 3000 > ~/sherpa-web.log 2>&1 &
```

Open port **3000** in the security group, then visit `http://YOUR_SERVER_IP:3000`.

`SHERPA_API_URL` is read when the web server starts, so changing it needs a restart, not a rebuild. Without it, the page calls port 8000 on its own host. The API must also list the web app's address in `ALLOWED_ORIGINS` in `.env` (for example `ALLOWED_ORIGINS=http://YOUR_SERVER_IP:3000`), or the browser blocks every call and the sign-in page shows "Sign-in options couldn't load". The API log names any origin it refused (`CORS: refused origin …`).

## 6. Serve it on a domain with HTTPS

A page loaded over `https://` can't call an `http://` API: the browser blocks it as mixed content,
and the sign-in page shows "Can't reach the Sherpa API". So serve the API through the same
domain. nginx terminates HTTPS and passes `/api` to the API and everything else to the web app.
In the site's `server { listen 443 ssl; … }` block (certbot sets up the certificate):

```nginx
client_max_body_size 110m;              # ZIP uploads (MAX_UPLOAD_MB is 100)

location /api/ {
    proxy_pass http://127.0.0.1:8000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;   # rate limits per real client
    proxy_set_header X-Forwarded-Proto $scheme;
    proxy_set_header Upgrade $http_upgrade;                         # voice mode's WebSocket
    proxy_set_header Connection $connection_upgrade;
    proxy_read_timeout 300s;                                        # long indexing and answers
    proxy_buffering off;
}
location = /cli/sherpa.py { proxy_pass http://127.0.0.1:8000; }

location / {
    proxy_pass http://127.0.0.1:3000;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
    proxy_set_header X-Forwarded-Proto $scheme;
}
```

`$connection_upgrade` needs this once in the `http { }` block, for example in
`/etc/nginx/conf.d/upgrade.conf`:

```nginx
map $http_upgrade $connection_upgrade { default upgrade; '' close; }
```

Then:
- Set `ALLOWED_ORIGINS=https://your-domain,https://www.your-domain` in `.env`.
- Start the web server with `SHERPA_API_URL=https://your-domain`.
- Close ports 3000 and 8000 in the security group. Only 80 and 443 need to be open.

## Everyday commands

| To | Run |
|---|---|
| See the backend log | `tail -f ~/sherpa-api.log` |
| Stop the backend | `pkill -f "uvicorn app.main"` |
| Stop the frontend | `pkill -f "next start"` |
| Update to the latest code | `cd ~/sherpa-ai-mentor && git pull`, stop, then run step 4 (and step 5 for the frontend) again |

## Good to know

- **HTTPS:** browsers only allow the microphone (voice mode) on HTTPS pages. Over plain `http://IP`, everything else works. For HTTPS, put the server behind a domain with a certificate, then set `ENVIRONMENT=production` and use `https://` addresses in `ALLOWED_ORIGINS` and `SHERPA_API_URL`.
- **Memory:** building the frontend needs about 2 GB of RAM, so use at least a `t3.small`, preferably a `t3.medium`.
- **Token:** the token you clone with is saved in `.git/config` on the server, which is what lets `git pull` work. Don't use it anywhere else, and never commit it.
- **Database:** to use Amazon RDS, put its `DATABASE_URL` in `.env` and allow port 5432 from this server in the RDS security group. See [`rds_setup.md`](rds_setup.md).
