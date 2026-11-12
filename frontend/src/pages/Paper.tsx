import { useMemo, useState } from 'react'
import { api, fmt } from '../api'
import { Card, Chip, Empty, Err, PageTitle } from '../components/Common'
import { useApp, usePoll } from '../store'

export default function Paper() {
  const { account, toast } = useApp()
  const aid = account!.id
  const isPaper = account!.environment === 'paper'
  const sum = usePoll(() => api(`/accounts/${aid}/summary`), [aid], 6000)
  const orders = usePoll(() => api(`/paper/orders?account_id=${aid}`), [aid], 8000)
  const trades = usePoll(() => api(`/paper/trades?account_id=${aid}`), [aid], 8000)
  const [t, setT] = useState({ symbol: 'ETHUSDT', side: 'BUY', type: 'market', mode: 'amount' as 'amount' | 'qty', value: '', limit: '', sl: '', tp: '', confirm: false })
  const tick = usePoll(() => api(`/market/ticker?symbol=${t.symbol}`), [t.symbol], 5000)
  const [busy, setBusy] = useState(false)
  const est = useMemo(() => {
    const px = tick.data ? (t.side === 'BUY' ? tick.data.ask : tick.data.bid) : null
    const v = Number(t.value)
    if (!px || !v) return null
    const notional = t.mode === 'amount' ? v : v * px
    return { px, notional, fee: notional * 0.001, qty: t.mode === 'amount' ? v / px : v }
  }, [t, tick.data])
  const submit = async () => {
    setBusy(true)
    try {
      const body: any = { account_id: aid, symbol: t.symbol, side: t.side, type: t.type, confirm: t.confirm, idempotency_key: crypto.randomUUID().slice(0, 30) }  // una clave nueva por cada envío
      if (t.side === 'BUY' || t.value) { if (t.mode === 'amount') body.quote_amount = Number(t.value); else body.quantity = Number(t.value) }
      if (t.type === 'limit') body.limit_price = Number(t.limit)
      if (t.sl) body.stop_loss = Number(t.sl)
      if (t.tp) body.take_profit = Number(t.tp)
      const r = await api('/paper/orders', { method: 'POST', body })
      toast(r.status === 'filled' ? `Ejecutada MANUAL ${r.side} ${r.quantity} ${r.symbol} @ ${r.fill_price.toFixed(4)}` : 'Rechazada: ' + r.reject_reason, r.status === 'filled' ? 'ok' : 'err')
      setT({ ...t, confirm: false }); sum.reload(); orders.reload(); trades.reload()
    } catch (e: any) { toast(e.message, 'err') } finally { setBusy(false) }
  }
  const reset = async () => { if (!confirm('¿Reiniciar el paper a su capital inicial? Se cierran posiciones sin P&L; queda auditado.')) return; try { await api('/paper/reset', { method: 'POST', body: { account_id: aid, confirm: true } }); toast('Paper reiniciado', 'ok'); sum.reload() } catch (e: any) { toast(e.message, 'err') } }
  if (!isPaper) return <><PageTitle title="Paper Trading" /><div className="banner warn">La cuenta activa ({account!.name}) no es una cuenta paper. Selecciona “Binance Paper (USDT)” arriba.</div></>
  const s = sum.data
  return (
    <>
      <PageTitle title="Paper Trading" sub="Spot largo, sin apalancamiento. Precio de referencia: bid/ask públicos de Binance + slippage y comisión configurados." right={<button className="btn ghost sm" onClick={reset}>Reiniciar paper</button>} />
      <Err msg={sum.error} />
      {s && <div className="three" style={{ gridTemplateColumns: 'repeat(5,1fr)', marginBottom: 12 }}>
        {[['Patrimonio', fmt.usd(s.equity)], ['Disponible', fmt.usd(s.cash)], ['Posiciones', fmt.usd(s.positions_value)], ['P&L realizado', fmt.signed(s.realized_pnl)], ['Objetivo algorítmico (5 %)', fmt.usd(s.algo_target_notional, 4)]].map(([k, v]) => <Card key={k}><small className="mut">{k}</small><div className="num" style={{ fontSize: 20, fontWeight: 700 }}>{v}</div></Card>)}
      </div>}
      <div className="two" style={{ gridTemplateColumns: '1fr 1.6fr' }}>
        <Card title={<>Ticket <span className="chip a">MANUAL</span></>} tone="green">
          <div className="form">
            <div className="banner info" style={{ margin: 0 }}>Las órdenes manuales usan <b>la cantidad que tú indiques</b>. El 5 % solo aplica a entradas algorítmicas.</div>
            <div className="two"><label>Símbolo<input value={t.symbol} onChange={e => setT({ ...t, symbol: e.target.value.toUpperCase() })} /></label>
              <label>Mercado<input value="Binance Spot (paper)" disabled /></label></div>
            <div className="seg" role="group"><button className={'buy ' + (t.side === 'BUY' ? 'on' : '')} onClick={() => setT({ ...t, side: 'BUY' })}>Comprar</button><button className={'sell ' + (t.side === 'SELL' ? 'on' : '')} onClick={() => setT({ ...t, side: 'SELL' })}>Vender / cerrar</button></div>
            <div className="two"><label>Tipo<select value={t.type} onChange={e => setT({ ...t, type: e.target.value })}><option value="market">Market</option><option value="limit">Limit (ejecutable ya)</option></select></label>
              {t.type === 'limit' && <label>Precio límite<input type="number" value={t.limit} onChange={e => setT({ ...t, limit: e.target.value })} /></label>}</div>
            <div className="two"><label>Tamaño por<select value={t.mode} onChange={e => setT({ ...t, mode: e.target.value as any })}><option value="amount">Monto (USDT)</option><option value="qty">Cantidad (base)</option></select></label>
              <label>{t.side === 'SELL' ? 'Vacío = cerrar todo' : 'Valor'}<input type="number" value={t.value} onChange={e => setT({ ...t, value: e.target.value })} placeholder={t.side === 'SELL' ? 'todo' : 'ej. 17'} /></label></div>
            {t.side === 'BUY' && <div className="two"><label>Stop loss (opc.)<input type="number" value={t.sl} onChange={e => setT({ ...t, sl: e.target.value })} /></label><label>Take profit (opc.)<input type="number" value={t.tp} onChange={e => setT({ ...t, tp: e.target.value })} /></label></div>}
            <div className="banner info" style={{ margin: 0 }}>
              {tick.data ? <>Precio ref. {t.side === 'BUY' ? 'ask' : 'bid'} <b className="num">{tick.data.ask && (t.side === 'BUY' ? tick.data.ask : tick.data.bid)}</b> · fuente {tick.data.source}</> : 'Sin precio'}
              {est && <><br />Nocional ≈ <b className="num">{est.notional.toFixed(4)}</b> USDT · cantidad ≈ {est.qty.toFixed(6)} · comisión ≈ {est.fee.toFixed(4)}</>}
            </div>
            <label className="flex" style={{ display: 'flex', color: 'var(--txt)' }}><input type="checkbox" style={{ width: 18 }} checked={t.confirm} onChange={e => setT({ ...t, confirm: e.target.checked })} />Confirmo esta orden MANUAL de paper trading</label>
            <button className="btn" disabled={busy || !t.confirm || (t.side === 'BUY' && !t.value)} onClick={submit}>Enviar orden MANUAL</button>
          </div>
        </Card>
        <div className="grid">
          <Card title="Posiciones abiertas" tone="cyan">{s?.open_positions.length ? <div className="scroll-x"><table><thead><tr><th>Símbolo</th><th>Origen</th><th className="r">Cant.</th><th className="r">Precio medio</th><th className="r">Marca</th><th className="r">P&L no real.</th><th className="r">SL/TP</th></tr></thead><tbody>
            {s.open_positions.map((p: any) => <tr key={p.symbol}><td>{p.symbol}</td><td><Chip kind={p.origin === 'MANUAL' ? 'a' : 'v'}>{p.origin}</Chip></td><td className="r num">{p.quantity}</td><td className="r num">{p.avg_price.toFixed(4)}</td><td className="r num">{p.mark.toFixed(4)}</td><td className={'r num ' + (p.unrealized >= 0 ? 'pos' : 'neg')}>{fmt.signed(p.unrealized, 4)}</td><td className="r">{p.stop_loss ?? '—'} / {p.take_profit ?? '—'}</td></tr>)}</tbody></table></div> : <Empty>Sin posiciones abiertas.</Empty>}</Card>
          <Card title="Órdenes" tone="violet"><div className="scroll-x" style={{ maxHeight: 260, overflowY: 'auto' }}>{orders.data?.length ? <table><thead><tr><th>Hora</th><th>Origen</th><th>Símbolo</th><th>Lado</th><th className="r">Cant.</th><th className="r">Precio</th><th className="r">Comisión</th><th>Estado</th></tr></thead><tbody>
            {orders.data.map((o: any) => <tr key={o.id} title={o.reject_reason || o.price_source}><td>{fmt.time(o.ts)}</td><td><Chip kind={o.origin === 'MANUAL' ? 'a' : 'v'}>{o.origin}</Chip></td><td>{o.symbol}</td><td>{o.side}</td><td className="r num">{o.quantity}</td><td className="r num">{o.fill_price?.toFixed(4) ?? '—'}</td><td className="r num">{o.fee.toFixed(4)}</td><td>{o.status === 'filled' ? <Chip kind="g">filled</Chip> : <span title={o.reject_reason}><Chip kind="r">rechazada</Chip> <small className="mut">{o.reject_reason.slice(0, 40)}</small></span>}</td></tr>)}</tbody></table> : <Empty>Sin órdenes.</Empty>}</div></Card>
          <Card title="Historial de operaciones cerradas" tone="green"><div className="scroll-x" style={{ maxHeight: 220, overflowY: 'auto' }}>{trades.data?.length ? <table><thead><tr><th>Cierre</th><th>Origen</th><th>Símbolo</th><th className="r">Entrada</th><th className="r">Salida</th><th className="r">Comisiones</th><th className="r">P&L neto</th></tr></thead><tbody>
            {trades.data.map((x: any) => <tr key={x.id}><td>{fmt.dt(x.closed_at)}</td><td>{x.origin}</td><td>{x.symbol}</td><td className="r num">{x.entry_price.toFixed(4)}</td><td className="r num">{x.exit_price.toFixed(4)}</td><td className="r num">{x.fees.toFixed(4)}</td><td className={'r num ' + (x.pnl >= 0 ? 'pos' : 'neg')}>{fmt.signed(x.pnl, 4)}</td></tr>)}</tbody></table> : <Empty>Aún no hay operaciones cerradas.</Empty>}</div></Card>
        </div>
      </div>
    </>
  )
}
