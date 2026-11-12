from contextlib import contextmanager

from sqlalchemy import create_engine, event
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from .config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_Session = None


def init_engine(url: str | None = None):
    global _engine, _Session
    s = get_settings()
    url = url or s.database_url
    if url.startswith("sqlite"):
        s.data_path  # asegura la carpeta
        _engine = create_engine(url, connect_args={"check_same_thread": False, "timeout": 30}, future=True)

        @event.listens_for(_engine, "connect")
        def _pragma(dbapi_con, _):
            cur = dbapi_con.cursor()
            cur.execute("PRAGMA journal_mode=WAL")
            cur.execute("PRAGMA synchronous=NORMAL")
            cur.execute("PRAGMA busy_timeout=30000")
            cur.close()
    else:
        _engine = create_engine(url, pool_size=5, max_overflow=5, pool_pre_ping=True, future=True)
    _Session = sessionmaker(_engine, expire_on_commit=False, future=True)
    from . import models  # noqa: F401

    Base.metadata.create_all(_engine)
    return _engine


def engine():
    if _engine is None:
        init_engine()
    return _engine


def SessionLocal():
    if _Session is None:
        init_engine()
    return _Session()


@contextmanager
def session_scope():
    s = SessionLocal()
    try:
        yield s
        s.commit()
    except Exception:
        s.rollback()
        raise
    finally:
        s.close()
