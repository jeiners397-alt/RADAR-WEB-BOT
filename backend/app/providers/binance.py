"""Binance — SOLO endpoints públicos (sin firma, sin API key). No existe place_order."""
from __future__ import annotations

import time

import httpx

from ..config import get_settings
from ..sizing import SymbolFilters
from .base import CircuitBreaker, ProviderAdapter, ProviderError, TokenBucket, TTLCache

INTERVALS = ["1m", "3m", "5m", "15m", "30m", "1h", "2h", "4h", "6h", "12h", "1d", "1w"]
INTERVAL_SECONDS = {"1m": 60, "3m": 180, "5m": 300, "15m": 900, "30m": 1800, "1h": 3600, "2h": 7200,
                    "4h": 14400, "6h": 21600, "12h": 43200, "1d": 86400, "1w": 604800}


class BinancePublic(ProviderAdapter):
    name = "binance"
    display = "Binance"

    def __init__(self, client: httpx.Client | None = None):
        s = get_settings()
        self.spot_url, self.fut_url = s.binance_spot_url, s.binance_futures_url
        verify = True
        if s.use_system_trust:  # útil en Windows/redes corporativas con inspección TLS
            import ssl
            import truststore
            verify = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        self.client = client or httpx.Client(timeout=s.http_timeout, verify=verify,
                                             headers={"User-Agent": "capital-radar-pro/1.0"})
        self.bucket = TokenBucket(rate_per_sec=10, capacity=20)  # ~600 req/min, bajo el límite de peso
        self.breaker = CircuitBreaker(5, 30)
        self.cache = TTLCache()
        self.used_weight = None
        self.last_latency_ms: float | None = None
        self.last_ok_at: float | None = None
        self.last_error: str | None = None

    # -- HTTP resiliente: token bucket + reintentos exponenciales + circuit breaker
    def _get(self, base: str, path: str, params: dict | None = None, retries: int = 3):
        if not self.breaker.allow():
            raise ProviderError("Binance: circuit breaker abierto (demasiados fallos recientes)")
        delay = 0.5
        for attempt in range(retries):
            self.bucket.take()
            t0 = time.monotonic()
            try:
                r = self.client.get(base + path, params=params)
                self.last_latency_ms = (time.monotonic() - t0) * 1000
                self.used_weight = r.headers.get("x-mbx-used-weight-1m", self.used_weight)
                if r.status_code in (418, 429):
                    ra = float(r.headers.get("retry-after", delay * 4))
                    self.breaker.fail()
                    time.sleep(min(ra, 5))
                    continue
                r.raise_for_status()
                self.breaker.ok()
                self.last_ok_at = time.time()
                self.last_error = None
                return r.json()
            except (httpx.HTTPError, ValueError) as e:
                self.breaker.fail()
                self.last_error = type(e).__name__
                if attempt == retries - 1:
                    raise ProviderError(f"Binance no disponible: {type(e).__name__}") from e
                time.sleep(delay)
                delay *= 2
        raise ProviderError("Binance: límite de tasa")

    def _base(self, market: str) -> tuple[str, str]:
        return (self.fut_url, "/fapi/v1") if market == "futures" else (self.spot_url, "/api/v3")

    def capabilities(self) -> dict:
        return {"public_market_data": True, "private_account": False, "trading": False,
                "markets": ["spot", "futures"], "intervals": INTERVALS,
                "notes": "Solo datos públicos. Sin API key. Trading real deshabilitado."}

    def health(self) -> dict:
        try:
            base, pre = self._base("spot")
            t0 = time.monotonic()
            self._get(base, pre + "/ping", retries=1)
            return {"ok": True, "latency_ms": round((time.monotonic() - t0) * 1000, 1), "used_weight_1m": self.used_weight}
        except ProviderError as e:
            return {"ok": False, "error": str(e), "breaker_open": self.breaker.is_open}

    def _exchange_info(self, market: str) -> dict:
        key = f"xi:{market}"
        hit = self.cache.get(key)
        if hit:
            return hit
        base, pre = self._base(market)
        data = self._get(base, pre + "/exchangeInfo")
        self.cache.set(key, data, 600)
        return data

    def list_instruments(self, market: str = "spot") -> list[dict]:
        out = []
        for s in self._exchange_info(market)["symbols"]:
            status = s.get("status") or s.get("contractStatus")
            out.append({"symbol": s["symbol"], "base": s["baseAsset"], "quote": s["quoteAsset"],
                        "status": status, "market": market, "tradable": status == "TRADING"})
        return out

    def symbol_filters(self, symbol: str, market: str = "spot") -> SymbolFilters:
        for s in self._exchange_info(market)["symbols"]:
            if s["symbol"] == symbol:
                f = SymbolFilters()
                for flt in s.get("filters", []):
                    t = flt["filterType"]
                    if t == "LOT_SIZE":
                        f.step_size, f.min_qty = float(flt["stepSize"]), float(flt["minQty"])
                    elif t in ("NOTIONAL", "MIN_NOTIONAL"):
                        f.min_notional = float(flt.get("minNotional") or flt.get("notional") or 0)
                    elif t == "PRICE_FILTER":
                        f.tick_size = float(flt["tickSize"])
                return f
        raise ProviderError(f"Símbolo {symbol} no existe en Binance {market}")

    def get_candles(self, symbol, interval, limit=500, market="spot", end_time=None, start_time=None):
        if interval not in INTERVALS:
            raise ProviderError(f"Intervalo no soportado: {interval}")
        base, pre = self._base(market)
        params = {"symbol": symbol.upper(), "interval": interval, "limit": min(limit, 1000)}
        if end_time:
            params["endTime"] = end_time
        if start_time:
            params["startTime"] = start_time
        key = f"k:{market}:{symbol}:{interval}:{limit}:{end_time}:{start_time}"
        ttl = 5 if not end_time else 300
        hit = self.cache.get(key)
        if hit:
            return hit
        raw = self._get(base, pre + "/klines", params)
        now_ms = int(time.time() * 1000)
        out = [{"t": k[0], "o": float(k[1]), "h": float(k[2]), "l": float(k[3]), "c": float(k[4]), "v": float(k[5]),
                "closed": k[6] < now_ms} for k in raw]
        self.cache.set(key, out, ttl)
        return out

    def get_ticker(self, symbol, market="spot"):
        base, pre = self._base(market)
        key = f"t:{market}:{symbol}"
        hit = self.cache.get(key)
        if hit:
            return hit
        d = self._get(base, pre + "/ticker/24hr", {"symbol": symbol.upper()})
        bk = self._get(base, pre + "/ticker/bookTicker", {"symbol": symbol.upper()})
        out = {"symbol": symbol.upper(), "market": market, "price": float(d["lastPrice"]),
               "change_pct": float(d["priceChangePercent"]), "high": float(d["highPrice"]), "low": float(d["lowPrice"]),
               "volume": float(d["volume"]), "quote_volume": float(d["quoteVolume"]),
               "bid": float(bk["bidPrice"]), "ask": float(bk["askPrice"]),
               "source": f"Binance {market} público", "ts": int(time.time() * 1000)}
        out["spread_pct"] = (out["ask"] - out["bid"]) / out["price"] * 100 if out["price"] else None
        self.cache.set(key, out, 2)
        return out

    def tickers_24h(self, market: str = "spot") -> list[dict]:
        key = f"t24:{market}"
        hit = self.cache.get(key)
        if hit:
            return hit
        base, pre = self._base(market)
        raw = self._get(base, pre + "/ticker/24hr")
        out = [{"symbol": d["symbol"], "price": float(d["lastPrice"]), "change_pct": float(d["priceChangePercent"]),
                "quote_volume": float(d["quoteVolume"])} for d in raw]
        self.cache.set(key, out, 15)
        return out


_instance: BinancePublic | None = None


def binance() -> BinancePublic:
    global _instance
    if _instance is None:
        _instance = BinancePublic()
    return _instance


def set_binance(inst):
    global _instance
    _instance = inst
