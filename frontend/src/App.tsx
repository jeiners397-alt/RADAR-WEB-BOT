import { useEffect, useState, type FormEvent } from 'react'
import { Link, NavLink, Navigate, Route, Routes, useLocation, useNavigate } from 'react-router-dom'
import { Bell, Bot, ChevronRight, Cpu, FlaskConical, HardDrive, Home, LayersIcon, LineChart, Link2, Menu, MemoryStick, PlayCircle, RefreshCw, Radio, Settings, ShieldCheck, FileText, Search, Store, User } from './icons'
import { fmt, api } from './api'
import { Logo, Card, Err } from './components/Common'
import { useApp, usePoll } from './store'
import Dashboard from './pages/Dashboard'
import Research from './pages/Research'
import Strategies from './pages/Strategies'
import Backtesting from './pages/Backtesting'
import Paper from './pages/Paper'
import Live from './pages/Live'
import Bots from './pages/Bots'
import Markets from './pages/Markets'
import Connectors from './pages/Connectors'
import Risk from './pages/Risk'
import Reports from './pages/Reports'
import SettingsPage from './pages/Settings'

function Login() {
  const { login } = useApp()
  const [u, setU] = useState('admin'), [p, setP] = useState(''), [err, setErr] = useState<string | null>(null), [busy, setBusy] = useState(false)
  const submit = async (e: FormEvent) => {
    e.preventDefault(); setBusy(true); setErr(null)
    try { await login(u, p) } catch (x: any) { setErr(x.message) } finally { setBusy(false) }
  }
  return (
    <div className="login">
      <form className="card c-green form" onSubmit={submit} aria-label="Inicio de sesión">
        <div className="flex"><Logo size={46} /><div><h1>CAPITAL <span style={{ color: 'var(--cyan)' }}>RADAR PRO</span></h1></div></div>
        <p>Laboratorio de Trading Algorítmico · acceso privado</p>
        <label>Usuario<input value={u} onChange={e => setU(e.target.value)} autoComplete="username" required /></label>
        <label>Contraseña<input type="password" value={p} onChange={e => setP(e.target.value)} autoComplete="current-password" required autoFocus /></label>
        <Err msg={err} />
        <button className="btn" disabled={busy}>{busy ? 'Verificando…' : 'Ingresar'}</button>
        <small className="mut">Paper Trading únicamente. Las operaciones reales están deshabilitadas.</small>
      </form>
    </div>
  )
}

const NAV = [
  { to: '/dashboard', label: 'Dashboard', icon: Home },
  { to: '/investigacion', label: 'Investigación (R2.0)', icon: FlaskConical },
  { to: '/estrategias', label: 'Estrategias', icon: LayersIcon },
  { to: '/backtesting', label: 'Backtesting', icon: LineChart },
  { to: '/paper', label: 'Paper Trading', icon: PlayCircle },
  { to: '/live', label: 'Trading en Vivo', icon: Radio, tag: 'OFF' },
  { to: '/bots', label: 'Bots & Automatización', icon: Bot },
  { to: '/mercados', label: 'Mercados', icon: Store },
]
const NAV2 = [
  { to: '/riesgo', label: 'Gestión de Riesgo', icon: ShieldCheck },
  { to: '/informes', label: 'Informes & Auditoría', icon: FileText },
  { to: '/configuracion', label: 'Configuración', icon: Settings },
]

