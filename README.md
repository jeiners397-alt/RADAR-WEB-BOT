# CAPITAL RADAR PRO v1.0

Laboratorio de trading algorítmico: investigación, backtesting y **paper trading** (100 USDT virtuales) sobre datos **públicos** de Binance, con arquitectura de conectores para Exness y MetaTrader 5.

> **Las operaciones reales están deshabilitadas.** El backend no contiene ninguna ruta que envíe órdenes reales. Todas las cifras de la interfaz salen de la API/BD; no hay rentabilidades inventadas.

## Qué incluye
- **Dashboard** (composición de la referencia aprobada) con KPIs reales, investigación, régimen de mercado, conectores, bots y resultados mensuales.
- **Investigación R2.0** con cola persistente, workers concurrentes, leases, reintentos con backoff, pausa/reanuda/cancela/reintenta.
- **Estrategias** versionadas (plantillas validadas en backend) · **Backtesting** determinista (sin lookahead, costes, OOS, buy&hold, hash de dataset).
- **Paper Trading**: ledger consistente; órdenes **MANUAL** (monto que eliges) y **ALGORITHM** (5 % del patrimonio con filtros `minNotional/stepSize`).
- **Mercados** con gráfico de velas, indicadores (EMA/SMA/RSI/ATR/RVOL/POC·VAH·VAL), favoritos.
- **Conectores** Binance / Exness / MT5 con credenciales cifradas en el servidor (adaptadores Exness/MT5 honestamente "no conectado").
- **Riesgo** (límites + kill switch) · **Informes & Auditoría** (CSV/JSON) · **Configuración**.

Estado detallado y honesto: [`docs/IMPLEMENTATION_STATUS.md`](docs/IMPLEMENTATION_STATUS.md). Decisiones: [`docs/DECISIONS.md`](docs/DECISIONS.md). Pendientes: [`docs/OPEN_QUESTIONS.md`](docs/OPEN_QUESTIONS.md).

## Desarrollo local (Windows / PowerShell)
```powershell
cd frontend; npm ci; npx vite build; cd ..
.\scripts\windows\run-local.ps1 -DataDir C:\dev\radar-data     # API :8000 + workers (SQLite fuera del repo)
cd backend; python ..\scripts\create_admin.py admin             # pide la contraseña (≥12 caracteres)
```
Abre http://localhost:8000. Pruebas: `cd backend; python -m pytest -q` · `cd frontend; npx tsc --noEmit` · E2E: `node e2e/smoke.mjs` (ver cabecera del archivo).

Si tu red inspecciona TLS (Python falla con `CERTIFICATE_VERIFY_FAILED`): `USE_SYSTEM_TRUST=true`.

## Producción (Ubuntu 24.04 en Azure, 2 vCPU / 4 GiB)
Ver [`docs/DEPLOY_AZURE.md`](docs/DEPLOY_AZURE.md). Resumen: `bash scripts/vps/deploy.sh` → Docker Compose (`restart: unless-stopped`, healthchecks, límites de memoria) y acceso por **túnel SSH** hasta disponer de dominio + HTTPS.

## Seguridad
El repositorio es **público**: nunca subas `.env`, `.pem`, bases de datos, respaldos ni logs. `.gitignore` y el job `secrets-scan` de CI lo vigilan. Credenciales de brokers: formulario → HTTPS → backend → cifrado Fernet; nunca se devuelven ni se guardan en el navegador.
