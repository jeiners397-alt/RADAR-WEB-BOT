#!/usr/bin/env bash
# Despliegue idempotente en Ubuntu 24.04. Uso (en el VPS):  bash scripts/vps/deploy.sh
# Requisitos: Docker + plugin compose. Genera secretos en /opt/capital-radar/.env (chmod 600) solo la primera vez.
set -euo pipefail
APP=/opt/capital-radar
REPO=https://github.com/jeiners397-alt/RADAR-WEB-BOT.git
BRANCH=${BRANCH:-feat/capital-radar-pro-v1}

if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sudo sh
  sudo usermod -aG docker "$USER" || true
fi
sudo mkdir -p "$APP" && sudo chown "$USER":"$USER" "$APP"
if [ -d "$APP/.git" ]; then git -C "$APP" fetch --all -q && git -C "$APP" checkout -q "$BRANCH" && git -C "$APP" pull -q --ff-only
else git clone -q -b "$BRANCH" "$REPO" "$APP"; fi
cd "$APP"

if [ ! -f .env ]; then
  umask 077
  KEY=$(docker run --rm python:3.12-slim sh -c 'pip install -q cryptography >/dev/null 2>&1 && python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"')
  { cat .env.example | grep -v '^POSTGRES_PASSWORD=' | grep -v '^CREDENTIAL_ENCRYPTION_KEY='
    echo "POSTGRES_PASSWORD=$(openssl rand -hex 24)"; echo "CREDENTIAL_ENCRYPTION_KEY=$KEY"; } > .env
  chmod 600 .env
  echo ">> .env creado (secretos generados en el servidor). RESPALDA CREDENTIAL_ENCRYPTION_KEY por separado."
fi

docker compose up -d --build
echo ">> Esperando salud de la API…"
for i in $(seq 1 40); do curl -fsS http://127.0.0.1:8000/api/v1/ready >/dev/null 2>&1 && break || sleep 3; done
curl -fsS http://127.0.0.1:8000/api/v1/ready && echo
echo ">> Crea el administrador (interactivo, la contraseña no se guarda en ningún archivo):"
echo "   docker compose exec api python /app/scripts/create_admin.py admin"
echo ">> Acceso (túnel SSH desde Windows):  ssh -i <clave> -L 8000:127.0.0.1:8000 <usuario>@<ip>   →  http://localhost:8000"

# arranque tras reinicio del VPS
sudo cp infra/capital-radar.service /etc/systemd/system/ && sudo systemctl daemon-reload && sudo systemctl enable capital-radar.service >/dev/null
