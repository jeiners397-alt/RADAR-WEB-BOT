# Decisiones técnicas

| # | Decisión | Motivo |
|---|----------|--------|
| 1 | **Cola de investigación en la propia BD** (leases + `UPDATE` condicional), sin Redis/Celery | VPS de 4 GiB: menos servicios y menos RAM. El reclamo atómico, reintentos, pausa/reanuda y recuperación tras reinicio están cubiertos por tests. Redis puede añadirse si hace falta (backlog). |
| 2 | **PostgreSQL 16 en producción, SQLite en desarrollo/tests** | Mismo SQLAlchemy; la reserva atómica de saldo usa `SELECT … FOR UPDATE` (efectivo en PostgreSQL). |
| 3 | **Sin Alembic en v1**: `create_all` al arrancar | Primera versión sin datos previos que migrar. **Deuda**: introducir Alembic antes del primer cambio de esquema en producción. |
| 4 | **Dimensionamiento 5 %** = 5 % del *patrimonio* (caja + posiciones marcadas a mercado) como **exposición nominal**, no riesgo | Definición del encargo. Se redondea hacia abajo al `stepSize`. |
| 5 | **Ajuste de 1 step** hacia arriba (máx. +10 % del objetivo) únicamente para alcanzar `minNotional` | Con 100 USDT el objetivo es 5 USDT y `minNotional` típico es 5: el redondeo hacia abajo casi siempre dejaba el nocional apenas por debajo y rechazaba todas las entradas. Si el objetivo < `minNotional`, o hace falta más de 1 step, se **rechaza** (nunca sube a 10). |
| 6 | Órdenes `limit` en paper solo se llenan si son ejecutables ya; si no, se **rechazan** con motivo | No se simula un libro de órdenes que no existe. |
| 7 | Backtest: señal en cierre de vela *i*, ejecución en la apertura de *i+1*; vela en formación excluida; cierre forzado al final; fracción OOS configurable | Evita lookahead. |
| 8 | **Profit Factor = N/A** si no hay pérdidas; **Win Rate = N/A** sin operaciones | No se inventan infinitos ni 0 %. |
| 9 | Solo **5 plantillas de estrategia con nombre** (S01–S05) y sin métricas | La captura mostraba 12 con cifras de ejemplo; no hay evidencia para ninguna. |
| 10 | Datos de mercado vía `data-api.binance.vision` (público) con token bucket, backoff y circuit breaker | Sin claves. Futuros: `fapi.binance.com` (solo datos). |
| 11 | Sesión por cookie HttpOnly + SameSite=Strict + cabecera CSRF; contraseñas Argon2; bloqueo tras 5 fallos | Estándar para panel de administración. |
| 12 | Credenciales de brokers cifradas con **Fernet**; la clave vive en variable de entorno/archivo 0600 **fuera de la BD** | Azure Key Vault queda como mejora (requiere identidad gestionada de la VM). |
| 13 | **Trading real sin ruta de código**: `place_order` del adaptador lanza error; `real_trading_allowed` es siempre `False` | Requisito irrenunciable. |
| 14 | Acceso sin dominio: API ligada a `127.0.0.1:8000` + **túnel SSH**; Caddy listo (`--profile domain`) | No exponer un panel por HTTP plano ni con certificado autofirmado. |
| 15 | Frontend sin Tailwind: CSS propio + SVG para gráficos de equity/donut y `lightweight-charts` para velas | Menos dependencias y bundle pequeño (165 kB gzip). |
| 16 | Paper de Exness/MT5 **no** implementado | No existe feed verificado; se muestran como "no conectado". |
