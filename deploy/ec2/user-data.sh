#!/bin/bash
# EC2 user data for Sherpa AI on Ubuntu 24.04: everything a fresh instance needs, so no SSH.
# Secrets come from SSM Parameter Store (/sherpa/github-token, /sherpa/env), never from this
# file, which anyone with EC2 read access can see. Progress: /var/log/sherpa-deploy.log.
# Guide: docs/deployment_guide.md
set -euo pipefail
exec > >(tee -a /var/log/sherpa-deploy.log) 2>&1

REGION=ap-south-1                         # where the /sherpa/* parameters live
GITHUB_USER=SurajsinghBayas
REPO=SurajsinghBayas/sherpa-ai-mentor
BRANCH=main

echo "== $(date -u) first boot"

# 2 GB of swap: building the web app needs more memory than a small instance has
if [ ! -f /swapfile ]; then
  fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y docker.io docker-compose-v2 git curl
systemctl enable --now docker
snap install aws-cli --classic
AWS=/snap/bin/aws

mkdir -p /opt/sherpa
cat > /opt/sherpa/config <<EOF
REGION=$REGION
REPO=$REPO
BRANCH=$BRANCH
EOF

# Private repo: clone with the token, then drop it from .git/config straight away
if [ ! -d /opt/sherpa/app/.git ]; then
  TOKEN=$($AWS ssm get-parameter --region "$REGION" --name /sherpa/github-token \
    --with-decryption --query Parameter.Value --output text)
  git clone --branch "$BRANCH" "https://${GITHUB_USER}:${TOKEN}@github.com/${REPO}.git" /opt/sherpa/app
  git -C /opt/sherpa/app remote set-url origin "https://github.com/${REPO}.git"
  unset TOKEN
fi

bash /opt/sherpa/app/deploy/ec2/deploy.sh
