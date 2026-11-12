"""Contrato ProviderAdapter + utilidades de resiliencia (token bucket, circuit breaker, caché TTL)."""
from __future__ import annotations

import threading
import time
from abc import ABC, abstractmethod


class ProviderError(Exception):
    pass


class NotConnected(ProviderError):
    pass


class TokenBucket:
    def __init__(self, rate_per_sec: float, capacity: float):
        self.rate, self.capacity = rate_per_sec, capacity
        self.tokens, self.ts = capacity, time.monotonic()
        self.lock = threading.Lock()

    def take(self, n: float = 1.0, block: bool = True) -> bool:
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.capacity, self.tokens + (now - self.ts) * self.rate)
                self.ts = now
                if self.tokens >= n:
                    self.tokens -= n
                    return True
                wait = (n - self.tokens) / self.rate
            if not block:
                return False
            time.sleep(min(wait, 1.0))


class CircuitBreaker:
    def __init__(self, threshold: int = 5, cooldown: float = 30.0):
        self.threshold, self.cooldown = threshold, cooldown
        self.fails, self.opened_at = 0, 0.0

    def allow(self) -> bool:
        if self.fails < self.threshold:
            return True
        if time.monotonic() - self.opened_at > self.cooldown:
            self.fails = self.threshold - 1  # half-open
            return True
        return False

    def ok(self):
        self.fails = 0

    def fail(self):
        self.fails += 1
        if self.fails >= self.threshold:
            self.opened_at = time.monotonic()

    @property
    def is_open(self) -> bool:
        return self.fails >= self.threshold and (time.monotonic() - self.opened_at) <= self.cooldown


class TTLCache:
    def __init__(self):
        self._d: dict = {}
        self._lock = threading.Lock()

    def get(self, key):
        with self._lock:
            v = self._d.get(key)
            if v and v[0] > time.monotonic():
                return v[1]
        return None

    def set(self, key, val, ttl: float):
        with self._lock:
            if len(self._d) > 2000:
                self._d.clear()
            self._d[key] = (time.monotonic() + ttl, val)


class ProviderAdapter(ABC):
    name: str = ""
    display: str = ""

    @abstractmethod
    def capabilities(self) -> dict: ...

    @abstractmethod
    def health(self) -> dict: ...

    def validate_connection(self, **kw) -> dict:
        raise NotConnected(f"{self.display}: validate_connection no disponible")

    def list_instruments(self, market: str = "spot") -> list[dict]:
        raise NotConnected(f"{self.display} no conectado")

    def get_candles(self, symbol: str, interval: str, limit: int = 500, market: str = "spot",
                    end_time: int | None = None, start_time: int | None = None) -> list[dict]:
        raise NotConnected(f"{self.display} no conectado")

    def get_ticker(self, symbol: str, market: str = "spot") -> dict:
        raise NotConnected(f"{self.display} no conectado")

    def get_balances(self, **kw):
        raise NotConnected(f"{self.display} no conectado")

    def get_orders(self, **kw):
        raise NotConnected(f"{self.display} no conectado")

    def get_positions(self, **kw):
        raise NotConnected(f"{self.display} no conectado")

    def place_order(self, **kw):
        raise ProviderError("Trading real deshabilitado en CAPITAL RADAR PRO v1 (sin camino de ejecución live)")

    def cancel_order(self, **kw):
        raise ProviderError("Trading real deshabilitado")
