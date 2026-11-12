import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { api, setCsrf } from './api'

export type Account = { id: number; provider: string; environment: string; name: string; currency: string; status: string; initial_balance: number; kill_switch: boolean; settings: any; has_credentials: boolean }
type Ctx = {
  user: { username: string; role: string; flags: any } | null
  loading: boolean
  accounts: Account[]
  account: Account | null
  setAccountId: (id: number) => void
  reloadAccounts: () => Promise<void>
  login: (u: string, p: string) => Promise<void>
  logout: () => Promise<void>
  toast: (text: string, kind?: 'ok' | 'err' | 'info') => void
  toasts: { id: number; text: string; kind: string }[]
  live: boolean
}
const C = createContext<Ctx>(null as any)
export const useApp = () => useContext(C)

export function AppProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<Ctx['user']>(null)
  const [loading, setLoading] = useState(true)
  const [accounts, setAccounts] = useState<Account[]>([])
  const [accountId, setAid] = useState<number | null>(null)
  const [toasts, setToasts] = useState<Ctx['toasts']>([])
  const [live, setLive] = useState(false)
  const tid = useRef(0)

  const toast = useCallback((text: string, kind: 'ok' | 'err' | 'info' = 'info') => {
    const id = ++tid.current
    setToasts(t => [...t, { id, text, kind }])
    setTimeout(() => setToasts(t => t.filter(x => x.id !== id)), 4500)
  }, [])

  const reloadAccounts = useCallback(async () => {
    const a: Account[] = await api('/accounts')
    setAccounts(a)
    setAid(cur => (cur && a.find(x => x.id === cur)) ? cur : (a.find(x => x.environment === 'paper') ?? a[0])?.id ?? null)
  }, [])

  const boot = useCallback(async () => {
    try {
      const me = await api('/auth/me')
      setCsrf(me.csrf); setUser({ username: me.username, role: me.role, flags: me.flags })
      await reloadAccounts()
    } catch { setUser(null) } finally { setLoading(false) }
  }, [reloadAccounts])

  useEffect(() => { boot() }, [boot])
  useEffect(() => {
    const h = () => { setUser(null); setAccounts([]) }
    window.addEventListener('crp-unauth', h)
    return () => window.removeEventListener('crp-unauth', h)
  }, [])

  // WebSocket por cuenta: se cierra y reabre al cambiar de cuenta (cancela stream anterior).
  useEffect(() => {
    if (!user || !accountId) return
    let ws: WebSocket | null = null, stop = false, last = 0, retry = 1000
    const timer = setInterval(() => setLive(Date.now() - last < 15000), 2000)
    const open = () => {
      if (stop) return
      ws = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/api/v1/ws?account_id=${accountId}`)
      ws.onmessage = () => { last = Date.now(); setLive(true); retry = 1000 }
      ws.onclose = () => { setLive(false); if (!stop) setTimeout(open, retry = Math.min(retry * 2, 15000)) }
    }
    open()
    return () => { stop = true; clearInterval(timer); ws?.close(); setLive(false) }
  }, [user, accountId])

  const login = async (username: string, password: string) => {
    const r = await api('/auth/login', { method: 'POST', body: { username, password } })
    setCsrf(r.csrf)
    await boot()
  }
  const logout = async () => { try { await api('/auth/logout', { method: 'POST' }) } finally { setUser(null); setAccounts([]); setAid(null) } }

  const value = useMemo<Ctx>(() => ({
    user, loading, accounts, account: accounts.find(a => a.id === accountId) ?? null, setAccountId: setAid,
    reloadAccounts, login, logout, toast, toasts, live,
  }), [user, loading, accounts, accountId, toasts, live, reloadAccounts, toast]) // eslint-disable-line
  return <C.Provider value={value}>{children}</C.Provider>
}

export function usePoll<T>(fn: () => Promise<T>, deps: any[], ms = 10000) {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)
  const seq = useRef(0)
  const reload = useCallback(async () => {
    const my = ++seq.current
    try { const d = await fn(); if (my === seq.current) { setData(d); setError(null) } }
    catch (e: any) { if (my === seq.current) setError(e.message ?? 'Error') }
    finally { if (my === seq.current) setLoading(false) }
  }, deps) // eslint-disable-line
  useEffect(() => { setData(null); setLoading(true); reload(); if (!ms) return; const t = setInterval(reload, ms); return () => { seq.current++; clearInterval(t) } }, [reload, ms])
  return { data, error, loading, reload }
}
