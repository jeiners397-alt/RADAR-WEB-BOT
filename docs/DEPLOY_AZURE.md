# Despliegue en Azure (Ubuntu 24.04, 2 vCPU / 4 GiB)

> Estado: **NO desplegado todavía** (falta el usuario SSH; ver `OPEN_QUESTIONS.md`). Este documento es el procedimiento exacto.

## 0. Conexión (desde Windows)
```powershell
ssh -i "C:\ruta\a\tu\clave.pem" -o IdentitiesOnly=yes <USUARIO_AZURE>@20.78.0.70
```
Verifica la huella del host (Azure Portal → VM → *Serial console* o `ssh-keygen -lf` en la VM) antes de aceptarla. La IP pública puede cambiar: confírmala en el portal.

## 1. Inventario (solo lectura) y retiro de bots antiguos
```powershell
ssh -i <clave> <usuario>@20.78.0.70 'bash -s' < scripts/vps/inventory.sh > $env:USERPROFILE\capital-radar-backups\inventario.txt
```
Reglas: (1) identificar con certeza qué es un bot anterior (servicio systemd, contenedor, cron, directorio en `$HOME`/`/opt`); (2) detenerlo de forma controlada (`systemctl stop`, `docker compose stop`); (3) **respaldo cifrado** (`tar | openssl enc -aes-256-cbc -pbkdf2`) bajado a `%USERPROFILE%\capital-radar-backups` y **probar el descifrado**; (4) borrar solo rutas/servicios/contenedores atribuidos, con un manifiesto del retiro y cómo restaurarlos; (5) lo dudoso, operaciones reales activas o servicios que afecten el acceso SSH **no se tocan** y se anotan.

## 2. Instalar
```bash
bash <(curl -fsSL https://raw.githubusercontent.com/jeiners397-alt/RADAR-WEB-BOT/feat/capital-radar-pro-v1/scripts/vps/deploy.sh)   # o clonar y ejecutar scripts/vps/deploy.sh
docker compose exec api python /app/scripts/create_admin.py admin     # contraseña interactiva
```
Genera `/opt/capital-radar/.env` (600) con `POSTGRES_PASSWORD` y `CREDENTIAL_ENCRYPTION_KEY`. **Guarda esa clave en un gestor de contraseñas**: sin ella no se pueden descifrar credenciales de brokers.

## 3. Acceso sin dominio (túnel SSH)
```powershell
.\scripts\windows\ssh-tunnel.ps1 -KeyPath "C:\ruta\clave.pem" -User <usuario>   # y abre http://localhost:8000
```
En el NSG de Azure deja abierto solo 22 (idealmente restringido a tu IP). 80/443 solo cuando haya dominio.

## 4. Dominio + HTTPS (cuando exista)
DNS A → IP del VPS; en `.env`: `DOMAIN=tu.dominio`, `COOKIE_SECURE=true`; `docker compose --profile domain up -d`; abrir 80/443 en el NSG. Caddy obtiene el certificado Let's Encrypt.

## 5. Verificación obligatoria antes de declarar completado
`curl 127.0.0.1:8000/api/v1/ready` · login · dashboard con 100 USDT · `docker compose ps` (todo *healthy*) · `sudo reboot` y repetir (los contenedores deben volver solos) · `bash scripts/vps/backup.sh` y comprobar el descifrado.

## 6. Recursos
Límites de memoria: db 512 MB, api 768 MB, research 512 MB, market 384 MB (~2.2 GB del total). `RESEARCH_WORKERS=1`. Vigila disco y créditos en Azure Cost Management (alertas de presupuesto).

## 7. Backups
`scripts/vps/backup.sh` (cron diario) → `/var/backups/capital-radar/*.enc` + sha256; rotación 14 días. Copia externa pendiente (ver `OPEN_QUESTIONS.md`).
