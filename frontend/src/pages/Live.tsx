import { Card, PageTitle } from '../components/Common'
import { useApp } from '../store'

export default function Live() {
  const { user } = useApp()
  const f = user?.flags ?? {}
  const rows: [string, string, boolean][] = [
    ['REAL_TRADING_ENABLED', 'Interruptor global de trading real', !!f.real_trading_enabled],
    ['REAL_ORDER_EXECUTION_ENABLED', 'Ejecución de órdenes reales', !!f.real_order_execution_enabled],
    ['PAPER_AUTO_TRADING_ENABLED', 'Automatización paper (independiente)', !!f.paper_auto_trading_enabled],
  ]
  return (
    <>
      <PageTitle title="Trading en Vivo" sub="Pantalla de preparación. En esta versión NO existe ruta de ejecución real." />
      <div className="banner red"><b>BLOQUEADO.</b> El backend no contiene código que envíe órdenes reales: ni guardar claves, ni encender un bot, ni cambiar variables lo habilita.</div>
      <div className="two">
        <Card title="Estado de los interruptores (servidor)" tone="red">
          <table><tbody>{rows.map(([k, d, v]) => <tr key={k}><td><code>{k}</code><br /><small className="mut">{d}</small></td><td className="r"><span className={'chip ' + (v ? 'a' : 'r')}>{v ? 'ON' : 'OFF'}</span></td></tr>)}</tbody></table>
          <small className="mut">Los dos primeros se muestran siempre en OFF: el servidor los fuerza a falso en v1.</small>
        </Card>
        <Card title="Requisitos antes de poder habilitar trading real (futuro)" tone="cyan">
          <ol style={{ lineHeight: 1.9, margin: 0, paddingLeft: 18 }}>
            <li>Autorización explícita y específica del propietario.</li>
            <li>Claves Binance con permiso de lectura verificado y whitelisting de IP del VPS.</li>
            <li>Backtest con OOS positivo y paper estable durante un periodo definido.</li>
            <li>Implementar y auditar el camino live detrás de feature flag, con límites de riesgo y kill switch server-side.</li>
            <li>Revisión de seguridad independiente.</li>
          </ol>
        </Card>
      </div>
    </>
  )
}
