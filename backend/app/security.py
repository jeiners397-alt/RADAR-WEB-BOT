"""Hash de contraseñas (argon2), cifrado de secretos (Fernet, clave fuera de la BD) y sesiones."""
import hashlib
import os
import re
import secrets
from datetime import timedelta
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from cryptography.fernet import Fernet

from .config import get_settings

_ph = PasswordHasher()
_fernet: Fernet | None = None


def hash_password(pw: str) -> str:
    return _ph.hash(pw)


def verify_password(h: str, pw: str) -> bool:
    try:
        return _ph.verify(h, pw)
    except (VerifyMismatchError, Exception):
        return False


def _key_path() -> Path:
    return get_settings().data_path / "secrets" / "credential.key"


def get_fernet() -> Fernet:
    """Clave desde env CREDENTIAL_ENCRYPTION_KEY o archivo 0600 fuera de la base de datos."""
    global _fernet
    if _fernet is None:
        key = os.environ.get("CREDENTIAL_ENCRYPTION_KEY")
        if not key:
            p = _key_path()
            p.parent.mkdir(parents=True, exist_ok=True)
            if not p.exists():
                p.write_bytes(Fernet.generate_key())
                try:
                    os.chmod(p, 0o600)
                except OSError:
                    pass
            key = p.read_text().strip()
        _fernet = Fernet(key.encode() if isinstance(key, str) else key)
    return _fernet


def reset_fernet():
    global _fernet
    _fernet = None


def encrypt_secret(plain: str) -> str:
    return get_fernet().encrypt(plain.encode()).decode()


def decrypt_secret(blob: str) -> str:
    return get_fernet().decrypt(blob.encode()).decode()


def fingerprint(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()[:12]


def mask(plain: str) -> str:
    return (plain[:3] + "…" + plain[-2:]) if len(plain) > 8 else "••••"


def new_session_token() -> tuple[str, str, str]:
    token = secrets.token_urlsafe(32)
    return token, hashlib.sha256(token.encode()).hexdigest(), secrets.token_urlsafe(24)


def token_id(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_ttl() -> timedelta:
    return timedelta(hours=get_settings().session_ttl_hours)


_SECRET_PATTERNS = [
    re.compile(r"(?i)(api[_-]?key|secret|password|passwd|token|authorization)(['\"]?\s*[:=]\s*['\"]?)([^\s'\",}]+)"),
]


def scrub(text: str) -> str:
    """Elimina valores sensibles de textos que irán a logs/auditoría."""
    for p in _SECRET_PATTERNS:
        text = p.sub(lambda m: f"{m.group(1)}{m.group(2)}***", text)
    return text


def scrub_obj(o):
    if isinstance(o, dict):
        return {k: ("***" if re.search(r"(?i)secret|password|token|api_?key|passwd", str(k)) else scrub_obj(v)) for k, v in o.items()}
    if isinstance(o, list):
        return [scrub_obj(x) for x in o]
    if isinstance(o, str):
        return scrub(o)
    return o
