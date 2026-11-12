import { useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '../api'
import { Card, Chip, Empty, PageTitle } from '../components/Common'
import { useApp, usePoll } from '../store'

const LABEL: Record<string, string> = { binance: 'Binance', exness: 'Exness', mt5: 'MetaTrader 5' }

export default function Connectors() {
  const { provider = 'binance' } = useParams()
  const { accounts, reloadAccounts, setAccountId, toast } = useApp()
  const prov = usePoll(() => api('/providers'), [], 20000)
  const info = prov.data?.find((p: any) => p.provider === provider)
  const mine = accounts.filter(a => a.provider === provider)
  const [show, setShow] = useState(false)
  const [f, setF] = useState<any>({ name: '', environment: 'demo', api_key: '', api_secret: '', login: '', server: '', platform: 'MT5', password: '' })
  const [busy, setBusy] = useState(false)
  const [res, setRes] = useState<any>(null)

  const add = async () => {
    setBusy(true)
    try {
      const body: any = { provider, name: f.name || `${LABEL[provider]} ${f.environment}`, environment: provider === 'binance' ? 'private-readonly' : f.environment }
      if (provider === 'binance') { body.api_key = f.api_key; body.api_secret = f.api_secret } else { body.login = f.login; body.server = f.server; body.platform = f.platform; body.password = f.password }
      const r = await api('/accounts', { method: 'POST', body })
      setRes(r.credential)
      setF({ ...f, api_key: '', api_secret: '', password: '' }) // se borra del estado del navegador de inmediato
      await reloadAccounts(); toast('Credencial cifrada en el servidor. Trading deshabilitado.', 'ok')
    } catch (e: any) { toast(e.message, 'err') } finally { setBusy(false) }
  }
  const test = async (id: number) => { const r = await api(`/accounts/${id}/test`, { method: 'POST' }); toast((r.ok ? 'OK: ' : 'No verificado: ') + (typeof r.detail === 'string' ? r.detail : r.status ?? JSON.stringify(r.detail)), r.ok ? 'ok' : 'err') }
  const del = async (id: number) => { if (!confirm('¿Eliminar cuenta y borrar su credencial cifrada?')) return; await api('/accounts/' + id, { method: 'DELETE' }); await reloadAccounts(); toast('Cuenta y credencial eliminadas', 'ok') }

  const caps = info?.capabilities
  return (
    <>
      <PageTitle title={`Conector · ${LABEL[provider]}`} sub="Cada cuenta tiene balance, órdenes, métricas y límites independientes." />
      {caps && <Card tone={info.health.ok ? 'green' : 'red'} title="Estado del conector" right={info.health.ok ? <Chip kind="g">conectado</Chip> : <Chip kind="r">no conectado</Chip>} style={{ marginBottom: 12 }}>
        <div className="kv"><div><span>Datos públicos de mercado</span><b>{caps.public_market_data ? 'Sí' : 'No'}</b></div><div><span>Cuenta privada</span><b>{caps.private_account ? 'Sí' : 'No'}</b></div><div><span>Trading</span><b className="neg">Deshabilitado</b></div>{caps.status && <div><span>Estado</span><b className="amber">{caps.status}</b></div>}{info.health.latency_ms && <div><span>Latencia</span><b className="num">{info.health.latency_ms} ms</b></div>}</div>
        <p className="mut" style={{ marginBottom: 0 }}>{caps.notes}</p>
      </Card>}
      <div className="two">
        <Card title="Cuentas" tone="cyan" right={<button className="btn sm" onClick={() => setShow(!show)}>{provider === 'binance' ? 'Agregar cuenta privada' : 'Agregar cuenta'}</button>}>
          {mine.length ? <table><thead><tr><th>Nombre</th><th>Entorno</th><th>Estado</th><th></th></tr></thead><tbody>{mine.map(a => <tr key={a.id}><td>{a.name}</td><td><Chip kind={a.environment === 'paper' ? 'a' : a.environment === 'public' ? 'g' : 'm'}>{a.environment}</Chip></td><td>{a.status.replace(/_/g, ' ')}</td><td className="r"><button className="btn ghost sm" onClick={() => setAccountId(a.id)}>Activar</button> <button className="btn ghost sm" onClick={() => test(a.id)}>Probar</button>{a.has_credentials && <> <button className="btn danger sm" onClick={() => del(a.id)}>Borrar</button></>}</td></tr>)}</tbody></table> : <Empty>Sin cuentas de {LABEL[provider]}.</Empty>}
          <small className="mut">Binance Público/Research no requiere claves. Binance Paper es interno (100 USDT) y no es una cuenta de Binance.</small>
        </Card>
        {show && <Card title="Credencial segura" tone="violet">
          <div className="banner warn">Se envía por HTTPS al backend, se cifra antes de guardarse y <b>nunca</b> vuelve a mostrarse. Guardar la clave <b>no habilita trading</b>. Usa permisos de solo lectura y whitelisting de IP.</div>
          {provider !== 'binance' && <div className="banner info">{caps?.notes} Puedes guardar los datos ahora; la cuenta quedará “no conectada” hasta que exista una pasarela verificada.</div>}
          <form className="form" onSubmit={e => { e.preventDefault(); add() }} autoComplete="off">
            <label>Nombre<input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} placeholder="Mi cuenta" /></label>
            {provider === 'binance' ? <>
              <label>API Key<input value={f.api_key} onChange={e => setF({ ...f, api_key: e.target.value })} autoComplete="off" spellCheck={false} required /></label>
              <label>Secret Key<input type="password" value={f.api_secret} onChange={e => setF({ ...f, api_secret: e.target.value })} autoComplete="new-password" required /></label></> : <>
              <div className="two"><label>Entorno<select value={f.environment} onChange={e => setF({ ...f, environment: e.target.value })}><option value="demo">Demo</option><option value="live">Real (solo lectura futura)</option></select></label><label>Plataforma<select value={f.platform} onChange={e => setF({ ...f, platform: e.target.value })}><option>MT5</option><option>MT4</option></select></label></div>
              <div className="two"><label>Login<input value={f.login} onChange={e => setF({ ...f, login: e.target.value })} required /></label><label>Servidor<input value={f.server} onChange={e => setF({ ...f, server: e.target.value })} required /></label></div>
              <label>Contraseña<input type="password" value={f.password} onChange={e => setF({ ...f, password: e.target.value })} autoComplete="new-password" required /></label></>}
            <button className="btn" disabled={busy}>Cifrar y guardar en el servidor</button>
          </form>
          {res && <p className="pos">Guardada · huella <code>{res.fingerprint}</code> · {res.masked} · trading_enabled=false</p>}
        </Card>}
      </div>
    </>
  )
}
