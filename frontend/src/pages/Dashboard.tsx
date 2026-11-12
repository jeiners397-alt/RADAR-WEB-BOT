import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmt } from '../api'
import { Activity, ArrowLeftRight, Brain, CalendarDays, Check, Gauge, ListChecks, Plug, TrendingDown, TrendingUp, Wallet, Zap, Bot } from '../icons'
import { AreaLine, CandleChart, Donut } from '../components/Charts'
import { Card, Chip, CountUp, Empty, Err, Skeleton } from '../components/Common'
import { useApp, usePoll } from '../store'
import { Layers } from 'lucide-react'

const TFS = ['5m', '15m', '1h', '4h', '1d']

function MarketCard({ accountId, saved }: { accountId: number; saved: any }) {
  const [market, setMarket] = useState<string>(saved?.market ?? 'spot')
  const [symbol, setSymbol] = useState<string>(saved?.symbol ?? 'BTCUSDT')
  const [tf, setTf] = useState<string>(saved?.tf ?? '1h')
  const [input, setInput] = useState(symbol)
  const [opts, setOpts] = useState<string[]>([])
  const tick = usePoll(() => api(`/market/ticker?symbol=${symbol}&market=${market}`), [symbol, market], 5000)
  const k = usePoll(() => api(`/market/candles?symbol=${symbol}&interval=${tf}&market=${market}&limit=120`), [symbol, tf, market], 10000)
  useEffect(() => { if (input.length >= 2) api(`/market/instruments?market=${market}&q=${input}&limit=8`).then(r => setOpts(r.items.map((i: any) => i.symbol))).catch(() => setOpts([])) }, [input, market])
  const save = (m: any) => api(`/accounts/${accountId}/settings`, { method: 'PUT', body: { last_market: m } }).catch(() => { })
  const t = tick.data
  return (
    <Card tone="cyan" src={t ? t.source : undefined} title={
      <span className="flex wrap">
        <select aria-label="Mercado" value={market} onChange={e => { setMarket(e.target.value); save({ market: e.target.value, symbol, tf }) }} style={{ width: 'auto', padding: '2px 6px' }}><option value="spot">Spot</option><option value="futures">Futuros</option></select>
        <input list="syms" aria-label="Símbolo" value={input} onChange={e => setInput(e.target.value.toUpperCase())} onKeyDown={e => { if (e.key === 'Enter' && input) { setSymbol(input); save({ market, symbol: input, tf }) } }} onBlur={() => { if (input && input !== symbol) { setSymbol(input); save({ market, symbol: input, tf }) } }} style={{ width: 110, padding: '2px 6px' }} />
        <datalist id="syms">{opts.map(o => <option key={o} value={o} />)}</datalist>
        {t && <><b className="num">{fmt.usd(t.price, t.price < 1 ? 5 : 2)}</b><span className={t.change_pct >= 0 ? 'pos' : 'neg'}>{fmt.pct(t.change_pct)}</span></>}
      </span>
    } right={<span className="tf">{TFS.map(x => <button key={x} className={x === tf ? 'on' : ''} onClick={() => { setTf(x); save({ market, symbol, tf: x }) }}>{x.toUpperCase()}</button>)}</span>}>
      {k.error ? <Err msg={`${symbol}: ${k.error}`} /> : k.loading ? <Skeleton h={190} /> : <CandleChart candles={k.data?.candles ?? []} />}
    </Card>
  )
}

