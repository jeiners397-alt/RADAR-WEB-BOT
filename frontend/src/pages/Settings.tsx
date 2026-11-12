import { Card, Chip, PageTitle } from '../components/Common'
import { useApp } from '../store'

export default function SettingsPage() {
  const { user, account } = useApp()
  return (
    <>
      <PageTitle title="Configuración" sub="Perfil, zona horaria y estado de seguridad." />
      <div className="two">
        <Card title="Perfil" tone="cyan"><div className="kv"><div><span>Usuario</span><b>{user?.username}</b></div><div><span>Rol</span><b>{user?.role}</b></div><div><span>Zona horaria de presentación</span><b>America/Lima (PET)</b></div><div><span>Almacenamiento interno</span><b>UTC</b></div><div><span>Cuenta activa</span><b>{account?.name}</b></div></div>
          <small className="mut">La contraseña se cambia ejecutando <code>python scripts/create_admin.py admin</code> en el servidor (asistente interactivo).</small></Card>
        <Card title="Seguridad" tone="green"><div className="kv">
          <div><span>Sesión</span><Chip kind="g">Cookie HttpOnly + SameSite=Strict + CSRF</Chip></div>
          <div><span>Credenciales de brokers</span><Chip kind="g">Cifradas en servidor (Fernet)</Chip></div>
          <div><span>Secretos en el navegador</span><Chip kind="g">Ninguno (memoria efímera)</Chip></div>
          <div><span>Trading real</span><Chip kind="r">Deshabilitado</Chip></div>
          <div><span>Bloqueo por intentos fallidos</span><Chip kind="g">5 intentos / 5 min</Chip></div></div></Card>
        <Card title="Accesibilidad y animación" tone="violet"><p className="mut">Se respeta <code>prefers-reduced-motion</code> del sistema. Atajo: <kbd>Ctrl</kbd>+<kbd>K</kbd> abre la paleta de comandos.</p></Card>
        <Card title="Notificaciones" tone="violet"><p className="mut">Las notificaciones del sistema aparecen en la campana. Canales externos (correo/Telegram): pendiente de configurar.</p></Card>
      </div>
    </>
  )
}
