import { useEffect, useRef } from 'react'
import { ColorType, CandlestickSeries, HistogramSeries, createChart, type IChartApi, type ISeriesApi } from 'lightweight-charts'

export function CandleChart({ candles, height = 190 }: { candles: any[]; height?: number }) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<IChartApi | null>(null)
  const cs = useRef<ISeriesApi<'Candlestick'> | null>(null)
  const vs = useRef<ISeriesApi<'Histogram'> | null>(null)
  useEffect(() => {
    if (!el.current) return
    const c = createChart(el.current, {
      height, autoSize: true,
      layout: { background: { type: ColorType.Solid, color: 'transparent' }, textColor: '#8ba0bd', fontSize: 11 },
      grid: { vertLines: { color: 'rgba(60,120,160,.10)' }, horzLines: { color: 'rgba(60,120,160,.10)' } },
      rightPriceScale: { borderColor: 'rgba(60,120,160,.3)' }, timeScale: { borderColor: 'rgba(60,120,160,.3)', timeVisible: true },
      crosshair: { mode: 1 },
    })
    cs.current = c.addSeries(CandlestickSeries, { upColor: '#19e3a1', downColor: '#ff4d6a', borderVisible: false, wickUpColor: '#19e3a1', wickDownColor: '#ff4d6a' })
    vs.current = c.addSeries(HistogramSeries, { priceFormat: { type: 'volume' }, priceScaleId: '' })
    vs.current.priceScale().applyOptions({ scaleMargins: { top: .8, bottom: 0 } })
    chart.current = c
    return () => { c.remove(); chart.current = null }
  }, [height])
  useEffect(() => {
    if (!cs.current || !vs.current) return
    cs.current.setData(candles.map(k => ({ time: Math.floor(k.t / 1000) as any, open: k.o, high: k.h, low: k.l, close: k.c })))
    vs.current.setData(candles.map(k => ({ time: Math.floor(k.t / 1000) as any, value: k.v, color: k.c >= k.o ? 'rgba(25,227,161,.35)' : 'rgba(255,77,106,.35)' })))
  }, [candles])
  return <div ref={el} className="chart-box" style={{ height }} />
}

export function AreaLine(props: { points: { ts: string; equity: number }[]; mode: 'idx' | 'pnl' | 'dd'; initial: number; height?: number }) {
  return <AreaInner {...props} height={props.height ?? 210} />
}

function AreaInner({ points, mode, height, initial = 100 }: any) {
  const W = 640, H = height, pad = { l: 46, r: 12, t: 12, b: 22 }
  if (!points || points.length < 2) return <div className="empty" style={{ height: H - 20, display: 'grid', placeItems: 'center' }}>Sin historial todavía: el patrimonio se registra con cada operación y cada 5 minutos.</div>
  const eq: number[] = points.map((p: any) => p.equity)
  let ys: number[]
  if (mode === 'idx') ys = eq.map(e => e / initial * 100)
  else if (mode === 'pnl') ys = eq.map(e => e - initial)
  else { let pk = eq[0]; ys = eq.map(e => { pk = Math.max(pk, e); return (e - pk) / pk * 100 }) }
  let mn = Math.min(...ys), mx = Math.max(...ys)
  if (mn === mx) { mn -= 1; mx += 1 }
  const x = (i: number) => pad.l + i / (ys.length - 1) * (W - pad.l - pad.r)
  const y = (v: number) => pad.t + (1 - (v - mn) / (mx - mn)) * (H - pad.t - pad.b)
  const line = ys.map((v, i) => `${i ? 'L' : 'M'}${x(i).toFixed(1)},${y(v).toFixed(1)}`).join(' ')
  const area = `${line} L${x(ys.length - 1)},${H - pad.b} L${x(0)},${H - pad.b} Z`
  const col = mode === 'dd' ? '#ff4d6a' : '#19e3a1'
  const ticks = [0, .25, .5, .75, 1].map(f => mn + (mx - mn) * f)
  const last = ys[ys.length - 1]
  return (
    <svg viewBox={`0 0 ${W} ${H}`} width="100%" height={H} role="img" aria-label="Evolución del patrimonio">
      <defs><linearGradient id={'g' + mode} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor={col} stopOpacity=".38" /><stop offset="1" stopColor={col} stopOpacity="0" /></linearGradient></defs>
      {ticks.map((t, i) => <g key={i}><line x1={pad.l} x2={W - pad.r} y1={y(t)} y2={y(t)} stroke="rgba(60,120,160,.15)" /><text x={pad.l - 6} y={y(t) + 4} textAnchor="end" fontSize="10" fill="#8ba0bd">{t.toFixed(mode === 'dd' ? 1 : 2)}</text></g>)}
      <path d={area} fill={`url(#g${mode})`} /><path d={line} fill="none" stroke={col} strokeWidth="2" strokeLinejoin="round" style={{ filter: `drop-shadow(0 0 4px ${col})` }} />
      <circle cx={x(ys.length - 1)} cy={y(last)} r="4" fill="#fff" />
      <text x={pad.l} y={H - 5} fontSize="10" fill="#8ba0bd">{new Date(points[0].ts).toLocaleDateString('es-PE')}</text>
      <text x={W - pad.r} y={H - 5} textAnchor="end" fontSize="10" fill="#8ba0bd">{new Date(points[points.length - 1].ts).toLocaleDateString('es-PE')}</text>
    </svg>
  )
}

export function Donut({ parts, total, label }: { parts: { v: number; c: string }[]; total: number; label: string }) {
  const R = 52, C = 2 * Math.PI * R
  let off = 0
  return (
    <svg viewBox="0 0 140 140" width="132" height="132" role="img" aria-label="Universo de análisis">
      <circle cx="70" cy="70" r={R} fill="none" stroke="#12233a" strokeWidth="16" />
      {total > 0 && parts.map((p, i) => { const len = p.v / total * C; const el = <circle key={i} cx="70" cy="70" r={R} fill="none" stroke={p.c} strokeWidth="16" strokeDasharray={`${len} ${C - len}`} strokeDashoffset={-off} transform="rotate(-90 70 70)" style={{ transition: 'stroke-dasharray .8s' }} />; off += len; return el })}
      <text x="70" y="70" textAnchor="middle" fontSize="26" fontWeight="700" fill="#fff">{total}</text>
      <text x="70" y="88" textAnchor="middle" fontSize="12" fill="#8ba0bd">{label}</text>
    </svg>
  )
}
