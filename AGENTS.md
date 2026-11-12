# Instrucciones para asistentes (Claude y otros)

- Idioma de interfaz y documentación: **español**. Código en inglés.
- **Nunca** habilites trading real ni añadas un camino de ejecución live sin autorización escrita del propietario.
- **Nunca** versiones secretos (`.env`, `.pem`, claves, BD, respaldos, logs). El repo es público.
- No inventes cifras: toda métrica sale de operaciones/ledger reales. Sin datos → `N/A`/`—`/estado vacío.
- Órdenes `MANUAL` usan el tamaño del usuario; solo `ALGORITHM` usa 5 % del patrimonio (`backend/app/sizing.py`).
- Cada consulta sensible a cuenta debe pasar por `deps.owned_account` (aislamiento server-side).
- Antes de dar algo por terminado: `cd backend && python -m pytest -q`, `cd frontend && npx tsc --noEmit && npx vite build`.
- VPS: 2 vCPU / 4 GiB. Un worker de investigación; no lances cientos de backtests simultáneos.
- Limpieza del VPS: inventariar → respaldar cifrado y verificar → retirar solo lo atribuible con certeza. Nunca `rm -rf` amplios ni `docker system prune --all --volumes`.
