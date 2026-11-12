import { useState } from 'react'
import { api, fmt } from '../api'
import { Card, Chip, Empty, Err, PageTitle } from '../components/Common'
import { useApp, usePoll } from '../store'

export default function Strategies() {
  const { account, toast } = useApp()
  const list = usePoll(() => api('/strategies?account_id=' + account!.id), [account!.id], 15000)
  const tpl = usePoll(() => api('/strategies/templates'), [], 0)
  const [edit, setEdit] = useState<any>(null)
  const [params, setParams] = useState<any>({})
  const [nw, setNw] = useState<any>(null)
  const isPaper = account!.environment === 'paper'
  const open = (s: any) => { setEdit(s); setParams({ ...s.params }) }
  const save = async () => { try { await api('/strategies/' + edit.id, { method: 'PUT', body: { params } }); toast('Nueva versión guardada', 'ok'); setEdit(null); list.reload() } catch (e: any) { toast(e.message, 'err') } }
  const toggle = async (s: any) => { try { await api(`/strategies/${s.id}/enable`, { method: 'POST', body: { account_id: account!.id, enabled: !s.enabled } }); list.reload() } catch (e: any) { toast(e.message, 'err') } }
  const create = async () => { try { await api('/strategies', { method: 'POST', body: nw }); setNw(null); list.reload(); toast('Estrategia creada', 'ok') } catch (e: any) { toast(e.message, 'err') } }
  return (
    <>
      <PageTitle title="Estrategias" sub="Plantillas implementadas en el backend (no se ejecuta código arbitrario). Las métricas salen de operaciones cerradas reales de la cuenta activa; sin operaciones = N/A."
        right={<button className="btn" onClick={() => setNw({ code: 'S' + String((list.data?.length ?? 0) + 1).padStart(2, '0'), name: '', template: 'ema_cross', params: {} })}>Nueva estrategia</button>} />
      {!isPaper && <div className="banner warn">La habilitación de estrategias solo existe en cuentas paper. Cambia a “Binance Paper”.</div>}
      <Err msg={list.error} />
      <Card tone="violet">
        {list.data ? <div className="scroll-x"><table><thead><tr><th>ID</th><th>Nombre</th><th>Plantilla</th><th>Versión</th><th>Parámetros</th><th className="r">Oper.</th><th className="r">Win Rate</th><th className="r">P&L</th><th className="r">PF</th><th>Paper</th><th></th></tr></thead><tbody>
          {list.data.map((s: any) => <tr key={s.id}><td>{s.code}</td><td>{s.name}</td><td>{s.template}</td><td>v{s.version}</td><td className="mut">{Object.entries(s.params).map(([k, v]) => `${k}=${v}`).join(', ')}</td>
            <td className="r num">{s.trades}</td><td className="r num">{s.win_rate == null ? 'N/A' : s.win_rate.toFixed(1) + '%'}</td><td className={'r num ' + (s.net_pnl >= 0 ? 'pos' : 'neg')}>{fmt.signed(s.net_pnl)}</td><td className="r num">{fmt.pf(s.profit_factor)}</td>
            <td>{s.enabled ? <Chip kind="g">Habilitada</Chip> : <Chip>Deshabilitada</Chip>}</td>
            <td className="r"><button className="btn ghost sm" onClick={() => open(s)}>Editar</button> <button className="btn ghost sm" disabled={!isPaper} onClick={() => toggle(s)}>{s.enabled ? 'Deshabilitar' : 'Habilitar'}</button></td></tr>)}</tbody></table></div> : <Empty>Cargando…</Empty>}
        <small className="mut">Habilitar no ejecuta nada por sí solo: la automatización paper exige además PAPER_AUTO_TRADING_ENABLED en el servidor y cada orden usa 5 % del patrimonio con los filtros de Binance.</small>
      </Card>
      {edit && <Card title={`Editar ${edit.code} · ${edit.name} (crea la versión v${edit.version + 1})`} tone="cyan" style={{ marginTop: 12 }}>
        <p className="mut">{tpl.data?.[edit.template]?.description}</p>
        <div className="three">{Object.entries(tpl.data?.[edit.template]?.params ?? {}).map(([k, spec]: any) => <label key={k} className="form">{k} ({spec.min}–{spec.max})<input type="number" value={params[k] ?? ''} onChange={e => setParams({ ...params, [k]: Number(e.target.value) })} /></label>)}</div>
        <div className="flex" style={{ marginTop: 10 }}><button className="btn" onClick={save}>Guardar nueva versión</button><button className="btn ghost" onClick={() => setEdit(null)}>Cancelar</button></div>
      </Card>}
      {nw && <Card title="Nueva estrategia" tone="cyan" style={{ marginTop: 12 }}><div className="form three"><label>Código<input value={nw.code} onChange={e => setNw({ ...nw, code: e.target.value })} /></label><label>Nombre<input value={nw.name} onChange={e => setNw({ ...nw, name: e.target.value })} /></label>
        <label>Plantilla<select value={nw.template} onChange={e => setNw({ ...nw, template: e.target.value })}>{Object.entries(tpl.data ?? {}).map(([k, v]: any) => <option key={k} value={k}>{v.label}</option>)}</select></label></div>
        <p className="mut">{tpl.data?.[nw.template]?.description} Se crea con parámetros por defecto; edítalos después.</p>
        <div className="flex"><button className="btn" onClick={create} disabled={!nw.name}>Crear</button><button className="btn ghost" onClick={() => setNw(null)}>Cancelar</button></div></Card>}
    </>
  )
}
