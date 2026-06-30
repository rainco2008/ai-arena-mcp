#!/usr/bin/env bash
set -euo pipefail

# Required: edit these variables before running this script.
DOMAIN="search.example.com"
ACME_EMAIL="admin@example.com"

# Optional.
REPO_URL="https://github.com/rainco2008/ai-arena-mcp.git"
APP_DIR="/opt/ai-arena-mcp"
ADMIN_TOKEN=""
GEMINI_SEARCH_BROWSER_BACKEND="playwright"
GEMINI_SEARCH_PROXY_SERVER=""
GEMINI_SEARCH_PROFILE_ROTATION_SECONDS="0"

if [[ "${DOMAIN}" == "search.example.com" || "${ACME_EMAIL}" == "admin@example.com" ]]; then
  echo "ERROR: Edit DOMAIN and ACME_EMAIL in this script before running it." >&2
  exit 1
fi

if [[ -z "${ADMIN_TOKEN}" ]]; then
  ADMIN_TOKEN="$(od -An -N24 -tx1 /dev/urandom | tr -d ' \n')"
fi

if [[ "$(id -u)" -ne 0 ]]; then
  echo "ERROR: Run this script as root, for example: sudo bash scripts/deploy_ubuntu_docker.sh" >&2
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "ERROR: Docker is not installed. Install Docker manually first, then rerun this script." >&2
  echo "Ubuntu reference: https://docs.docker.com/engine/install/ubuntu/" >&2
  exit 1
fi

if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: Docker Compose plugin is not available. Install docker-compose-plugin manually first." >&2
  echo "Ubuntu reference: https://docs.docker.com/compose/install/linux/" >&2
  exit 1
fi

if ! command -v git >/dev/null 2>&1; then
  echo "ERROR: git is not installed. Install it first, for example: sudo apt-get install -y git" >&2
  exit 1
fi

systemctl is-active --quiet docker || systemctl start docker

if command -v ufw >/dev/null 2>&1; then
  ufw allow 80/tcp || true
  ufw allow 443/tcp || true
fi

if [[ -d "${APP_DIR}/.git" ]]; then
  git -C "${APP_DIR}" pull --ff-only
else
  mkdir -p "$(dirname "${APP_DIR}")"
  git clone "${REPO_URL}" "${APP_DIR}"
fi

cat > "${APP_DIR}/.env.production" <<EOF
DOMAIN=${DOMAIN}
ACME_EMAIL=${ACME_EMAIL}
ADMIN_TOKEN=${ADMIN_TOKEN}
GEMINI_SEARCH_BROWSER_BACKEND=${GEMINI_SEARCH_BROWSER_BACKEND}
GEMINI_SEARCH_PROXY_SERVER=${GEMINI_SEARCH_PROXY_SERVER}
GEMINI_SEARCH_PROFILE_ROTATION_SECONDS=${GEMINI_SEARCH_PROFILE_ROTATION_SECONDS}
EOF

cd "${APP_DIR}"
docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build

echo
echo "Deployment completed."
echo "Console URL: https://${DOMAIN}/"
echo "API base URL: https://${DOMAIN}/v1"
echo "Check models: curl https://${DOMAIN}/v1/models"
echo "Admin token: ${ADMIN_TOKEN}"