function Sidebar({ open, close }: { open: boolean; close: () => void }) {
  const loc = useLocation()
  const [conn, setConn] = useState(loc.pathname.startsWith('/conectores'))
  const tel = usePoll(() => api('/telemetry/latest'), [], 15000)
  const s = tel.data?.server
  const Meter = ({ icon, label, v }: { icon: any; label: string; v?: number }) => (
    <div className="meter">{icon}<div className="row"><span>{label}</span><span className="num">{v == null ? '—' : Math.round(v) + '%'}</span></div><div className="bar"><i style={{ width: (v ?? 0) + '%' }} /></div></div>
  )
  return (
    <aside className={'sidebar' + (open ? ' open' : '')} aria-label="Navegación principal" onClick={close}>
      {NAV.map(n => <NavLink key={n.to} to={n.to} className={({ isActive }) => 'nav' + (isActive ? ' active' : '')}><n.icon size={19} />{n.label}{n.tag && <span className="tag">{n.tag}</span>}</NavLink>)}
      <div className="nav" role="button" tabIndex={0} onClick={e => { e.stopPropagation(); setConn(!conn) }} onKeyDown={e => e.key === 'Enter' && setConn(!conn)}><Link2 size={19} />Conectores<ChevronRight size={16} className={'chev' + (conn ? ' open' : '')} /></div>
      {conn && [['binance', 'Binance'], ['exness', 'Exness'], ['mt5', 'MetaTrader 5']].map(([k, l]) => <NavLink key={k} to={'/conectores/' + k} className={({ isActive }) => 'nav sub' + (isActive ? ' active' : '')}>{l}</NavLink>)}
      {NAV2.map(n => <NavLink key={n.to} to={n.to} className={({ isActive }) => 'nav' + (isActive ? ' active' : '')}><n.icon size={19} />{n.label}</NavLink>)}
      <div className="meters">
        <Meter icon={<Cpu size={16} />} label="CPU" v={s?.cpu} /><Meter icon={<MemoryStick size={16} />} label="RAM" v={s?.ram} /><Meter icon={<HardDrive size={16} />} label="DISCO" v={s?.disk} />
        {!s && <small className="mut">Sin telemetría: el worker de mercado no ha reportado.</small>}
      </div>
    </aside>
  )
}

function CommandPalette({ onClose }: { onClose: () => void }) {
  const nav = useNavigate()
  const [q, setQ] = useState('')
  const [sym, setSym] = useState<any[]>([])
  const routes = [...NAV, ...NAV2].map(n => ({ label: n.label, to: n.to })).concat(['binance', 'exness', 'mt5'].map(k => ({ label: 'Conector ' + k, to: '/conectores/' + k })))
  useEffect(() => { if (q.length >= 2) api(`/market/instruments?q=${encodeURIComponent(q)}&quote=USDT&limit=6`).then(r => setSym(r.items)).catch(() => setSym([])); else setSym([]) }, [q])
  const hits = routes.filter(r => r.label.toLowerCase().includes(q.toLowerCase())).slice(0, 6)
  const go = (to: string) => { nav(to); onClose() }
  return (
    <div className="cmdk" onClick={onClose} role="dialog" aria-label="Paleta de comandos">
      <div className="box" onClick={e => e.stopPropagation()}>
        <input autoFocus placeholder="Buscar sección o símbolo (ej. BTCUSDT)…" value={q} onChange={e => setQ(e.target.value)} onKeyDown={e => { if (e.key === 'Escape') onClose(); if (e.key === 'Enter') { if (hits[0]) go(hits[0].to); else if (sym[0]) go('/mercados?symbol=' + sym[0].symbol) } }} />
        {hits.map(h => <div key={h.to} className="it" onClick={() => go(h.to)}>↳ {h.label}</div>)}
        {sym.map(s => <div key={s.symbol} className="it" onClick={() => go('/mercados?symbol=' + s.symbol)}><Search size={14} /> {s.symbol} <span className="mut">Binance spot</span></div>)}
      </div>
    </div>
  )
}

