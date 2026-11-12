import math
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

_tmp = tempfile.mkdtemp(prefix="radar-test-")
os.environ["DATA_DIR"] = _tmp
os.environ["DATABASE_URL"] = f"sqlite:///{_tmp}/test.db"
os.environ["PAPER_AUTO_TRADING_ENABLED"] = "false"

from app.providers import binance as bmod  # noqa: E402
from app.sizing import SymbolFilters  # noqa: E402


def make_candles(n=400, start=100.0, seed=1, step=3600_000, closed=True):
    """Serie determinista (seno + tendencia), sin aleatoriedad externa."""
    out, t = [], 1_700_000_000_000
    for i in range(n):
        base = start * (1 + 0.0008 * i) + 5 * math.sin(i / 7.0 + seed)
        o = base
        c = base + 1.5 * math.sin(i / 3.0)
        out.append({"t": t + i * step, "o": o, "h": max(o, c) + 1, "l": min(o, c) - 1, "c": c,
                    "v": 1000 + 200 * math.sin(i / 5.0), "closed": closed})
    return out


class FakeBinance:
    last_latency_ms = 12.0
    last_ok_at = 1.0
    used_weight = "1"

    def __init__(self):
        self.prices = {"BTCUSDT": 60000.0, "ETHUSDT": 3000.0, "XRPUSDT": 0.5}
        self.calls = 0

    def capabilities(self):
        return {"public_market_data": True, "trading": False}

    def health(self):
        return {"ok": True, "latency_ms": 12.0}

    def list_instruments(self, market="spot"):
        return [{"symbol": s, "base": s[:-4], "quote": "USDT", "status": "TRADING", "market": market, "tradable": True}
                for s in self.prices]

    def tickers_24h(self, market="spot"):
        return [{"symbol": s, "price": p, "change_pct": 1.0, "quote_volume": 1e6 * (i + 1)}
                for i, (s, p) in enumerate(self.prices.items())]

    def get_ticker(self, symbol, market="spot"):
        if symbol not in self.prices:
            from app.providers.base import ProviderError
            raise ProviderError("símbolo inexistente")
        p = self.prices[symbol]
        return {"symbol": symbol, "price": p, "bid": p * 0.9999, "ask": p * 1.0001, "change_pct": 1.0, "high": p, "low": p,
                "volume": 1, "quote_volume": 1, "source": "FAKE", "ts": 0, "spread_pct": 0.02}

    def symbol_filters(self, symbol, market="spot"):
        return SymbolFilters(step_size=0.00001 if symbol != "XRPUSDT" else 0.1, min_qty=0.00001, min_notional=5.0)

    def get_candles(self, symbol, interval, limit=500, market="spot", end_time=None, start_time=None):
        self.calls += 1
        if symbol == "BADUSDT":
            from app.providers.base import ProviderError
            raise ProviderError("simulado")
        if symbol == "NEWUSDT":
            return make_candles(20)
        return make_candles(min(limit, 500), start=self.prices.get(symbol, 100))


@pytest.fixture(scope="session", autouse=True)
def _init():
    from app.db import init_engine
    init_engine()
    bmod.set_binance(FakeBinance())
    yield


@pytest.fixture()
def db():
    from app.db import SessionLocal
    s = SessionLocal()
    yield s
    s.rollback()
    s.close()


@pytest.fixture()
def fake():
    return bmod.binance()
