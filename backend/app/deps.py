"""Dependencias FastAPI: sesión de BD, usuario autenticado (cookie HttpOnly + CSRF) y propiedad de cuentas."""
from datetime import datetime, timezone

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import Account, SessionRow, User
from .security import token_id

COOKIE = "crp_session"


def get_db():
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def current_session(request: Request, db: Session = Depends(get_db)) -> tuple[User, SessionRow]:
    tok = request.cookies.get(COOKIE)
    if not tok:
        raise HTTPException(401, "No autenticado")
    row = db.get(SessionRow, token_id(tok))
    if not row:
        raise HTTPException(401, "Sesión inválida")
    exp = row.expires_at if row.expires_at.tzinfo else row.expires_at.replace(tzinfo=timezone.utc)
    if exp < datetime.now(timezone.utc):
        db.delete(row)
        db.commit()
        raise HTTPException(401, "Sesión expirada")
    if request.method not in ("GET", "HEAD", "OPTIONS"):
        if request.headers.get("x-csrf-token") != row.csrf:
            raise HTTPException(403, "CSRF inválido")
    user = db.get(User, row.user_id)
    if not user:
        raise HTTPException(401, "Usuario inexistente")
    return user, row


def current_user(sess=Depends(current_session)) -> User:
    return sess[0]


def owned_account(db: Session, user: User, account_id: int) -> Account:
    """Autorización server-side: nunca se confía en account_id del cliente sin comprobar propiedad."""
    acc = db.get(Account, account_id)
    if not acc or acc.user_id != user.id:
        raise HTTPException(404, "Cuenta no encontrada")
    return acc