export default function Dashboard() {
  const { account } = useApp()
  const [tab, setTab] = useState<'idx' | 'pnl' | 'dd'>('idx')
  const d = usePoll(() => api(`/dashboard?account_id=${account!.id}`), [account!.id], 8000)
  const eq = usePoll(() => api(`/analytics/equity?account_id=${account!.id}`), [account!.id], 15000)
  if (d.error && !d.data) return <Err msg={d.error} />
  if (!d.data) return <div className="grid kpis">{Array.from({ length: 7 }).map((_, i) => <Skeleton key={i} h={78} />)}</div>
  const s = d.data.summary, u = d.data.universe, job = d.data.research.job, isPaper = account!.environment === 'paper'
  const stateText = job ? ({ running: 'Ejecutando', paused: 'En pausa', done: 'Completada', cancelled: 'Cancelada' } as any)[job.state] : 'Sin investigación'
  const donut = u ? [{ v: u.completed, c: '#19e3a1' }, { v: u.pending + u.running, c: '#3b8cff' }, { v: u.skipped, c: '#d946ef' }, { v: u.failed, c: '#8ba0bd' }] : []
  const pct = (n: number) => u && u.total ? (n / u.total * 100).toFixed(1) : '0.0'
  const R = d.data.regime
  return (
    <>
      {!isPaper && <div className="banner warn">Cuenta <b>{account!.provider.toUpperCase()}</b> ({account!.status.replace(/_/g, ' ')}): no hay conexión verificada, por lo que no se muestran saldos ni operaciones. El mercado público sigue disponible y está etiquetado con su fuente.</div>}
      <div className="grid kpis">
        <Card style={{ padding: 0 }} tone="green"><div className="kpi"><div className="ic"><Wallet color="#19e3a1" /></div><div><small>Capital Virtual</small><div className="v num">$<CountUp value={isPaper ? s.equity : null} /></div><div className="s">{isPaper ? `Caja ${fmt.usd(s.cash)} · ${account!.currency}` : 'No conectado'}</div></div></div></Card>
        <Card style={{ padding: 0 }} tone="green"><div className="kpi"><div className="ic"><TrendingUp color="#19e3a1" /></div><div><small>P&L Acumulado</small><div className={'v num ' + (s.net_pnl >= 0 ? 'pos' : 'neg')}>{isPaper ? <><CountUp value={Math.abs(s.net_pnl)} prefix={s.net_pnl >= 0 ? '+$' : '-$'} /></> : '—'}</div><div className="s">{fmt.pct(s.net_pnl_pct)}</div></div></div></Card>
        <Card style={{ padding: 0 }} tone="green"><div className="kpi"><div className="ic"><CalendarDays color="#19e3a1" /></div><div><small>P&L Mensual</small><div className={'v num ' + (s.month_pnl >= 0 ? 'pos' : 'neg')}>{isPaper ? fmt.signed(s.month_pnl) : '—'}</div><div className="s">{fmt.pct(s.month_pnl_pct)}</div></div></div></Card>
        <Card style={{ padding: 0 }} tone="cyan"><div className="kpi"><div className="ic"><ArrowLeftRight color="#19d3e3" /></div><div><small>Operaciones</small><div className="v num">{isPaper ? s.trades : '—'}</div><div className="s">Win Rate: {s.win_rate == null ? 'N/A' : s.win_rate.toFixed(1) + '%'}</div></div></div></Card>
        <Card style={{ padding: 0 }} tone="violet"><div className="kpi"><div className="ic"><Activity color="#8a63ff" /></div><div><small>Profit Factor</small><div className="v num">{fmt.pf(s.profit_factor)}</div><div className="s">{s.profit_factor == null ? 'Sin pérdidas o sin operaciones' : 'bruto ganado / perdido'}</div></div></div></Card>
        <Card style={{ padding: 0 }} tone="red"><div className="kpi"><div className="ic"><TrendingDown color="#ff4d6a" /></div><div><small>Drawdown Máx.</small><div className="v num neg">{isPaper ? s.max_drawdown_pct.toFixed(1) + '%' : '—'}</div><div className="s">sobre curva de patrimonio</div></div></div></Card>
        <Card style={{ padding: 0 }} tone="violet"><div className="kpi"><div className="ic"><Layers color="#8a63ff" /></div><div><small>Operaciones / Semana</small><div className="v num">{isPaper ? s.trades_per_week : '—'}</div><div className="s">últimos 7 días</div></div></div></Card>
      </div>

      <div className="grid row1">
        <Card tone="green" icon={<TrendingUp size={18} />} title="Evolución del Patrimonio" right={<span className="tabs" role="tablist">{([['idx', 'Índice'], ['pnl', 'P&L'], ['dd', 'Drawdown']] as const).map(([k, l]) => <button key={k} role="tab" aria-selected={tab === k} className={tab === k ? 'on' : ''} onClick={() => setTab(k)}>{l}</button>)}</span>}>
          {eq.data ? <AreaLine points={eq.data.points} mode={tab} initial={eq.data.initial || 100} /> : <Skeleton h={210} />}
        </Card>
        <Card tone="violet" icon={<Brain size={18} />} title={<>Investigación R2.0 <Chip kind="v">{stateText}</Chip></>}>
          {job ? <>
            <div className="flex" style={{ justifyContent: 'space-between' }}><small>Progreso general · {job.name}</small><b className="num">{u.processed_pct}%</b></div>
            <div className="progress" style={{ margin: '6px 0 12px' }}><i style={{ width: u.processed_pct + '%' }} /></div>
            <div className="kv">
              <div><span>Pares solicitados</span><b className="num">{u.total}</b></div>
              <div><span>Pares procesados</span><b className="num">{u.completed}</b></div>
              <div><span>Pares pendientes</span><b className="num">{u.pending + u.running}</b></div>
              <div><span>Omitidos / con error</span><b className="num">{u.skipped} / {u.failed}</b></div>
              <div><span>Último símbolo</span><b>{u.last_symbol ?? '—'}</b></div>
              <div><span>Tiempo transcurrido</span><b className="num">{fmt.dur(d.data.research.elapsed_seconds)}</b></div>
            </div></> : <Empty>No hay investigaciones. <Link to="/investigacion" style={{ color: 'var(--cyan)' }}>Crear una investigación →</Link></Empty>}
        </Card>
        <Card tone="green" icon={<Zap size={18} />} title="Actividad en Tiempo Real" right={<span className="flex"><i className={'dot ' + (d.data.telemetry.workers.length ? 'on pulse' : '')} /> {d.data.telemetry.workers.some((w: any) => w.age_seconds < 60) ? 'LIVE' : 'sin workers'}</span>}>
          {d.data.activity.length ? <div className="act">{d.data.activity.map((a: any, i: number) => <div key={i}><span className="mut num">{fmt.time(a.ts)}</span><Check size={15} color="#19e3a1" /><span>{a.text}</span></div>)}</div> : <Empty>Sin actividad registrada todavía.</Empty>}
        </Card>
      </div>

      <div className="grid row2">
        <MarketCard accountId={account!.id} saved={account!.settings?.last_market} />
        <Card tone="cyan" icon={<Gauge size={18} />} title="Universo de Análisis">
          {u && u.total ? <div className="flex">
            <Donut parts={donut} total={u.total} label="Pares" />
            <div className="kv" style={{ flex: 1 }}>
              <div><span><i className="dot" style={{ background: '#19e3a1' }} />Procesados</span><b className="num">{u.completed} ({pct(u.completed)}%)</b></div>
              <div><span><i className="dot" style={{ background: '#3b8cff' }} />Pendientes</span><b className="num">{u.pending + u.running} ({pct(u.pending + u.running)}%)</b></div>
              <div><span><i className="dot" style={{ background: '#d946ef' }} />Excluidos</span><b className="num">{u.skipped} ({pct(u.skipped)}%)</b></div>
              <div><span><i className="dot" style={{ background: '#8ba0bd' }} />Errores</span><b className="num">{u.failed} ({pct(u.failed)}%)</b></div>
            </div></div> : <Empty>Universo vacío: aún no se ha lanzado una investigación.</Empty>}
        </Card>
        <Card tone="violet" icon={<Activity size={18} />} title="Régimen de Mercado" src="BTCUSDT 1H · Binance público">
          {R ? <>
            <div style={{ textAlign: 'center', margin: '4px 0 12px' }}><span className="chip v" style={{ fontSize: 15, padding: '6px 26px', border: '1px solid var(--violet)' }}>{R.label}</span></div>
            <div className="kv"><div><span>Tendencia BTC</span><b>{R.trend}</b></div><div><span>Volatilidad</span><b>{R.volatility}</b></div><div><span>ATR %</span><b className="num">{R.atr_pct?.toFixed(2) ?? '—'}%</b></div><div><span>Pendiente EMA21/55</span><b className="num">{R.ema_slope_pct?.toFixed(2) ?? '—'}%</b></div></div>
          </> : <Empty>Régimen no disponible (feed sin datos).</Empty>}
        </Card>
        <Card tone="green" icon={<ListChecks size={18} />} title="Próximas Acciones">
          <div className="kv">{d.data.next_actions.map((a: any, i: number) => <div key={i}><span style={{ color: a.done ? 'var(--green)' : undefined }}><input type="checkbox" readOnly checked={a.done} style={{ width: 16 }} />{a.text}</span></div>)}</div>
        </Card>
      </div>

      <div className="grid row3">
        <Card tone="violet" icon={<Layers size={18} />} title={`Estrategias Activas (${d.data.strategies_total})`}>
          <table><thead><tr><th>ID</th><th>Estrategia</th><th className="r">Oper.</th><th className="r">Win Rate</th><th className="r">P&L</th><th className="r">PF</th><th>Estado</th></tr></thead>
            <tbody>{d.data.strategies.map((x: any) => <tr key={x.id}><td>{x.code}</td><td>{x.name}</td><td className="r num">{x.trades}</td><td className="r num">{x.win_rate == null ? 'N/A' : x.win_rate.toFixed(1) + '%'}</td><td className={'r num ' + (x.net_pnl >= 0 ? 'pos' : 'neg')}>{fmt.signed(x.net_pnl)}</td><td className="r num">{fmt.pf(x.profit_factor)}</td><td>{x.enabled ? <Chip kind="g">Activa</Chip> : <Chip>Inactiva</Chip>}</td></tr>)}</tbody></table>
          <Link to="/estrategias" style={{ color: 'var(--cyan)', display: 'block', textAlign: 'right', marginTop: 8 }}>Ver las {d.data.strategies_total} estrategias →</Link>
        </Card>
        <Card tone="cyan" icon={<Plug size={18} />} title="Conectores de Mercado">
          <div className="kv" style={{ gap: 12 }}>{d.data.connectors.map((c: any) => <Link key={c.provider} to={'/conectores/' + c.provider}><div><span><b>{c.label}</b><br /><small className="mut">{c.subtitle}</small></span><span className="flex"><i className={'dot ' + (c.state === 'conectado' ? 'on' : 'off')} />{c.state}{c.latency_ms ? <small className="mut num">{Math.round(c.latency_ms)}ms</small> : null}</span></div></Link>)}</div>
        </Card>
        <Card tone="violet" icon={<Bot size={18} />} title="Bots & Ejecución">
          <div className="kv">
            {d.data.telemetry.workers.length ? d.data.telemetry.workers.map((w: any) => <div key={w.worker_id}><span>{w.worker_id}</span>{w.age_seconds < 60 ? <Chip kind="g">Ejecutando</Chip> : <Chip kind="r">Sin heartbeat</Chip>}</div>) : <Empty>Sin workers reportando.</Empty>}
            <div><span>Auto-trading paper</span>{d.data.bots.paper_auto_enabled ? <Chip kind="a">Habilitado</Chip> : <Chip>En pausa (deshabilitado)</Chip>}</div>
            <div><span>Estrategias habilitadas</span><b className="num">{d.data.bots.strategies_enabled}</b></div>
            <div><span>Trading real</span><Chip kind="r">Bloqueado</Chip></div>
          </div>
        </Card>
        <Card tone="cyan" icon={<CalendarDays size={18} />} title="Resultados Mensuales">
          {d.data.monthly.rows.length ? <table><thead><tr><th>Mes</th><th className="r">Rend.</th><th className="r">Oper.</th></tr></thead><tbody>
            {d.data.monthly.rows.slice(0, 5).map((r: any) => <tr key={r.month}><td>{r.month}</td><td className={'r num ' + (r.pnl >= 0 ? 'pos' : 'neg')}>{fmt.pct(r.return_pct)}</td><td className="r num">{r.trades}</td></tr>)}
            <tr><td><b>Acumulado</b></td><td className={'r num ' + (d.data.monthly.total_pnl >= 0 ? 'pos' : 'neg')}>{fmt.signed(d.data.monthly.total_pnl)} USDT</td><td className="r num"><b>{d.data.monthly.total_trades}</b></td></tr></tbody></table> : <Empty>Aún no hay operaciones cerradas.</Empty>}
        </Card>
      </div>
    </>
  )
}
