from app.core import _unit_factor, _canonical_unit, _convert_qty, get_unit_factor


def unit_factor(input_unit: str, base_unit: str) -> float:
    return float(_unit_factor(input_unit, base_unit))


def canonical_unit(unit: str) -> str:
    return _canonical_unit(unit)


def convert_qty(qty: float, from_unit: str, to_unit: str) -> float:
    return float(_convert_qty(qty, from_unit, to_unit))


def to_base_qty(qty_value: float, input_unit: str, base_unit: str) -> float:
    return float(qty_value or 0.0) * unit_factor(input_unit, base_unit)


def minmax_to_base(value: float, input_unit: str, base_unit: str) -> float:
    u = (input_unit or base_unit or '').strip()
    b = (base_unit or '').strip()
    if not b:
        return float(value or 0.0)
    factor = _unit_factor(u, b)
    if factor is None or float(factor) <= 0:
        raise ValueError(f'Unidad no compatible: {u!r} -> {b!r}')
    return float(value or 0.0) * float(factor)