function Header({ onMenu }: { onMenu: () => void }) {
  const { user, accounts, account, setAccountId, logout, live } = useApp()
  const health = usePoll(() => api('/providers'), [], 20000)
  const [now, setNow] = useState(new Date())
  const notes = usePoll(() => api('/notifications'), [], 30000)
  useEffect(() => { const t = setInterval(() => setNow(new Date()), 1000); return () => clearInterval(t) }, [])
  const feed = health.data?.[0]?.health?.ok
  const state = health.data == null ? 'Verificando…' : feed ? (live ? 'EN LÍNEA' : 'ONLINE (sin stream)') : 'FEED CAÍDO'
  const unread = (notes.data ?? []).filter((n: any) => !n.read).length
  return (
    <header className="header">
      <button className="iconbtn menu-btn" onClick={onMenu} aria-label="Menú"><Menu size={18} /></button>
      <Link to="/dashboard" className="brand"><Logo /><div><b>CAPITAL<br /><span>RADAR PRO</span><small>v1.0</small></b></div></Link>
      <div className="head-title"><h1>Laboratorio de Trading Algorítmico</h1><p>Investigación · Backtesting · Paper Trading · Trading en Vivo</p></div>
      <select className="acc-select" aria-label="Cuenta activa" value={account?.id ?? ''} onChange={e => setAccountId(Number(e.target.value))}>
        {accounts.map(a => <option key={a.id} value={a.id}>{a.provider.toUpperCase()} · {a.name} [{a.environment}]</option>)}
      </select>
      <div className="pill hide-m"><small>Estado del Sistema</small><span><i className={'dot ' + (feed ? 'on' : health.data ? 'off' : '') + (live ? ' pulse' : '')} />{state}</span></div>
      <div className="pill hide-m" style={{ minWidth: 210 }}><small>Última actualización</small><span className="num">{now.toLocaleString('es-PE', { timeZone: 'America/Lima', hour12: false, day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit', second: '2-digit' })} (PET)<RefreshCw size={14} onClick={() => { health.reload(); notes.reload() }} style={{ cursor: 'pointer' }} /></span></div>
      <button className="iconbtn" aria-label="Notificaciones" title={unread ? `${unread} sin leer` : 'Sin notificaciones'}><Bell size={18} />{unread > 0 && <span className="badge">{unread}</span>}</button>
      <div className="user"><div className="avatar"><User size={20} /></div><div><b>{user?.username}</b><br /><small className="mut">{user?.role === 'admin' ? 'Administrador' : user?.role}</small></div></div>
      <button className="btn ghost sm" onClick={logout}>Salir</button>
    </header>
  )
}

export default function App() {
  const { user, loading, account, toasts } = useApp()
  const [menu, setMenu] = useState(false)
  const [cmd, setCmd] = useState(false)
  useEffect(() => {
    const h = (e: KeyboardEvent) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); setCmd(v => !v) } }
    window.addEventListener('keydown', h); return () => window.removeEventListener('keydown', h)
  }, [])
  if (loading) return <div className="login"><Logo size={60} /></div>
  if (!user) return <Login />
  return (
    <div className="app">
      <Header onMenu={() => setMenu(!menu)} />
      <Sidebar open={menu} close={() => setMenu(false)} />
      <main className="content" key={account?.id /* cambiar de cuenta remonta TODAS las vistas: se descartan datos y streams previos */}>
        {!account ? <Card><Err msg="No hay cuentas. Ejecuta el asistente de primer inicio en el servidor." /></Card> :
          <Routes>
            <Route path="/" element={<Navigate to="/dashboard" replace />} />
            <Route path="/dashboard" element={<Dashboard />} />
            <Route path="/investigacion" element={<Research />} />
            <Route path="/estrategias" element={<Strategies />} />
            <Route path="/backtesting" element={<Backtesting />} />
            <Route path="/paper" element={<Paper />} />
            <Route path="/live" element={<Live />} />
            <Route path="/bots" element={<Bots />} />
            <Route path="/mercados" element={<Markets />} />
            <Route path="/conectores/:provider" element={<Connectors />} />
            <Route path="/riesgo" element={<Risk />} />
            <Route path="/informes" element={<Reports />} />
            <Route path="/configuracion" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/dashboard" replace />} />
          </Routes>}
      </main>
      <div className="toasts" aria-live="polite">{toasts.map(t => <div key={t.id} className={'toast ' + t.kind}>{t.text}</div>)}</div>
      {cmd && <CommandPalette onClose={() => setCmd(false)} />}
    </div>
  )
}
export { fmt }
