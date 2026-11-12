import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { api, fmt } from '../api'
import { CandleChart } from '../components/Charts'
import { Card, Empty, Err, PageTitle, Skeleton } from '../components/Common'
import { useApp, usePoll } from '../store'

export default function Markets() {
  const { account } = useApp()
  const [sp, setSp] = useSearchParams()
  const [market, setMarket] = useState('spot')
  const [sort, setSort] = useState('volume')
  const [q, setQ] = useState('')
  const [symbol, setSymbol] = useState(sp.get('symbol') ?? account!.settings?.last_market?.symbol ?? 'BTCUSDT')
  const [tf, setTf] = useState('1h')
  const [favs, setFavs] = useState<string[]>(account!.settings?.favorites ?? [])
  const list = usePoll(() => api(`/market/tickers?market=${market}&sort=${sort}&limit=200`), [market, sort], 15000)
  const k = usePoll(() => api(`/market/candles?symbol=${symbol}&interval=${tf}&market=${market}&limit=300`), [symbol, tf, market], 10000)
  const ind = usePoll(() => api(`/market/indicators?symbol=${symbol}&interval=${tf}&market=${market}`), [symbol, tf, market], 30000)
  useEffect(() => { const s = sp.get('symbol'); if (s) setSymbol(s) }, [sp])
  const toggleFav = (s: string) => { const n = favs.includes(s) ? favs.filter(x => x !== s) : [...favs, s]; setFavs(n); api(`/accounts/${account!.id}/settings`, { method: 'PUT', body: { favorites: n } }).catch(() => { }) }
  const rows = (list.data?.items ?? []).filter((r: any) => r.symbol.includes(q.toUpperCase())).sort((a: any, b: any) => Number(favs.includes(b.symbol)) - Number(favs.includes(a.symbol)))
  const i = ind.data
  return (
    <>
      <PageTitle title="Mercados" sub="Catálogo público de Binance. Exness y MT5 aparecerán aquí cuando exista una pasarela verificada." />
      <div className="two" style={{ gridTemplateColumns: '1fr 1.5fr' }}>
        <Card title="Instrumentos" tone="cyan" right={<span className="flex"><select value={market} onChange={e => setMarket(e.target.value)} style={{ width: 'auto' }}><option value="spot">Spot</option><option value="futures">Futuros</option></select><select value={sort} onChange={e => setSort(e.target.value)} style={{ width: 'auto' }}><option value="volume">Volumen</option><option value="change">Cambio 24h</option></select></span>} src={list.data?.source}>
          <input placeholder="Buscar símbolo…" value={q} onChange={e => setQ(e.target.value)} aria-label="Buscar símbolo" />
          <Err msg={list.error} />
          <div style={{ maxHeight: 560, overflowY: 'auto', marginTop: 8 }}>{list.loading ? <Skeleton h={300} /> : <table><thead><tr><th></th><th>Símbolo</th><th className="r">Precio</th><th className="r">24h</th><th className="r">Vol. USDT</th></tr></thead><tbody>
            {rows.map((r: any) => <tr key={r.symbol} onClick={() => { setSymbol(r.symbol); setSp({ symbol: r.symbol }) }} style={{ cursor: 'pointer', background: r.symbol === symbol ? 'rgba(25,211,227,.08)' : undefined }}>
              <td onClick={e => { e.stopPropagation(); toggleFav(r.symbol) }} style={{ cursor: 'pointer', color: favs.includes(r.symbol) ? 'var(--amber)' : 'var(--mut)' }} aria-label="Favorito">{favs.includes(r.symbol) ? '★' : '☆'}</td>
              <td>{r.symbol}</td><td className="r num">{r.price}</td><td className={'r num ' + (r.change_pct >= 0 ? 'pos' : 'neg')}>{fmt.pct(r.change_pct)}</td><td className="r num">{Math.round(r.quote_volume).toLocaleString('en-US')}</td></tr>)}</tbody></table>}</div>
        </Card>
        <div className="grid">
          <Card title={`${symbol} · ${market === 'spot' ? 'Binance Spot' : 'Binance Futuros'}`} tone="green" right={<span className="tf">{['1m', '5m', '15m', '1h', '4h', '1d'].map(x => <button key={x} className={x === tf ? 'on' : ''} onClick={() => setTf(x)}>{x.toUpperCase()}</button>)}</span>} src={k.data ? `${k.data.source} · ${new Date(k.data.fetched_at).toLocaleTimeString('es-PE', { timeZone: 'America/Lima' })} PET` : undefined}>
            {k.error ? <Err msg={`${symbol}: ${k.error}`} /> : k.loading ? <Skeleton h={340} /> : <CandleChart candles={k.data.candles} height={340} />}
          </Card>
          <Card title="Indicadores (velas cerradas)" tone="violet">
            {i ? <div className="three"><div className="kv"><div><span>RSI 14</span><b className="num">{i.rsi14?.toFixed(1) ?? '—'}</b></div><div><span>ATR 14</span><b className="num">{i.atr14?.toPrecision(5) ?? '—'}</b></div><div><span>RVOL 20</span><b className="num">{i.rvol20?.toFixed(2) ?? '—'}</b></div></div>
              <div className="kv">{[9, 21, 55, 200].map(n => <div key={n}><span>EMA {n}</span><b className="num">{i.ema[n]?.toPrecision(7) ?? '—'}</b></div>)}</div>
              <div className="kv"><div><span>POC</span><b className="num">{i.volume_profile?.poc?.toPrecision(7) ?? '—'}</b></div><div><span>VAH / VAL</span><b className="num">{i.volume_profile ? `${i.volume_profile.vah.toPrecision(6)} / ${i.volume_profile.val.toPrecision(6)}` : '—'}</b></div><div><span>Régimen</span><b>{i.regime.label}</b></div></div></div> : <Empty>Calculando…</Empty>}
            {i?.volume_profile && <small className="mut">POC/VAH/VAL: {i.volume_profile.method}.</small>}
          </Card>
        </div>
      </div>
    </>
  )
}
