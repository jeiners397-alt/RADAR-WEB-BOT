import { useState } from 'react'
import { api, fmt } from '../api'
import { Card, Empty, PageTitle } from '../components/Common'
import { useApp, usePoll } from '../store'

export default function Reports() {
  const { account } = useApp()
  const [filter, setFilter] = useState('')
  const au = usePoll(() => api('/audits?limit=300' + (filter ? '&action=' + encodeURIComponent(filter) : '')), [filter], 10000)
  const aid = account!.id
  const dl = async (kind: string, fmtx: string) => {
    const r = await fetch(`/api/v1/reports/export?account_id=${aid}&kind=${kind}&fmt=${fmtx}`, { credentials: 'same-origin' })
    const blob = await r.blob(); const a = document.createElement('a'); a.href = URL.createObjectURL(blob); a.download = `${kind}_${aid}.${fmtx}`; a.click()
  }
  return (
    <>
      <PageTitle title="Informes & Auditoría" sub="Trazabilidad de configuraciones, órdenes y ejecuciones. Los detalles se sanean: nunca contienen secretos." />
      <div className="two" style={{ marginBottom: 12 }}>
        <Card title={`Exportar · ${account!.name}`} tone="green">
          <div className="flex wrap"><button className="btn ghost" onClick={() => dl('trades', 'csv')}>Operaciones CSV</button><button className="btn ghost" onClick={() => dl('trades', 'json')}>Operaciones JSON</button><button className="btn ghost" onClick={() => dl('orders', 'csv')}>Órdenes CSV</button><button className="btn ghost" onClick={() => dl('orders', 'json')}>Órdenes JSON</button></div>
          <small className="mut">Los exports son por cuenta. PDF: pendiente (ver docs/IMPLEMENTATION_STATUS.md).</small>
        </Card>
        <Card title="Filtro de auditoría" tone="cyan"><input placeholder="prefijo de acción: paper., auth., research., account…" value={filter} onChange={e => setFilter(e.target.value)} /></Card>
      </div>
      <Card title="Eventos de auditoría" tone="violet">
        {au.data?.length ? <div className="scroll-x" style={{ maxHeight: 520, overflowY: 'auto' }}><table><thead><tr><th>Hora (PET)</th><th>Acción</th><th>Cuenta</th><th>Detalle</th></tr></thead><tbody>{au.data.map((e: any) => <tr key={e.id}><td className="num">{fmt.dt(e.ts)}</td><td>{e.action}</td><td>{e.account_id ?? '—'}</td><td className="mut" style={{ maxWidth: 520, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{JSON.stringify(e.detail)}</td></tr>)}</tbody></table></div> : <Empty>Sin eventos.</Empty>}
      </Card>
    </>
  )
}
