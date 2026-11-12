#!/usr/bin/env bash
# Inventario SOLO LECTURA del VPS antes de instalar CAPITAL RADAR PRO. No modifica nada.
# Uso: ssh -i <clave> <usuario>@<ip> 'bash -s' < scripts/vps/inventory.sh
set -u
echo "== Sistema ==";  . /etc/os-release; echo "$PRETTY_NAME"; uname -r; nproc; free -h | sed -n 1,2p; df -h / | tail -1
echo; echo "== Usuario/sesión =="; id; who
echo; echo "== Puertos en escucha =="; (ss -tlnp 2>/dev/null || sudo -n ss -tlnp 2>/dev/null) | head -40
echo; echo "== Docker =="; if command -v docker >/dev/null; then docker --version; docker ps -a --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}' 2>&1 | head -40; docker volume ls 2>&1 | head -30; docker compose ls -a 2>&1 | head; else echo "docker no instalado"; fi
echo; echo "== Servicios systemd (no del sistema base) =="; systemctl list-units --type=service --state=running --no-pager 2>/dev/null | grep -Eiv 'systemd|dbus|ssh|cron|rsyslog|networkd|resolved|udev|getty|polkit|snapd|multipathd|chrony|unattended|walinux|waagent|irqbalance|packagekit|ModemManager|udisks|fwupd|cloud-|hv_|lvm|apport|accounts-daemon|serial' | head -30
echo; echo "== Servicios habilitados custom (/etc/systemd/system) =="; ls -la /etc/systemd/system/*.service 2>/dev/null | head -30
echo; echo "== Cron =="; crontab -l 2>&1 | head -30; ls -la /etc/cron.d 2>/dev/null | head
echo; echo "== Procesos de usuario (python/node/screen/tmux/pm2) =="; ps -eo user,pid,etime,pcpu,pmem,cmd --sort=-pmem | grep -Ei 'python|node|pm2|screen|tmux|bot|trading|freqtrade|ccxt' | grep -v grep | head -30
echo; echo "== Directorios candidatos (home, /opt, /srv) =="; ls -la ~ 2>/dev/null | head -50; ls -la /opt /srv 2>/dev/null | head -30
echo; echo "== Tamaño de directorios en home =="; du -sh ~/* 2>/dev/null | sort -h | tail -20
echo; echo "== Firewall =="; (sudo -n ufw status 2>&1 || echo "ufw no consultable sin sudo") | head -15
