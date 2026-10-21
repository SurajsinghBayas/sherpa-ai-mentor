#!/bin/bash
# Pull the latest code and (re)start Sherpa AI. Run by user data on first boot, then by SSM Run
# Command for every update (docs/deployment_guide.md). Safe to run again at any time.
# Everything is inside main() so bash has read the whole script before `git pull` replaces it.
set -euo pipefail

main() {
  # shellcheck disable=SC1091
  source /opt/sherpa/config
  local AWS=/snap/bin/aws APP=/opt/sherpa/app
  param() {
    $AWS ssm get-parameter --region "$REGION" --name "$1" --with-decryption \
      --query Parameter.Value --output text
  }

  echo "== $(date -u) deploy"

  # 1. Latest code. The token goes to git as an auth header through the environment, so it
  #    isn't in the command line, the remote URL, or .git/config.
  local token
  token=$(param /sherpa/github-token)
  GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=http.extraHeader \
    GIT_CONFIG_VALUE_0="Authorization: Basic $(printf 'x-access-token:%s' "$token" | base64 -w0)" \
    git -C "$APP" pull --ff-only origin "$BRANCH"
  unset token
  echo "code at $(git -C "$APP" log -1 --format='%h %s')"

  # 2. The API's settings, readable by root only
  (umask 077 && param /sherpa/env > /opt/sherpa/sherpa.env)

  # 3. Public address: DOMAIN from the settings, else <public-ip>.sslip.io (HTTPS without a domain)
  DOMAIN=$(grep -E '^DOMAIN=' /opt/sherpa/sherpa.env | tail -1 | cut -d= -f2- | tr -d '"' || true)
  if [ -z "$DOMAIN" ]; then
    local t ip
    t=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
    ip=$(curl -fsS -H "X-aws-ec2-metadata-token: $t" http://169.254.169.254/latest/meta-data/public-ipv4)
    DOMAIN="${ip//./-}.sslip.io"
  fi
  export DOMAIN
  echo "serving https://$DOMAIN"

  # 4. Build and start (only what changed is rebuilt), then drop old images
  cd "$APP/deploy/ec2"
  docker compose -p sherpa up -d --build --remove-orphans
  docker image prune -f >/dev/null

  # 5. Wait until the API answers through HTTPS (the first certificate takes a few seconds)
  for _ in $(seq 1 40); do
    if curl -fsS "https://$DOMAIN/health" >/dev/null 2>&1; then
      echo "== up: https://$DOMAIN"
      return 0
    fi
    sleep 5
  done
  echo "== not answering yet; check: docker compose -p sherpa logs --tail 100"
  docker compose -p sherpa ps
  return 1
}

main "$@"
