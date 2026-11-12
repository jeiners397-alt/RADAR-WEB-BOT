// E2E: login → dashboard → mercado → orden manual paper → historial → cuenta no conectada → vuelta a Binance.
// Uso: BASE_URL=http://127.0.0.1:8000 ADMIN_PASSWORD_FILE=... node e2e/smoke.mjs
import { chromium } from 'playwright'
import fs from 'node:fs'

const BASE = process.env.BASE_URL ?? 'http://127.0.0.1:8000'
const PW = fs.readFileSync(process.env.ADMIN_PASSWORD_FILE, 'utf8').trim()
const OUT = process.env.SHOTS ?? 'shots'
fs.mkdirSync(OUT, { recursive: true })
const results = []
const ok = (name, cond, extra = '') => { results.push({ name, pass: !!cond }); console.log((cond ? 'PASS ' : 'FAIL ') + name + (extra ? ' — ' + extra : '')) }

const browser = await chromium.launch()
const ctx = await browser.newContext({ viewport: { width: 1648, height: 928 }, locale: 'es-PE' })
const page = await ctx.newPage()
page.setDefaultTimeout(Number(process.env.PW_TIMEOUT ?? 30000))
page.setDefaultNavigationTimeout(Number(process.env.PW_TIMEOUT ?? 30000))
const errors = []
page.on('pageerror', e => errors.push(String(e)))
page.on('console', m => { if (m.type() === 'error' && !/favicon|WebSocket|401/i.test(m.text())) errors.push(m.text()) })

await page.goto(BASE)
await page.fill('input[autocomplete=username]', process.env.ADMIN_USER ?? 'admin')
await page.fill('input[type=password]', 'mala-clave')
await page.click('button.btn')
await page.waitForSelector('.err')
ok('login con clave incorrecta es rechazado', (await page.locator('.err').count()) > 0)
await page.fill('input[type=password]', PW)
await page.click('button.btn')
await page.waitForURL('**/dashboard')
await page.waitForSelector('.kpis')
await page.waitForTimeout(3500)
ok('login → /dashboard (no landing)', page.url().endsWith('/dashboard'))
const txt = await page.locator('main').innerText()
ok('capital paper inicial 100.00', /100\.00/.test(txt))
ok('no hay cifras demo hardcodeadas (10,000 / 412 / 484 / 39.42)', !/10,000\.00|412|484 |39\.42/.test(txt))
ok('Trading real bloqueado visible', /Bloqueado/.test(txt))
await page.screenshot({ path: `${OUT}/dashboard-desktop.png` })

const sym = page.locator('input[aria-label="Símbolo"]').first()
await sym.fill('ETHUSDT'); await sym.press('Enter'); await page.waitForTimeout(2500)
ok('selector cambia el símbolo del gráfico', (await sym.inputValue()) === 'ETHUSDT')

for (const [path, h] of [['investigacion', 'Investigación R2.0'], ['estrategias', 'Estrategias'], ['backtesting', 'Backtesting'], ['paper', 'Paper Trading'], ['live', 'Trading en Vivo'], ['bots', 'Bots'], ['mercados', 'Mercados'], ['conectores/binance', 'Conector'], ['conectores/exness', 'Exness'], ['conectores/mt5', 'MetaTrader'], ['riesgo', 'Riesgo'], ['informes', 'Informes'], ['configuracion', 'Configuración']]) {
  await page.goto(`${BASE}/${path}`); await page.waitForSelector('.page-title h2'); await page.waitForTimeout(700)
  ok(`ruta /${path}`, (await page.locator('.page-title h2').innerText()).includes(h))
  await page.screenshot({ path: `${OUT}/${path.replace('/', '-')}.png` })
}

await page.goto(`${BASE}/paper`); await page.waitForSelector('.page-title h2'); await page.waitForTimeout(1500)
await page.locator('label:has-text("Valor") input').fill('17')
await page.locator('label:has-text("Confirmo") input').check()
await page.click('text=Enviar orden MANUAL')
await page.waitForTimeout(2500)
const body = await page.locator('main').innerText()
ok('orden manual de 17 USDT ejecutada con etiqueta MANUAL', /MANUAL/.test(body) && /filled/.test(body))
await page.screenshot({ path: `${OUT}/paper-after-order.png` })

await page.locator('.seg button:has-text("Vender")').click()
await page.locator('label:has-text("Confirmo") input').check()
await page.click('text=Enviar orden MANUAL'); await page.waitForTimeout(2500)
const after = await page.locator('main').innerText()
ok('historial muestra operación cerrada', after.includes('P&L neto') && !after.includes('Aún no hay operaciones cerradas'))

await page.goto(`${BASE}/conectores/exness`); await page.waitForSelector('.page-title h2')
await page.click('text=Agregar cuenta'); await page.locator('label:has-text("Login") input').fill('99999'); await page.locator('label:has-text("Servidor") input').fill('Demo-Server'); await page.locator('label:has-text("Contraseña") input').fill('pw-de-prueba-123')
await page.click('text=Cifrar y guardar en el servidor'); await page.waitForTimeout(1500)
ok('contraseña no queda visible en el DOM tras guardar', !(await page.content()).includes('pw-de-prueba-123'))
const opts = await page.locator('select[aria-label="Cuenta activa"] option').allInnerTexts()
await page.selectOption('select[aria-label="Cuenta activa"]', { label: opts.find(t => t.startsWith('EXNESS')) })
await page.locator('a:has-text("Dashboard")').first().click(); await page.waitForSelector('.kpis'); await page.waitForTimeout(2500)
const ex = await page.locator('main').innerText()
ok('cuenta Exness: aviso no conectado y sin datos de paper', /no hay conexión verificada/.test(ex) && !/\$100\.00/.test(ex))
await page.screenshot({ path: `${OUT}/dashboard-exness.png` })
await page.selectOption('select[aria-label="Cuenta activa"]', { label: opts.find(t => t.includes('Paper')) })
await page.waitForSelector('text=/Caja \d/', { timeout: 20000 }).catch(() => { })
ok('retorno a Binance Paper restituye datos propios', /Caja \d/.test(await page.locator('main').innerText()))

const ls = await page.evaluate(() => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }))
ok('localStorage/sessionStorage sin secretos', !/pw-de-prueba|secret|password/i.test(ls))

await page.setViewportSize({ width: 390, height: 844 }); await page.goto(`${BASE}/dashboard`); await page.waitForSelector('.kpis'); await page.waitForTimeout(2500)
ok('mobile: sin scroll horizontal de página', await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth + 2))
await page.screenshot({ path: `${OUT}/dashboard-mobile.png` })
ok('sin errores de consola/JS', errors.length === 0, errors.slice(0, 3).join(' | '))
await browser.close()
const failed = results.filter(r => !r.pass)
console.log(`\n${results.length - failed.length}/${results.length} comprobaciones OK`)
process.exit(failed.length ? 1 : 0)
