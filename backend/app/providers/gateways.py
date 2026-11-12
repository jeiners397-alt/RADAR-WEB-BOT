"""Exness y MT5: adaptadores HONESTOS. No hay integración verificada, por lo que nunca reportan 'conectado'."""
from __future__ import annotations

from .base import ProviderAdapter


class ExnessAdapter(ProviderAdapter):
    name = "exness"
    display = "Exness"

    def capabilities(self) -> dict:
        return {
            "public_market_data": False, "private_account": False, "trading": False,
            "status": "REQUIERE PASARELA OFICIAL/MT5",
            "notes": ("Exness opera sobre MetaTrader 4/5 (y su terminal web). No se asume una API pública universal "
                      "de usuario+contraseña. Se conectará únicamente a través de una pasarela MT5 verificada."),
            "fields": ["platform", "account_type", "login", "server", "password"],
        }

    def health(self) -> dict:
        return {"ok": False, "state": "no_conectado", "detail": "Requiere pasarela MT5 autorizada; no hay integración activa"}


class MT5Adapter(ProviderAdapter):
    name = "mt5"
    display = "MetaTrader 5"

    def capabilities(self) -> dict:
        return {
            "public_market_data": False, "private_account": False, "trading": False,
            "status": "REQUIERE GATEWAY WINDOWS",
            "notes": ("El paquete Python MetaTrader5 solo funciona con un terminal MT5 en Windows. El VPS es Ubuntu: "
                      "se necesita un gateway Windows separado (VM o PC) expuesto de forma segura. No implementado."),
            "fields": ["login", "server", "password"],
        }

    def health(self) -> dict:
        return {"ok": False, "state": "no_conectado", "detail": "Sin gateway MT5 configurado ni verificado"}


def adapter_for(provider: str):
    from .binance import binance
    return {"binance": binance, "exness": ExnessAdapter, "mt5": MT5Adapter}[provider]()
