import { useEffect, useRef, useState, type ReactNode } from 'react'

export function Logo({ size = 34 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 64 64" aria-hidden>
      <defs><linearGradient id="lg" x1="0" y1="1" x2="1" y2="0"><stop offset="0" stopColor="#19e3a1" /><stop offset="1" stopColor="#19b6e3" /></linearGradient></defs>
      <rect x="6" y="34" width="12" height="22" rx="2" fill="url(#lg)" /><rect x="24" y="22" width="12" height="34" rx="2" fill="url(#lg)" opacity=".92" /><rect x="42" y="8" width="12" height="48" rx="2" fill="url(#lg)" opacity=".85" />
      <path d="M4 30 L22 18 L38 24 L60 4" stroke="#7c5cff" strokeWidth="3" fill="none" strokeLinecap="round" />
    </svg>
  )
}

export const Skeleton = ({ h = 60 }: { h?: number }) => <div className="skeleton" style={{ height: h }} />

export function Card({ title, icon, tone, right, children, src, style }: { title?: ReactNode; icon?: ReactNode; tone?: 'green' | 'violet' | 'cyan' | 'red'; right?: ReactNode; children: ReactNode; src?: string; style?: React.CSSProperties }) {
  return (
    <section className={'card ' + (tone ? 'c-' + tone : '')} style={style}>
      {title && <h3>{icon}<span>{title}</span><span className="sp" />{right}</h3>}
      {children}
      {src && <span className="src">{src}</span>}
    </section>
  )
}

export const Chip = ({ kind = 'm', children }: { kind?: 'g' | 'r' | 'a' | 'm' | 'v'; children: ReactNode }) => <span className={'chip ' + kind}>{children}</span>
export const Empty = ({ children }: { children: ReactNode }) => <div className="empty">{children}</div>

/** Contador suavizado (respeta prefers-reduced-motion). */
export function CountUp({ value, decimals = 2, prefix = '', suffix = '' }: { value: number | null | undefined; decimals?: number; prefix?: string; suffix?: string }) {
  const [shown, setShown] = useState(value ?? 0)
  const from = useRef(value ?? 0)
  useEffect(() => {
    if (value == null) return
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) { setShown(value); return }
    const start = performance.now(), a = from.current, b = value
    let raf = 0
    const step = (t: number) => { const p = Math.min(1, (t - start) / 600); setShown(a + (b - a) * (1 - Math.pow(1 - p, 3))); if (p < 1) raf = requestAnimationFrame(step); else from.current = b }
    raf = requestAnimationFrame(step)
    return () => cancelAnimationFrame(raf)
  }, [value])
  if (value == null) return <>—</>
  return <>{prefix}{shown.toLocaleString('en-US', { minimumFractionDigits: decimals, maximumFractionDigits: decimals })}{suffix}</>
}

export function PageTitle({ title, sub, right }: { title: string; sub?: string; right?: ReactNode }) {
  return <div className="page-title"><div><h2>{title}</h2>{sub && <p>{sub}</p>}</div><span className="sp" />{right}</div>
}

export function Err({ msg }: { msg: string | null }) { return msg ? <div className="err" role="alert">{msg}</div> : null }
