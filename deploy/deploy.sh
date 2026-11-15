#!/usr/bin/env bash
# Deploy (or redeploy) to a Vultr server from your laptop.
#   ./deploy/deploy.sh <server-ip> [domain]     domain defaults to will-agents-buy.us; pass "" for plain http on the IP
# Copies the code and your .env (never via git), builds the container on the server and starts it behind Caddy.
# With a domain whose DNS A record points at the server, Caddy gets an HTTPS certificate automatically.
set -euo pipefail
IP="${1:?usage: ./deploy/deploy.sh <server-ip> [domain]}"
DOMAIN="${2-will-agents-buy.us}"
HOST="root@$IP"
cd "$(dirname "$0")/.."
[ -f .env ] || { echo "No .env here. Copy .env.example to .env and fill in your keys first."; exit 1; }

echo "→ waiting for the server to finish setting up (Docker install)…"
for i in $(seq 1 60); do ssh -o StrictHostKeyChecking=accept-new -o ConnectTimeout=5 "$HOST" 'test -f /root/cloud-init-done && command -v docker' >/dev/null 2>&1 && break; sleep 5; done
ssh "$HOST" 'command -v docker' >/dev/null || { echo "Docker isn't on the server yet. Did you paste deploy/cloud-init.yaml when creating it?"; exit 1; }

echo "→ copying code"
rsync -az --delete --exclude .git --exclude .venv --exclude venv --exclude runs --exclude 'web/node_modules' --exclude 'web/dist' \
  --exclude '__pycache__' --exclude '.env' --exclude 'deploy/.env' --exclude '.DS_Store' ./ "$HOST:/root/app/"
echo "→ copying .env (secrets go over SSH only)"
scp -q .env "$HOST:/root/app/.env"
ssh "$HOST" "chmod 600 /root/app/.env && echo 'SITE=${DOMAIN:-:80}' > /root/app/deploy/.env"

echo "→ building and starting (first build takes a few minutes)"
ssh "$HOST" 'cd /root/app && docker compose -f deploy/docker-compose.yml up -d --build && docker image prune -f >/dev/null'

URL="http://$IP"; [ -n "$DOMAIN" ] && URL="https://$DOMAIN"
echo "→ checking $URL"
for i in $(seq 1 30); do curl -fsS -o /dev/null "$URL/api/shoppers" 2>/dev/null && { echo "✓ live at $URL"; exit 0; }; sleep 4; done
echo "Not answering yet. Logs: ssh $HOST 'cd /root/app && docker compose -f deploy/docker-compose.yml logs --tail 50 app'"
