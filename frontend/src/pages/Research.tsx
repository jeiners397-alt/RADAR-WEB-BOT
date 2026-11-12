import { useState } from 'react'
import { api, fmt } from '../api'
import { Card, Chip, Empty, Err, PageTitle } from '../components/Common'
import { useApp, usePoll } from '../store'

const TFS = ['15m', '1h', '4h', '1d']

export default function Research() {
  const { toast } = useApp()
  const jobs = usePoll(() => api('/research/jobs'), [], 4000)
  const workers = usePoll(() => api('/research/workers'), [], 5000)
  const [sel, setSel] = useState<number | null>(null)
  const detail = usePoll(() => sel ? api('/research/jobs/' + sel) : Promise.resolve(null), [sel], 4000)
  const [f, setF] = useState({ name: 'Investigación R2.0', market: 'spot', quote: 'USDT', max_symbols: 40, tfs: ['1h'] as string[] })
  const [busy, setBusy] = useState(false)
  const create = async () => {
    setBusy(true)
    try { const r = await api('/research/jobs', { method: 'POST', body: { name: f.name, market: f.market, quote: f.quote, max_symbols: f.max_symbols, timeframes: f.tfs } }); toast(`Investigación creada: ${r.tasks} tareas`, 'ok'); setSel(r.id); jobs.reload() }
    catch (e: any) { toast(e.message, 'err') } finally { setBusy(false) }
  }
  const act = async (id: number, a: string) => { try { await api(`/research/jobs/${id}/${a}`, { method: 'POST' }); jobs.reload(); detail.reload() } catch (e: any) { toast(e.message, 'err') } }
  return (
    <>
      <PageTitle title="Investigación R2.0" sub="Descubre el universo del proveedor y analiza símbolos × timeframes con workers concurrentes. Datos públicos de Binance." />
      <div className="two" style={{ gridTemplateColumns: '1fr 1.6fr' }}>
        <div className="grid">
          <Card title="Nueva investigación" tone="violet">
            <div className="form">
              <label>Nombre<input value={f.name} onChange={e => setF({ ...f, name: e.target.value })} /></label>
              <div className="two"><label>Mercado<select value={f.market} onChange={e => setF({ ...f, market: e.target.value })}><option value="spot">Binance Spot</option><option value="futures">Binance Futuros (solo datos)</option></select></label>
                <label>Quote<input value={f.quote} onChange={e => setF({ ...f, quote: e.target.value.toUpperCase() })} /></label></div>
              <label>Máx. símbolos (por volumen 24h) — limitado por recursos del VPS<input type="number" min={1} max={500} value={f.max_symbols} onChange={e => setF({ ...f, max_symbols: Number(e.target.value) })} /></label>
              <div className="flex wrap">Timeframes: {TFS.map(t => <label key={t} className="flex" style={{ display: 'flex' }}><input type="checkbox" style={{ width: 16 }} checked={f.tfs.includes(t)} onChange={e => setF({ ...f, tfs: e.target.checked ? [...f.tfs, t] : f.tfs.filter(x => x !== t) })} />{t}</label>)}</div>
              <button className="btn" disabled={busy || !f.tfs.length} onClick={create}>Crear y encolar</button>
              <small className="mut">Exness y MT5 se podrán investigar cuando exista una pasarela verificada (ver Conectores).</small>
            </div>
          </Card>
          <Card title="Workers" tone="cyan">
            {workers.data?.length ? <table><thead><tr><th>Worker</th><th>Tipo</th><th className="r">Heartbeat</th></tr></thead><tbody>{workers.data.map((w: any) => <tr key={w.worker_id}><td>{w.worker_id}</td><td>{w.kind}</td><td className="r">{w.alive ? <Chip kind="g">hace {Math.round(w.age_seconds)}s</Chip> : <Chip kind="r">caído ({Math.round(w.age_seconds)}s)</Chip>}</td></tr>)}</tbody></table> : <Empty>Ningún worker ha reportado. Inicia el servicio worker-research.</Empty>}
          </Card>
        </div>
        <div className="grid">
          <Card title="Investigaciones" tone="green">
            {jobs.error && <Err msg={jobs.error} />}
            {jobs.data?.length ? <table><thead><tr><th>#</th><th>Nombre</th><th>Estado</th><th className="r">Progreso</th><th className="r">Pend/Corr/Comp/Omit/Fall</th><th></th></tr></thead><tbody>
              {jobs.data.map((j: any) => { const p = j.progress; return <tr key={j.id} onClick={() => setSel(j.id)} style={{ cursor: 'pointer', background: sel === j.id ? 'rgba(25,211,227,.07)' : undefined }}>
                <td>{j.id}</td><td>{j.name}</td><td><Chip kind={j.state === 'running' ? 'g' : j.state === 'paused' ? 'a' : 'm'}>{j.state}</Chip></td>
                <td className="r num">{p.processed_pct}%</td><td className="r num">{p.pending}/{p.running}/{p.completed}/{p.skipped}/{p.failed} = {p.total}</td>
                <td className="r" onClick={e => e.stopPropagation()}>
                  {j.state === 'running' && <button className="btn ghost sm" onClick={() => act(j.id, 'pause')}>Pausar</button>}
                  {j.state === 'paused' && <button className="btn ghost sm" onClick={() => act(j.id, 'resume')}>Reanudar</button>}
                  {p.failed > 0 && <button className="btn ghost sm" onClick={() => act(j.id, 'retry')}>Reintentar</button>}
                  {(j.state === 'running' || j.state === 'paused') && <button className="btn danger sm" onClick={() => act(j.id, 'cancel')}>Cancelar</button>}</td></tr> })}</tbody></table> : <Empty>Sin investigaciones aún.</Empty>}
          </Card>
          {sel && detail.data && <Card title={`Resultados · ${detail.data.name}`} tone="violet" right={<small className="mut">últimos 200 · hipótesis ≠ ventaja demostrada</small>}>
            <div className="scroll-x" style={{ maxHeight: 420, overflowY: 'auto' }}><table><thead><tr><th>Símbolo</th><th>TF</th><th>Estado</th><th className="r">Último</th><th className="r">RSI14</th><th className="r">ATR%</th><th className="r">RVOL</th><th>vs POC</th><th>Régimen</th><th>Calidad</th></tr></thead><tbody>
              {detail.data.results.map((r: any, i: number) => <tr key={i}><td>{r.symbol}</td><td>{r.timeframe}</td><td><Chip kind={r.status === 'completed' ? 'g' : r.status === 'failed' ? 'r' : 'a'}>{r.status}</Chip></td>
                {r.result ? <><td className="r num">{fmt.usd(r.result.last_close, r.result.last_close < 1 ? 5 : 2)}</td><td className="r num">{r.result.rsi14?.toFixed(1) ?? '—'}</td><td className="r num">{r.result.atr_pct?.toFixed(2) ?? '—'}</td><td className="r num">{r.result.rvol20?.toFixed(2) ?? '—'}</td><td>{r.result.above_poc == null ? '—' : r.result.above_poc ? 'sobre' : 'bajo'}</td><td>{r.result.regime}</td><td>{r.result.quality}</td></> : <td colSpan={7} className="mut">{r.error}</td>}</tr>)}</tbody></table></div>
          </Card>}
        </div>
      </div>
    </>
  )
}
