"""Dimensionamiento algorítmico: 5% del PATRIMONIO (equity) como exposición nominal. NO es riesgo máximo de pérdida.

Definición (documentada en docs/DECISIONS.md): equity = caja disponible + valor de mercado de posiciones abiertas.
objetivo = equity * fraction. Se limita por la caja disponible (descontando comisión estimada).
Se redondea hacia ABAJO al stepSize (con un único ajuste de 1 step hacia arriba, máx. +10% del objetivo, solo para alcanzar minNotional). Si el resultado viola minNotional/minQty se RECHAZA: nunca se sube solo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from decimal import ROUND_DOWN, Decimal


MAX_OVERSHOOT = 0.10


@dataclass
class SymbolFilters:
    step_size: float = 0.00000001
    min_qty: float = 0.0
    min_notional: float = 0.0
    tick_size: float = 0.00000001


@dataclass
class Sizing:
    ok: bool
    reason: str = ""
    equity: float = 0.0
    fraction: float = 0.0
    target_notional: float = 0.0
    quantity: float = 0.0
    notional: float = 0.0
    steps: list[str] = field(default_factory=list)

    def asdict(self) -> dict:
        return self.__dict__.copy()


def floor_to_step(qty: float, step: float) -> float:
    if step <= 0:
        return qty
    d = (Decimal(str(qty)) / Decimal(str(step))).to_integral_value(rounding=ROUND_DOWN) * Decimal(str(step))
    return float(d)


def algo_size(equity: float, cash: float, price: float, filters: SymbolFilters, fraction: float = 0.05,
              fee_rate: float = 0.001) -> Sizing:
    s = Sizing(ok=False, equity=equity, fraction=fraction)
    if price <= 0 or equity <= 0:
        s.reason = "Precio o patrimonio inválido"
        return s
    target = equity * fraction
    s.target_notional = target
    s.steps.append(f"Patrimonio {equity:.2f} × {fraction * 100:.2f}% = {target:.4f} USDT objetivo")
    max_affordable = cash / (1 + fee_rate)
    if target > max_affordable:
        s.reason = f"Saldo disponible insuficiente ({cash:.2f} USDT) para el objetivo {target:.2f}"
        return s
    qty = floor_to_step(target / price, filters.step_size)
    s.steps.append(f"Cantidad = {target:.4f}/{price} redondeada abajo a step {filters.step_size} = {qty}")
    notional = qty * price
    # minNotional típico (5 USDT) == objetivo (5 USDT): el redondeo hacia abajo casi siempre queda un poco por debajo.
    # Se permite UN step hacia arriba solo si el sobrante respecto al objetivo es <= MAX_OVERSHOOT (10%). Nunca más.
    if notional < filters.min_notional <= target * (1 + MAX_OVERSHOOT):
        up = qty + filters.step_size
        if up * price <= target * (1 + MAX_OVERSHOOT) and up * price <= max_affordable:
            qty, notional = float(Decimal(str(up))), up * price
            s.steps.append(f"Ajuste de 1 step para cumplir minNotional: nocional {notional:.4f} (sobreexposición ≤ {MAX_OVERSHOOT:.0%} del objetivo)")
    s.quantity, s.notional = qty, notional
    if qty <= 0 or qty < filters.min_qty:
        s.reason = f"Cantidad {qty} menor que minQty {filters.min_qty}"
        return s
    if notional < filters.min_notional:
        s.reason = (f"Nocional {notional:.4f} USDT < minNotional {filters.min_notional} del instrumento: "
                    f"rechazada (no se aumenta automáticamente la exposición)")
        return s
    s.ok = True
    return s
