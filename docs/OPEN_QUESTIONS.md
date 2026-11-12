# Preguntas abiertas y bloqueos

1. ~~Usuario SSH~~ **Resuelto**: `azureuser`. (Antes: no figura en la configuración SSH de Windows (no existe `~/.ssh/config`). Está en Azure Portal → VM → *Conectar → SSH* (campo "Nombre de usuario"; por defecto de Azure suele ser `azureuser`, pero **no se ha probado ningún usuario al azar**). Hasta tenerlo no se toca el servidor.)
2. **Pull Request** — el `git push` funciona (credencial de Git de Windows), pero `gh` no tiene sesión: ejecutar `gh auth login` para abrir el PR desde la CLI, o crearlo en la web.
3. **Dominio** — sin dominio no hay HTTPS público. Cuando exista: apuntar el DNS A a la IP del VPS, poner `DOMAIN=` y `COOKIE_SECURE=true` en `.env` y `docker compose --profile domain up -d`. Abrir 80/443 en el NSG de Azure.
4. **Exness / MT5** — requieren pasarela MT5 (terminal Windows) autorizada. Pendiente de decidir dónde correrá (VM Windows o PC propio) y de revisar los términos de Exness para automatización.
5. **Política de respaldo externo** — `backup.sh` cifra y verifica en el VPS. Falta decidir el destino externo (p. ej. Azure Blob con SAS de solo escritura, o descarga periódica a `%USERPROFILE%\capital-radar-backups`).
6. **Azure Key Vault** — mejora opcional para la clave Fernet.
7. **Alertas de créditos/cuota de Azure** — se configuran en Azure Cost Management (no desde el repo).
