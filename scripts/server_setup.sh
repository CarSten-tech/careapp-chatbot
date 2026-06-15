#!/bin/bash
# CareApp Server-Setup für Ubuntu 24.04
# Einmalig ausführen: bash server_setup.sh

set -e
echo "=== CareApp Setup ==="

# 1. Docker installieren
if ! command -v docker &>/dev/null; then
  echo ">>> Docker wird installiert..."
  apt-get update -q
  apt-get install -y -q ca-certificates curl
  install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
    https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
    > /etc/apt/sources.list.d/docker.list
  apt-get update -q
  apt-get install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin
  echo ">>> Docker installiert."
else
  echo ">>> Docker bereits vorhanden."
fi

# 2. Repo klonen (oder aktualisieren)
REPO_DIR="/opt/careapp"
if [ -d "$REPO_DIR/.git" ]; then
  echo ">>> Repo wird aktualisiert..."
  git -C "$REPO_DIR" pull
else
  echo ">>> Repo wird geklont..."
  git clone https://github.com/CarSten-tech/careapp-chatbot.git "$REPO_DIR"
fi

# 3. .env anlegen wenn noch nicht vorhanden
ENV_FILE="$REPO_DIR/.env"
if [ ! -f "$ENV_FILE" ]; then
  echo ""
  echo "=== Konfiguration ==="
  read -p "DATABASE_URL (Supabase): " DB_URL
  read -p "NVIDIA_API_KEY (nvapi-...): " NVIDIA_KEY
  read -p "NVIDIA_MODEL_ID [moonshotai/kimi-k2.6]: " NVIDIA_MODEL
  NVIDIA_MODEL=${NVIDIA_MODEL:-moonshotai/kimi-k2.6}
  read -p "CAREAPP_ADMIN_TOKEN (mind. 20 Zeichen): " ADMIN_TOKEN
  read -p "CAREAPP_ALLOWED_ORIGINS (Vercel-URL, z.B. https://careapp.vercel.app): " ORIGINS

  cat > "$ENV_FILE" <<EOF
DATABASE_URL=$DB_URL
NVIDIA_API_KEY=$NVIDIA_KEY
NVIDIA_MODEL_ID=$NVIDIA_MODEL
CAREAPP_ADMIN_TOKEN=$ADMIN_TOKEN
CAREAPP_ALLOWED_ORIGINS=$ORIGINS
CAREAPP_GRAPH_VERSION=graph-v1
CAREAPP_PROMPT_VERSION=prompts-v1
CAREAPP_MODEL_VERSION=models-v1
EOF
  echo ">>> .env gespeichert."
else
  echo ">>> .env bereits vorhanden — wird nicht überschrieben."
fi

# 4. Docker-Image bauen + Container starten
echo ">>> Docker-Image wird gebaut (dauert 2–4 Minuten beim ersten Mal)..."
cd "$REPO_DIR"
docker build -t careapp:latest .

# Alten Container stoppen falls er läuft
docker stop careapp 2>/dev/null || true
docker rm   careapp 2>/dev/null || true

echo ">>> Container wird gestartet..."
docker run -d \
  --name careapp \
  --restart unless-stopped \
  --env-file "$ENV_FILE" \
  -p 8000:8000 \
  careapp:latest

echo ""
echo "=== Fertig ==="
echo ">>> FastAPI läuft auf Port 8000."
echo ">>> Health-Check: curl http://localhost:8000/api/v1/health"
echo ">>> Logs: docker logs -f careapp"
