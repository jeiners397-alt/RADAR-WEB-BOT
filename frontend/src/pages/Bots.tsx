import { api } from '../api'
import { Card, Chip, Empty, PageTitle } from '../components/Common'
import { usePoll } from '../store'

export default function Bots() {
  const w = usePoll(() => api('/research/workers'), [], 4000)
  const t = usePoll(() => api('/telemetry/latest'), [], 4000)
  const jobs = usePoll(() => api('/research/jobs'), [], 5000)
  return (
    <>
      <PageTitle title="Bots & Automatización" sub="Workers, colas y estado de ejecución. Los reintentos usan backoff exponencial y hay circuit breaker por proveedor." />
      <div className="three" style={{ marginBottom: 12 }}>
        <Card tone="cyan"><small className="mut">Cola pendiente</small><div className="num" style={{ fontSize: 26, fontWeight: 700 }}>{t.data?.queue_pending ?? '—'}</div></Card>
        <Card tone="green"><small className="mut">Latencia API Binance</small><div className="num" style={{ fontSize: 26, fontWeight: 700 }}>{t.data?.api_latency_ms ? Math.round(t.data.api_latency_ms) + ' ms' : '—'}</div><small className="mut">peso 1m usado: {t.data?.binance_used_weight_1m ?? '—'}</small></Card>
        <Card tone="violet"><small className="mut">Base de datos</small><div style={{ fontSize: 26, fontWeight: 700 }}>{t.data?.db_status ?? '—'}</div></Card>
      </div>
      <div className="two">
        <Card title="Workers" tone="violet">
          {w.data?.length ? <table><thead><tr><th>Worker</th><th>Tipo</th><th>Estado</th><th className="r">Último heartbeat</th></tr></thead><tbody>{w.data.map((x: any) => <tr key={x.worker_id}><td>{x.worker_id}</td><td>{x.kind}</td><td>{x.alive ? <Chip kind="g">Ejecutando</Chip> : <Chip kind="r">Sin heartbeat</Chip>}</td><td className="r num">{Math.round(x.age_seconds)} s</td></tr>)}</tbody></table> : <Empty>Ningún worker ha reportado heartbeat.</Empty>}
          <small className="mut">Concurrencia configurable con RESEARCH_WORKERS (por defecto 1 en el VPS de 4 GiB).</small>
        </Card>
        <Card title="Trabajos" tone="cyan">
          {jobs.data?.length ? <table><thead><tr><th>#</th><th>Trabajo</th><th>Estado</th><th className="r">Progreso</th></tr></thead><tbody>{jobs.data.map((j: any) => <tr key={j.id}><td>{j.id}</td><td>{j.name}</td><td><Chip kind={j.state === 'running' ? 'g' : 'm'}>{j.state}</Chip></td><td className="r num">{j.progress.processed_pct}%</td></tr>)}</tbody></table> : <Empty>Sin trabajos.</Empty>}
          <small className="mut">Pausa, reanuda, reintenta y cancela desde Investigación.</small>
        </Card>
      </div>
      <div className="banner info" style={{ marginTop: 12 }}>Bots de trading paper: se habilitan por estrategia (Estrategias) y solo operan si el servidor tiene <code>PAPER_AUTO_TRADING_ENABLED=true</code>. Hoy no hay ningún bot de ejecución activo.</div>
    </>
  )
}
