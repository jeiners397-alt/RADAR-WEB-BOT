"""Asistente de primer inicio: crea el usuario admin y las cuentas base (Binance público + paper 100 USDT).
La contraseña se pide por consola (getpass) o variable ADMIN_PASSWORD_FILE; nunca está en el código.
Uso:  python scripts/create_admin.py [usuario]
"""
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from sqlalchemy import select  # noqa: E402

from app.db import init_engine, session_scope  # noqa: E402
from app.models import User  # noqa: E402
from app.paper import ensure_default_accounts  # noqa: E402
from app.security import hash_password  # noqa: E402


def main():
    username = sys.argv[1] if len(sys.argv) > 1 else "admin"
    init_engine()
    with session_scope() as db:
        u = db.scalar(select(User).where(User.username == username))
        pwfile = os.environ.get("ADMIN_PASSWORD_FILE")
        if pwfile:
            pw = open(pwfile, encoding="utf-8").read().strip()
        else:
            pw = getpass.getpass(f"Contraseña para '{username}' (mín. 12 caracteres): ")
            if pw != getpass.getpass("Repite la contraseña: "):
                raise SystemExit("Las contraseñas no coinciden")
        if len(pw) < 12:
            raise SystemExit("Contraseña demasiado corta (mínimo 12 caracteres)")
        if u:
            u.password_hash = hash_password(pw)
            print(f"Contraseña de '{username}' actualizada.")
        else:
            u = User(username=username, password_hash=hash_password(pw), role="admin")
            db.add(u)
            db.flush()
            print(f"Usuario '{username}' creado.")
        ensure_default_accounts(db, u.id)
    print("Cuentas base listas: Binance Público y Binance Paper (capital virtual 100 USDT).")


if __name__ == "__main__":
    main()
