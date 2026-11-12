# Estado de implementación (11–12 nov 2026)

Leyenda: **IMPLEMENTADO** = funciona y está probado · **PARCIAL** · **BLOQUEADO** (falta algo externo) · **NO DISPONIBLE** (no construido).

## Verificación realizada
| Prueba | Resultado |
|---|---|
| `pytest` backend (unitarias + API + workers) | **40 pasan** (métricas, sizing 5 %, backtest determinista/sin lookahead, ledger paper, idempotencia, kill switch, aislamiento entre usuarios, no-filtración de secretos, 3 workers sin duplicados y conteos consistentes, recuperación de leases) |
| `tsc --noEmit` + `vite build` frontend | OK (bundle 165 kB gzip) |
| E2E Playwright contra backend real + Binance público real | **27/27**: login → dashboard → selector → 13 rutas → orden MANUAL 17 USDT → historial → cuenta Exness "no conectada" → retorno a Binance Paper → sin secretos en storage → móvil sin scroll horizontal |
| Binance público real desde este PC | OK (ticker, velas, 3 742 instrumentos, filtros reales BTCUSDT `minNotional=5`) |
| `docker compose up -d --build` | **NO EJECUTADO**: este PC no tiene Docker. Se probará en el VPS. |
| CI de GitHub Actions | Definido; **no ejecutado** (no se ha subido nada: falta `gh auth login`). |

## Funcionalidades
| Área | Estado | Notas |
|---|---|---|
| Login, sesión HttpOnly, CSRF, bloqueo por intentos, Argon2, asistente de admin sin contraseña por defecto | IMPLEMENTADO | `scripts/create_admin.py` |
| Dashboard (composición de la referencia) con datos reales | IMPLEMENTADO | Sin cifras hardcodeadas; vacíos/N/A honestos |
| Selector de cuenta que remonta todas las vistas y reabre el WebSocket | IMPLEMENTADO | Probado en E2E y API |
| Binance público (spot + futuros datos), rate-limit, backoff, circuit breaker | IMPLEMENTADO | Spot probado en vivo; **futuros sin probar en vivo** |
| WebSocket de Binance (streams de mercado) | NO DISPONIBLE | Se usa polling (5–15 s). El WebSocket propio de la app (snapshot por cuenta, seq, expiración) sí existe |
| Paper 100 USDT, MANUAL vs ALGORITHM, fees/slippage, SL/TP, reset auditado | IMPLEMENTADO | Spot largo; sin cortos ni apalancamiento |
| 5 % algorítmico con minNotional/step | IMPLEMENTADO | Ajuste de máx. 1 step documentado (DECISIONS #5). El disparo de señales automáticas continuas **no existe**: solo `POST /paper/algo-orders` por estrategia habilitada y con `PAPER_AUTO_TRADING_ENABLED=true` |
| Motor de señales automático (bot que evalúa estrategias y opera solo) | NO DISPONIBLE | Las plantillas generan señales para backtest; falta el scheduler que las evalúe en vivo |
| Investigación con workers, cola, leases, reintentos, pausa/reanuda/cancela | IMPLEMENTADO | 3 workers probados en tests; en el VPS corre 1 |
| Indicadores EMA/SMA/RSI/ATR/RVOL/POC·VAH·VAL, régimen | IMPLEMENTADO | Sin ADX/MACD/VWAP ni SMC (BOS/CHoCH/FVG) |
| Estrategias versionadas y validadas | IMPLEMENTADO | 6 plantillas; 5 sembradas (S01–S05) sin métricas |
| Backtesting reproducible + OOS + buy&hold + export en pantalla | IMPLEMENTADO | Sin walk-forward completo; export CSV de backtest no disponible |
| Mercados, favoritos, búsqueda | IMPLEMENTADO | Multi-chart no |
| Conectores: credenciales cifradas Fernet, borrar/revocar, máscara | IMPLEMENTADO | Verificación de permisos de claves privadas Binance: NO implementada |
| Exness / MT5 | BLOQUEADO | Requieren pasarela MT5/Windows; adaptadores honestos "no conectado" |
| Trading en vivo | IMPLEMENTADO como **bloqueo** | Sin ruta de ejecución real |
| Riesgo (límites, kill switch, denegaciones) | IMPLEMENTADO | Simulación de escenarios: NO |
| Informes/auditoría, export CSV/JSON | IMPLEMENTADO | PDF: NO |
| Telemetría CPU/RAM/disco/latencia/heartbeats | IMPLEMENTADO | Requiere worker-market corriendo |
| Paleta Ctrl+K, animaciones, reduced-motion | IMPLEMENTADO | |
| Modo DEMO visual con cifras de la captura | NO DISPONIBLE | Decisión: evitar cifras ficticias |
| 2FA, RBAC multiusuario, notificaciones externas | NO DISPONIBLE | |
| Alembic (migraciones) | NO DISPONIBLE | `create_all` en v1 (deuda) |
| Despliegue en Azure | **BLOQUEADO** | Falta el usuario SSH de la VM; ver `OPEN_QUESTIONS.md` |
| Limpieza de bots antiguos del VPS | **NO REALIZADA** | Depende del acceso SSH |

## Deudas / riesgos conocidos
- `trade_samples` solo registra entrada y salida (no muestreo intermedio).
- Cobertura de tests de frontend: solo E2E (sin Vitest unitario).
- Sin protección CSRF/rate-limit fuera de login; sin 2FA: el panel debe quedar tras túnel SSH/HTTPS.
- El rate-limit de login es en memoria (se reinicia con el proceso).
