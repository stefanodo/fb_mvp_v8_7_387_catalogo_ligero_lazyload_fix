from app.core import _parse_float, normalize_price_to_base, suggest_item_waste_pct, upper_name, normalize_stock_area


def normalize_item_type(value: str = "INSUMO") -> str:
    v = (value or 'INSUMO').strip().upper()
    if v in {'PREPARACION','PREPARACIÓN','SUBRECETA','ELABORADO'}:
        return 'PREPARACION'
    return 'INSUMO'


def normalize_order_category(value: str = "") -> str:
    v = (value or "").strip().lower()
    mapping = {
        "verduras": "verduras", "verdura": "verduras",
        "pescados": "pescados", "pescado": "pescados", "marisco": "pescados",
        "carnes": "carnes", "carne": "carnes",
        "huevos": "huevos", "huevo": "huevos",
        "lacteos": "lacteos", "lácteos": "lacteos", "lacteo": "lacteos", "lácteo": "lacteos",
        "preparaciones": "preparaciones", "preparacion": "preparaciones", "preparación": "preparaciones",
        "limpieza": "limpieza", "congelados": "congelados",
    }
    return mapping.get(v, "")


def normalize_item_payload(name: str, unit: str, current_price: str = "0", current_price_unit: str = "", waste_default_pct: str = "", stock_area: str = "", order_category: str = "", item_type: str = "INSUMO") -> dict:
    u = (unit or "").strip()
    cpu = (current_price_unit or "").strip() or u
    price = normalize_price_to_base(_parse_float(current_price, 0.0), u, cpu)
    item_name = upper_name(name)
    waste_txt = (waste_default_pct or "").strip()
    waste_def = (_parse_float(waste_txt, suggest_item_waste_pct(item_name, u))
                 if waste_txt != "" else suggest_item_waste_pct(item_name, u))
    return {
        "name": item_name,
        "unit": u,
        "current_price": float(price or 0),
        "current_price_unit": cpu,
        "waste_default_pct": float(waste_def or 0),
        "stock_area": normalize_stock_area(stock_area),
        "order_category": normalize_order_category(order_category),
        "item_type": normalize_item_type(item_type),
    }


def normalize_supplier_payload(name: str, phone: str = "", email: str = "") -> dict:
    return {
        "name": (name or "").strip(),
        "phone": (phone or "").strip(),
        "email": (email or "").strip(),
    }
