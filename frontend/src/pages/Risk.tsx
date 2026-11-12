import { useEffect, useState } from 'react'
import { api } from '../api'
import { Card, Chip, Empty, PageTitle } from '../components/Common'
import { useApp, usePoll } from '../store'

export default function Risk() {
  const { account, toast } = useApp()
  const aid = account!.id
  const r = usePoll(() => api('/risk/' + aid), [aid], 8000)
  const [f, setF] = useState<any>(null)
  useEffect(() => { if (r.data && !f) setF({ max_open_positions: r.data.max_open_positions, max_total_exposure_pct: r.data.max_total_exposure_pct, max_daily_loss_pct: r.data.max_daily_loss_pct, max_order_notional: r.data.max_order_notional ?? '' }) }, [r.data, f])
  const save = async () => { try { await api('/risk/' + aid, { method: 'PUT', body: { ...f, max_order_notional: f.max_order_notional === '' ? null : Number(f.max_order_notional) } }); toast('Reglas guardadas (validadas en servidor)', 'ok'); r.reload() } catch (e: any) { toast(e.message, 'err') } }
  const kill = async (active: boolean) => { await api(`/risk/${aid}/kill-switch`, { method: 'POST', body: { active } }); toast(active ? 'KILL SWITCH activado' : 'Kill switch desactivado', active ? 'err' : 'ok'); r.reload() }
  const d = r.data
  return (
    <>
      <PageTitle title="Gestión de Riesgo" sub={`Reglas por cuenta: ${account!.name}. Todas se validan en el servidor antes de cada orden.`} />
      {d?.kill_switch && <div className="banner red"><b>KILL SWITCH ACTIVO</b>: toda orden de esta cuenta se rechaza.</div>}
      <div className="two">
        <Card title="Límites" tone="violet">
          {f ? <div className="form">
            <label>Máx. posiciones abiertas<input type="number" value={f.max_open_positions} onChange={e => setF({ ...f, max_open_positions: Number(e.target.value) })} /></label>
            <label>Exposición total máx. (% patrimonio)<input type="number" value={f.max_total_exposure_pct} onChange={e => setF({ ...f, max_total_exposure_pct: Number(e.target.value) })} /></label>
            <label>Pérdida diaria máx. (% patrimonio)<input type="number" value={f.max_daily_loss_pct} onChange={e => setF({ ...f, max_daily_loss_pct: Number(e.target.value) })} /></label>
            <label>Nocional máx. por orden (vacío = sin tope)<input type="number" value={f.max_order_notional} onChange={e => setF({ ...f, max_order_notional: e.target.value })} /></label>
            <button className="btn" onClick={save}>Guardar reglas</button>
            <small className="mut">Apalancamiento: no existe (spot sin margen). La asignación algorítmica del 5 % es independiente de estos límites.</small>
          </div> : <Empty>Cargando…</Empty>}
        </Card>
        <div className="grid">
          <Card title="Exposición y kill switch" tone="red">
            <div className="kv"><div><span>Exposición actual</span><b className="num">{d?.current_exposure_pct == null ? '—' : d.current_exposure_pct.toFixed(1) + '%'}</b></div><div><span>Kill switch</span>{d?.kill_switch ? <Chip kind="r">ACTIVO</Chip> : <Chip kind="g">inactivo</Chip>}</div></div>
            <div className="flex" style={{ marginTop: 12 }}>{d?.kill_switch ? <button className="btn" onClick={() => kill(false)}>Desactivar</button> : <button className="btn danger" onClick={() => kill(true)}>Activar kill switch</button>}</div>
          </Card>
          <Card title="Historial de denegaciones" tone="cyan">
            {d?.denials.length ? <table><thead><tr><th>Origen</th><th>Símbolo</th><th>Motivo</th></tr></thead><tbody>{d.denials.map((o: any) => <tr key={o.id}><td>{o.origin}</td><td>{o.symbol}</td><td className="mut">{o.reject_reason}</td></tr>)}</tbody></table> : <Empty>Sin órdenes rechazadas.</Empty>}
          </Card>
        </div>
      </div>
    </>
  )
}
