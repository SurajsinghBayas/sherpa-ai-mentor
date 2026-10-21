# Deploying Sherpa AI on AWS EC2 (Ubuntu, no SSH)

One EC2 instance runs the whole app with Docker. It sets itself up on first boot from **user data**, and every update afterwards goes through **AWS Systems Manager (SSM)**. No SSH key, no port 22, nothing to log in to.

```
  Browser / desktop app
          │ https://<domain>
          ▼
  EC2 (Ubuntu 24.04, t3.medium) ─ Docker Compose
    caddy :443  ── /api/*, /health, /ready ──▶ api :8000  (FastAPI) ──▶ Amazon RDS Postgres + pgvector
       │                                          └──────────────▶ Bedrock (LLM, embeddings), Polly
       └──── everything else ────────────────▶ web :3000  (Next.js)

  Secrets: SSM Parameter Store  /sherpa/github-token, /sherpa/env   (fetched by the instance at deploy)
```

| File | What it does |
|---|---|
| `deploy/ec2/user-data.sh` | First boot: swap, Docker, AWS CLI, clones the private repo, runs `deploy.sh` |
| `deploy/ec2/deploy.sh` | Pulls the latest code, fetches settings from SSM, builds and starts the containers, waits for HTTPS |
| `deploy/ec2/docker-compose.yml` | `api`, `web` and `caddy` (HTTPS with automatic Let's Encrypt certificates) |
| `deploy/ec2/Caddyfile` | Sends the API's paths to the API and the rest to the web app, on one origin |

No domain yet? It serves on `https://<public-ip-with-dashes>.sslip.io` (for example `https://13-233-10-20.sslip.io`), a free name that points at the instance's IP and gets a real certificate. Add a domain later in one line (step 8).

Run every command below from **AWS CloudShell** (console → the `>_` icon, already signed in) or a terminal with the AWS CLI configured. Use the same region as the RDS database:

```bash
export AWS_REGION=ap-south-1
```

---

## 1. GitHub token for the private repo

The instance clones `SurajsinghBayas/sherpa-ai-mentor`, which is private, so it needs a token.

1. GitHub → Settings → Developer settings → **Fine-grained tokens** → Generate new token.
2. Resource owner `SurajsinghBayas`, **Only select repositories** → `sherpa-ai-mentor`.
3. Repository permissions → **Contents: Read-only** (Metadata: Read-only is added automatically). Nothing else.
4. Pick an expiry, generate, and copy it. It starts with `github_pat_`.

The usual way to clone a private repo with a token is to put it in the URL:

```bash
git clone https://YOUR_GITHUB_USERNAME:YOUR_TOKEN@github.com/YOUR_GITHUB_USERNAME/YOUR_PRIVATE_REPO.git
# here: https://SurajsinghBayas:<token>@github.com/SurajsinghBayas/sherpa-ai-mentor.git
```

`user-data.sh` does exactly that on first boot, then immediately rewrites the remote to the plain URL so the token isn't left in `.git/config`. Updates pass the token to git through environment variables instead.

> **Never write the real token into this guide, a script, user data, or any file in the repo.** Anything committed stays in every clone and in the git history even after it's deleted, and GitHub's secret scanning may block the push or revoke the token. User data is also readable by anyone with EC2 read access. The token lives only in SSM Parameter Store (next step). If a token is ever pasted somewhere public (a chat, an issue, a commit), revoke it and make a new one.

## 2. Store the secrets in SSM Parameter Store

Both are `SecureString` parameters, encrypted with your account's AWS-managed key.

**The GitHub token:**

```bash
read -rs GH_TOKEN && aws ssm put-parameter --name /sherpa/github-token \
  --type SecureString --overwrite --value "$GH_TOKEN"; unset GH_TOKEN
```

(`read -rs` waits for you to paste the token, without showing it or saving it in shell history.)

**The API's settings.** Start from your working `.env` and change what production needs:

```bash
# from the repo root on your laptop
grep -vE '^(ENVIRONMENT|ALLOW_LOCAL_INGEST|ALLOWED_ORIGINS|DATA_DIR)=' .env > sherpa.prod.env
```

Then make sure `sherpa.prod.env` has at least these (no quotes around values):

```bash
DATABASE_URL=postgresql+psycopg://postgres:<password>@<instance>.ap-south-1.rds.amazonaws.com:5432/postgres?sslmode=require
JWT_SECRET_KEY=<openssl rand -hex 32>
ENCRYPTION_KEY=<python3 -c 'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())'>
LLM_PROVIDER=openai
LLM_MODEL=moonshotai.kimi-k2.5
OPENAI_BASE_URL=https://bedrock-mantle.us-east-1.api.aws/v1
OPENAI_API_KEY=<…>
OPENAI_PROJECT_ID=<…>
AWS_BEARER_TOKEN_BEDROCK=<Bedrock API key>
AWS_DEFAULT_REGION=us-east-1
POLLY_ACCESS_KEY_ID=<…>
POLLY_SECRET_ACCESS_KEY=<…>
POLLY_REGION=us-east-1
SMTP_HOST=smtp.gmail.com
SMTP_USER=<…>
SMTP_PASSWORD=<…>
# optional: your own domain (step 8). Leave it out to use <ip>.sslip.io
# DOMAIN=sherpa.example.com
```

`JWT_SECRET_KEY` and `ENCRYPTION_KEY` must be long random values, different from each other. Keep them the same across deploys: changing `ENCRYPTION_KEY` makes saved API keys unreadable, and changing `JWT_SECRET_KEY` signs everyone out. The deploy sets `ENVIRONMENT=production`, `ALLOW_LOCAL_INGEST=false` and `ALLOWED_ORIGINS=https://<domain>` itself, and the API refuses to start if a production setting is unsafe.

Upload it, then delete the local copy:

```bash
aws ssm put-parameter --name /sherpa/env --type SecureString --overwrite \
  --value file://sherpa.prod.env && rm sherpa.prod.env
```

To change a setting later, put the parameter again and redeploy (step 7).

## 3. IAM role for the instance

The instance needs SSM (for Run Command and Session Manager) and read access to `/sherpa/*`, nothing more.

```bash
aws iam create-role --role-name sherpa-ec2 --assume-role-policy-document '{
  "Version": "2012-10-17",
  "Statement": [{"Effect": "Allow", "Principal": {"Service": "ec2.amazonaws.com"}, "Action": "sts:AssumeRole"}]
}'
aws iam attach-role-policy --role-name sherpa-ec2 \
  --policy-arn arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore
aws iam put-role-policy --role-name sherpa-ec2 --policy-name sherpa-read-secrets --policy-document "{
  \"Version\": \"2012-10-17\",
  \"Statement\": [{\"Effect\": \"Allow\", \"Action\": \"ssm:GetParameter\",
    \"Resource\": \"arn:aws:ssm:${AWS_REGION}:*:parameter/sherpa/*\"}]
}"
aws iam create-instance-profile --instance-profile-name sherpa-ec2
aws iam add-role-to-instance-profile --instance-profile-name sherpa-ec2 --role-name sherpa-ec2
sleep 15   # a new instance profile takes a few seconds to be usable
```

## 4. Network: HTTPS in, no SSH

```bash
VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SG=$(aws ec2 create-security-group --group-name sherpa-web --vpc-id "$VPC" \
  --description "Sherpa AI: HTTP and HTTPS only, no SSH" --query GroupId --output text)
aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 80  --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id "$SG" --protocol tcp --port 443 --cidr 0.0.0.0/0
```

Port 80 is only for the certificate check and the redirect to HTTPS. There is deliberately no rule for port 22.

Let the instance reach the database: add an inbound rule to the **RDS instance's** security group for PostgreSQL from this group (assuming RDS is in the same VPC):

```bash
RDS_SG=$(aws rds describe-db-instances --db-instance-identifier database-1 \
  --query 'DBInstances[0].VpcSecurityGroups[0].VpcSecurityGroupId' --output text)
aws ec2 authorize-security-group-ingress --group-id "$RDS_SG" --protocol tcp --port 5432 --source-group "$SG"
```

## 5. Launch the instance

`deploy/ec2/user-data.sh` is the boot script; pass the file as it is in the repo (it holds no secrets). Check `REGION` at its top matches where you stored the parameters.

```bash
AMI=$(aws ssm get-parameter --name /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
  --query Parameter.Value --output text)

ID=$(aws ec2 run-instances \
  --image-id "$AMI" \
  --instance-type t3.medium \
  --iam-instance-profile Name=sherpa-ec2 \
  --security-group-ids "$SG" \
  --user-data file://deploy/ec2/user-data.sh \
  --block-device-mappings 'DeviceName=/dev/sda1,Ebs={VolumeSize=30,VolumeType=gp3}' \
  --metadata-options HttpTokens=required,HttpEndpoint=enabled \
  --tag-specifications 'ResourceType=instance,Tags=[{Key=Name,Value=sherpa-ai}]' \
  --query 'Instances[0].InstanceId' --output text)
echo "$ID"
```

There is no `--key-name`: without a key pair nobody can SSH in, even by mistake.

**Give it a fixed address** right away (otherwise the IP, and the `sslip.io` name, change on every stop/start):

```bash
aws ec2 wait instance-running --instance-ids "$ID"
ALLOC=$(aws ec2 allocate-address --query AllocationId --output text)
aws ec2 associate-address --instance-id "$ID" --allocation-id "$ALLOC"
IP=$(aws ec2 describe-addresses --allocation-ids "$ALLOC" --query 'Addresses[0].PublicIp' --output text)
echo "https://${IP//./-}.sslip.io"
```

`t3.medium` (2 vCPU, 4 GB) is the smallest size that builds the web app comfortably and keeps private-mode repos in memory. The first boot takes about 8–12 minutes: packages, then the Docker builds.

## 6. Watch it come up

Follow the boot log through SSM, no SSH:

```bash
aws ssm send-command --instance-ids "$ID" --document-name AWS-RunShellScript \
  --parameters 'commands=["tail -n 40 /var/log/sherpa-deploy.log"]' \
  --query Command.CommandId --output text
# then, with that id:
aws ssm get-command-invocation --instance-id "$ID" --command-id <command-id> \
  --query StandardOutputContent --output text
```

(The SSM agent registers about a minute after boot; until then `send-command` says the instance isn't valid. `aws ec2 get-console-output --instance-id "$ID" --latest --output text` works from the first second.)

It's done when the log ends with `== up: https://<domain>`. Then check:

```bash
curl -s "https://${IP//./-}.sslip.io/health"
# {"ok":true,"db":"postgres","embeddings":{"available":true},...}
```

Open `https://<ip-with-dashes>.sslip.io`, sign up, and import a repo.

## 7. Update to the latest code

After pushing to `main`, redeploy with one command. It pulls, rebuilds only what changed, and restarts:

```bash
CMD=$(aws ssm send-command --instance-ids "$ID" --document-name AWS-RunShellScript \
  --comment "deploy sherpa" --timeout-seconds 1800 \
  --parameters 'commands=["bash /opt/sherpa/app/deploy/ec2/deploy.sh"]' \
  --query Command.CommandId --output text)
aws ssm wait command-executed --instance-id "$ID" --command-id "$CMD" || true
aws ssm get-command-invocation --instance-id "$ID" --command-id "$CMD" \
  --query '[Status, StandardOutputContent, StandardErrorContent]' --output text | tail -20
```

Do the same after changing `/sherpa/env` or the token. Find the instance id later with
`aws ec2 describe-instances --filters Name=tag:Name,Values=sherpa-ai Name=instance-state-name,Values=running --query 'Reservations[].Instances[].InstanceId' --output text`.

**A shell, still without SSH:** EC2 console → the instance → **Connect** → **Session Manager** → Connect. Or from a terminal with the [Session Manager plugin](https://docs.aws.amazon.com/systems-manager/latest/userguide/session-manager-working-with-install-plugin.html): `aws ssm start-session --target "$ID"`. Useful commands there:

```bash
sudo docker compose -p sherpa ps
sudo docker compose -p sherpa logs --tail 100 api
sudo tail -f /var/log/sherpa-deploy.log
```

## 8. Your own domain (optional)

1. Point an **A record** for, say, `sherpa.example.com` at the Elastic IP.
2. Add `DOMAIN=sherpa.example.com` to `/sherpa/env` (step 2) and redeploy (step 7). Caddy gets the certificate on its own.

## 9. Connect the rest

- **Desktop apps:** build them against the server so they don't call `localhost`:
  `gh variable set SHERPA_API_URL --body "https://<domain>"`, then Actions → desktop → **Run workflow**. The API already accepts the desktop apps' origins.
- **Google sign-in:** in Google Cloud Console → Credentials → the OAuth client, add `https://<domain>` to **Authorized JavaScript origins**.
- **CLI:** `curl -fsSL https://<domain>/cli/sherpa.py -o sherpa` downloads a CLI already pointed at this server.

## Notes

- **Private mode** keeps code in the API container's memory, so it assumes this single instance. A redeploy restarts the API and ends any open private sessions (users re-import).
- **Database:** migrations run on API startup; a new or empty RDS database is set up automatically.
- **Cost (ap-south-1, on demand):** about $30/month for `t3.medium` plus 30 GB gp3. The Elastic IP is free while attached to a running instance. SSM parameters (standard tier) are free.
- **Tear down:** `aws ec2 terminate-instances --instance-ids "$ID"`, then `aws ec2 release-address --allocation-id "$ALLOC"` (an unattached Elastic IP is billed).

## Troubleshooting

| Symptom | Fix |
|---|---|
| `send-command`: instance not in a valid state | The SSM agent isn't registered yet (wait a minute), or the instance profile is missing `AmazonSSMManagedInstanceCore` |
| Log: `AccessDeniedException` on `ssm:GetParameter` | The parameter isn't under `/sherpa/`, or it's in another region than `REGION` in `user-data.sh` |
| Log: `fatal: Authentication failed` / 403 on clone | The token lacks Contents read on this repo, or expired. Put a new one (step 2) and redeploy |
| API exits: `unsafe production config` | The message lists what's wrong in `/sherpa/env` (JWT/encryption keys, `DATABASE_URL`) |
| `/health` hangs, then times out | RDS security group doesn't allow 5432 from `sherpa-web` (step 4) |
| Browser: certificate error | Port 80 or 443 is closed, or the domain doesn't point at the Elastic IP yet |
| Web build killed (`exit code 137`) | Out of memory: use `t3.medium` or larger |
