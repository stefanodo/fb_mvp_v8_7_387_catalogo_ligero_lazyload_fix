from __future__ import annotations
from dataclasses import dataclass
from typing import Optional

@dataclass
class UnitConversionResult:
    original_quantity: Optional[float]
    original_unit: Optional[str]
    converted_quantity: Optional[float]
    converted_unit: Optional[str]
    conversion_status: str
    notes: Optional[str] = None
    def ok(self) -> bool:
        return self.conversion_status == "CONVERTIDA"

WEIGHT_UNITS = {"g", "kg"}
COUNT_UNITS = {"ud", "docena"}
LIQUID_UNITS = {"ml", "l"}
VALID_UNITS = WEIGHT_UNITS | COUNT_UNITS | LIQUID_UNITS | {"racion"}

def normalize_unit(unit: Optional[str]) -> Optional[str]:
    if not unit: return None
    value = str(unit).strip().lower()
    aliases = {"gramo":"g","gramos":"g","gr":"g","kilo":"kg","kilos":"kg","kilogramo":"kg","kilogramos":"kg","unidad":"ud","unidades":"ud","uds":"ud","docenas":"docena","ración":"racion","raciones":"racion","mililitro":"ml","mililitros":"ml","litro":"l","litros":"l"}
    return aliases.get(value, value)

def safe_float(value) -> Optional[float]:
    if value is None or value == "": return None
    if isinstance(value, str): value = value.strip().replace(",", ".")
    try: return float(value)
    except Exception: return None

def convert_quantity(quantity, from_unit: Optional[str], to_unit: Optional[str], allow_liquid_to_weight: bool = False, liquid_density: Optional[float] = None) -> UnitConversionResult:
    qty, src, dst = safe_float(quantity), normalize_unit(from_unit), normalize_unit(to_unit)
    if qty is None or qty < 0: return UnitConversionResult(qty, src, None, dst, "NO_CONVERTIBLE", "Cantidad inválida.")
    if not src or not dst: return UnitConversionResult(qty, src, None, dst, "NO_CONVERTIBLE", "Unidad origen o destino pendiente.")
    if src not in VALID_UNITS or dst not in VALID_UNITS: return UnitConversionResult(qty, src, None, dst, "NO_CONVERTIBLE", "Unidad no reconocida.")
    if src == dst: return UnitConversionResult(qty, src, round(qty, 6), dst, "CONVERTIDA")
    if src in WEIGHT_UNITS and dst in WEIGHT_UNITS:
        converted = qty / 1000 if src == "g" and dst == "kg" else qty * 1000 if src == "kg" and dst == "g" else qty
        return UnitConversionResult(qty, src, round(converted, 6), dst, "CONVERTIDA")
    if src in COUNT_UNITS and dst in COUNT_UNITS:
        converted = qty * 12 if src == "docena" and dst == "ud" else qty / 12 if src == "ud" and dst == "docena" else qty
        return UnitConversionResult(qty, src, round(converted, 6), dst, "CONVERTIDA")
    if src in LIQUID_UNITS and dst in LIQUID_UNITS:
        converted = qty / 1000 if src == "ml" and dst == "l" else qty * 1000 if src == "l" and dst == "ml" else qty
        return UnitConversionResult(qty, src, round(converted, 6), dst, "CONVERTIDA", "Conversión solo entre unidades de volumen.")
    if src in LIQUID_UNITS and dst in WEIGHT_UNITS:
        if not allow_liquid_to_weight or not liquid_density or liquid_density <= 0:
            return UnitConversionResult(qty, src, None, dst, "PENDIENTE_CONVERSION_PESO", "Falta conversión validada de volumen a peso.")
        liters = qty / 1000 if src == "ml" else qty
        kg = liters * liquid_density
        converted = kg if dst == "kg" else kg * 1000
        return UnitConversionResult(qty, src, round(converted, 6), dst, "CONVERTIDA", "Conversión volumen-peso con densidad validada.")
    return UnitConversionResult(qty, src, None, dst, "UNIDAD_INCOMPATIBLE", f"No hay conversión segura de {src} a {dst}.")

def convert_for_cost(quantity, ingredient_unit: Optional[str], price_unit: Optional[str], allow_liquid_to_weight: bool = False, liquid_density: Optional[float] = None) -> UnitConversionResult:
    return convert_quantity(quantity, ingredient_unit, price_unit, allow_liquid_to_weight, liquid_density)
