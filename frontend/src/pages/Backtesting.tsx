import { useState } from 'react'
import { api, fmt } from '../api'
import { Card, Chip, Empty, Err, PageTitle } from '../components/Common'
import { useApp, usePoll } from '../store'

function Curve({ eq }: { eq: number[] }) {
  if (!eq?.length) return null
  const W = 640, H = 160, mn = Math.min(...eq), mx = Math.max(...eq) || 1
  const d = eq.map((v, i) => `${i ? 'L' : 'M'}${(i / (eq.length - 1) * W).toFixed(1)},${(H - (v - mn) / ((mx - mn) || 1) * (H - 10) - 5).toFixed(1)}`).join(' ')
  return <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H}><path d={d} fill="none" stroke="#19e3a1" strokeWidth="2" /></svg>
}

const M = ({ m, t }: { m: any; t: string }) => <div><small className="mut">{t}</small><div className="num" style={{ fontWeight: 700 }}>{m.trades} ops · {fmt.signed(m.net_pnl)} · WR {m.win_rate == null ? 'N/A' : m.win_rate.toFixed(1) + '%'} · PF {fmt.pf(m.profit_factor)} · DD {m.max_drawdown_pct.toFixed(1)}%</div></div>

export default function Backtesting() {
  const { toast } = useApp()
  const strategies = usePoll(() => api('/strategies'), [], 0)
  const runs = usePoll(() => api('/backtests'), [], 4000)
  const [sel, setSel] = useState<number | null>(null)
  const detail = usePoll(() => sel ? api('/backtests/' + sel) : Promise.resolve(null), [sel], 3000)
  const [f, setF] = useState({ strategy_id: 0, symbol: 'BTCUSDT', interval: '1h', candles: 1500, initial: 100, fee_rate: 0.001, slippage_bps: 5, allocation_fraction: 0.05, oos_fraction: 0.3 })
  const run = async () => {
    try { const r = await api('/backtests', { method: 'POST', body: { ...f, strategy_id: f.strategy_id || strategies.data[0].id } }); toast('Backtest encolado', 'ok'); setSel(r.id); runs.reload() } catch (e: any) { toast(e.message, 'err') }
  }
  const res = detail.data?.result
  return (
    <>
      <PageTitle title="Backtesting" sub="Determinista y reproducible: señal al cierre de la vela i, ejecución en la apertura de i+1, con comisiones y slippage; sin lookahead; tramo OOS reservado; comparación con buy & hold." />
      <div className="two" style={{ gridTemplateColumns: '1fr 1.7fr' }}>
        <div className="grid">
          <Card title="Experimento" tone="violet"><div className="form">
            <label>Estrategia<select value={f.strategy_id} onChange={e => setF({ ...f, strategy_id: Number(e.target.value) })}>{strategies.data?.map((s: any) => <option key={s.id} value={s.id}>{s.code} · {s.name} v{s.version}</option>)}</select></label>
            <div className="two"><label>Símbolo<input value={f.symbol} onChange={e => setF({ ...f, symbol: e.target.value.toUpperCase() })} /></label>
              <label>Timeframe<select value={f.interval} onChange={e => setF({ ...f, interval: e.target.value })}>{['5m', '15m', '1h', '4h', '1d'].map(x => <option key={x}>{x}</option>)}</select></label></div>
            <div className="two"><label>Velas (100–5000)<input type="number" value={f.candles} onChange={e => setF({ ...f, candles: Number(e.target.value) })} /></label><label>Capital inicial<input type="number" value={f.initial} onChange={e => setF({ ...f, initial: Number(e.target.value) })} /></label></div>
            <div className="two"><label>Comisión (fracción)<input type="number" step="0.0001" value={f.fee_rate} onChange={e => setF({ ...f, fee_rate: Number(e.target.value) })} /></label><label>Slippage (bps)<input type="number" value={f.slippage_bps} onChange={e => setF({ ...f, slippage_bps: Number(e.target.value) })} /></label></div>
            <div className="two"><label>Asignación por entrada<input type="number" step="0.01" value={f.allocation_fraction} onChange={e => setF({ ...f, allocation_fraction: Number(e.target.value) })} /></label><label>Fracción OOS<input type="number" step="0.05" value={f.oos_fraction} onChange={e => setF({ ...f, oos_fraction: Number(e.target.value) })} /></label></div>
            <button className="btn" onClick={run}>Ejecutar backtest</button></div></Card>
          <Card title="Historial" tone="cyan">
            {runs.data?.length ? <table><thead><tr><th>#</th><th>Estado</th><th>Símbolo</th><th className="r">Net</th></tr></thead><tbody>{runs.data.map((r: any) => <tr key={r.id} style={{ cursor: 'pointer' }} onClick={() => setSel(r.id)}><td>{r.id}</td><td><Chip kind={r.status === 'done' ? 'g' : r.status === 'failed' ? 'r' : 'a'}>{r.status}</Chip></td><td>{r.config.symbol} {r.config.interval}</td><td className="r num">{r.summary ? fmt.signed(r.summary.net_pnl) : '—'}</td></tr>)}</tbody></table> : <Empty>Sin backtests.</Empty>}
          </Card>
        </div>
        <Card title={sel ? `Resultado #${sel}` : 'Resultado'} tone="green">
          {!sel && <Empty>Selecciona o ejecuta un backtest.</Empty>}
          {detail.data?.status === 'failed' && <Err msg={detail.data.error} />}
          {detail.data && ['queued', 'running'].includes(detail.data.status) && <Empty>En cola/ejecutando… (lo procesa el worker de mercado)</Empty>}
          {res && <div className="form">
            {res.warnings.map((w: string) => <div key={w} className="banner warn">{w}</div>)}
            <M m={res.metrics} t="Total (neto de costes)" /><M m={res.in_sample} t="In-sample" /><M m={res.out_of_sample} t={`Out-of-sample (desde vela ${res.oos_start_index})`} />
            <div className="banner info">Buy & hold 100%: <b>{fmt.pct(res.benchmark.buy_hold_full_return_pct)}</b> (DD {res.benchmark.max_drawdown_pct.toFixed(1)}%) · mismo tamaño que la estrategia: {fmt.pct(res.benchmark.buy_hold_alloc_return_pct)}. Estrategia: <b>{fmt.pct(res.metrics.return_pct)}</b></div>
            <Curve eq={res.equity} />
            <small className="mut">Reproducibilidad · motor {res.engine} · dataset sha256 <code>{res.dataset.hash.slice(0, 16)}…</code> · {res.dataset.candles} velas · params {JSON.stringify(res.params)}</small>
            <div className="scroll-x" style={{ maxHeight: 220, overflowY: 'auto' }}><table><thead><tr><th>Entrada</th><th>Salida</th><th className="r">Px ent.</th><th className="r">Px sal.</th><th className="r">P&L</th></tr></thead><tbody>{res.trades.map((t: any, i: number) => <tr key={i}><td>{new Date(t.entry_t).toLocaleString('es-PE')}</td><td>{new Date(t.exit_t).toLocaleString('es-PE')}</td><td className="r num">{t.entry.toFixed(4)}</td><td className="r num">{t.exit.toFixed(4)}</td><td className={'r num ' + (t.pnl >= 0 ? 'pos' : 'neg')}>{fmt.signed(t.pnl, 4)}</td></tr>)}</tbody></table></div>
          </div>}
        </Card>
      </div>
    </>
  )
}
