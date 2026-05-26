from __future__ import annotations

from urllib.parse import urlencode
import unicodedata


def normalize_order_note(note: str = "") -> str:
    return (note or "").strip()


def normalize_supplier_name(name: str = "") -> str:
    return (name or "").strip()


def order_page_url(center_id: int | None = None, oid: int | None = None, anchor: str = "orderDetailPanel", **params) -> str:
    query = {"page": "pedidos"}
    if center_id:
        query["center_id"] = int(center_id)
    if oid:
        query["oid"] = int(oid)
    for key, value in params.items():
        if value is None or value == "":
            continue
        query[key] = value
    url = f"/?{urlencode(query)}"
    if anchor:
        url += f"#{anchor}"
    return url


def parse_optional_int(raw_value) -> int | None:
    try:
        value = str(raw_value or "").strip()
        return int(value) if value else None
    except Exception:
        return None


def order_norm_text(value: str = "") -> str:
    s = unicodedata.normalize('NFKD', str(value or ''))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch))
    return s.lower().strip()


def normalize_order_block(value: str = "") -> str:
    v = order_norm_text(value)
    mapping = {
        'fresh': 'fresh', 'frescos': 'fresh',
        'frozen': 'frozen', 'congelados': 'frozen',
        'dry': 'dry', 'secos': 'dry',
        'clean': 'clean', 'limpieza': 'clean',
        'free': 'free', 'libres': 'free', 'sin clasificar': 'free',
        'prod': 'prod', 'producciones': 'prod',
    }
    return mapping.get(v, 'fresh')


def normalize_order_fresh_group(value: str = "") -> str:
    v = order_norm_text(value)
    mapping = {
        'verduras': 'verduras', 'verdura': 'verduras', 'hortalizas': 'verduras', 'frutas': 'verduras', 'fruta': 'verduras',
        'pescados': 'pescados', 'pescado': 'pescados', 'marisco': 'pescados',
        'carnes': 'carnes', 'carne': 'carnes',
        'huevos': 'huevos', 'huevo': 'huevos',
        'lacteos': 'lacteos', 'lacteo': 'lacteos', 'lácteos': 'lacteos', 'lácteo': 'lacteos',
        'all': 'all', 'todos': 'all',
    }
    return mapping.get(v, '')


def classify_order_fresh_group(name: str = '', explicit: str = '') -> str:
    exp = normalize_order_fresh_group(explicit)
    if exp and exp != 'all':
        return exp
    n = order_norm_text(name)
    fish_words = [
        'atun','salmon','bacalao','merluza','rodaballo','lubina','dorada','corvina','rape','sepia','calamar','pulpo',
        'mejillon','ostra','almeja','chirla','navaja','vieira','berberecho','gamba','langost','bogavante','carabinero',
        'necora','caballa','anchoa','boqueron','trucha','pescado','jurel','gallo','besugo','sardina','sardinilla',
        'cabracho','pez','hueva de maruca','hueva','ventresca','bonito','pez espada','emperador','chipiron',
        'calamarcito','sepionet','marisco','zamburina','navajas','berberechos','atun rojo','balfego'
    ]
    meat_words = [
        'ternera','vacuno','buey','entrecot','solomillo','magret','pato','pollo','cerdo','cordero','costilla','morcilla',
        'chorizo','papada','lomo','carne','conejo','rabo toro','guanciale','salchicha','butifarra','perdiz',
        'pichon','jamon','bacon','panceta','mortadela','pastrami','secreto','presa','pluma','chuleta','hamburguesa',
        'filete','carrillera','cochinillo','iberico','iberica','foie','sobrasada','lacon','cecina','huesos de pollo',
        'alas de pollo','patas de pollo'
    ]
    egg_words = ['huevo','huevos','yema','claras','codorniz','ovoproducto','huevina']
    dairy_words = [
        'queso','yogur','yogurt','kefir','nata','mantequilla','leche','burrata','ricotta','requeson','mozzarella',
        'gorgonzola','parmesano','skyr','queso crema','mascarpone','pecorino','grana padano','manchego','cheddar',
        'brie','camembert','gruyere','emmental','provolone','taleggio','feta'
    ]
    if any(w in n for w in fish_words):
        return 'pescados'
    if any(w in n for w in meat_words):
        return 'carnes'
    if any(w in n for w in egg_words):
        return 'huevos'
    if any(w in n for w in dairy_words):
        return 'lacteos'
    return 'verduras'


def infer_order_block(*, stock_area: str = '', name: str = '', explicit_group: str = '', raw_category: str = '', raw_subcategory: str = '') -> str:
    area = order_norm_text(stock_area)
    if area in {'frescos', 'fresh'}:
        return 'fresh'
    if area in {'congelados', 'frozen'}:
        return 'frozen'
    if area in {'secos', 'dry'}:
        return 'dry'
    if area in {'limpieza', 'clean'}:
        return 'clean'
    combined = order_norm_text(' '.join([explicit_group, raw_category, raw_subcategory]))
    if combined:
        if any(k in combined for k in ['congel', 'frozen', 'ultracongel']):
            return 'frozen'
        if any(k in combined for k in ['limpieza', 'higiene', 'deterg', 'lejia', 'desengras', 'papel']):
            return 'clean'
        if any(k in combined for k in ['seco', 'economato', 'despensa', 'ultramarinos']):
            return 'dry'
        if any(k in combined for k in ['verdura', 'verduras', 'hortaliza', 'fruta', 'pescado', 'pescados', 'marisco', 'carne', 'carnes', 'huevo', 'huevos', 'lacteo', 'lacteos']):
            return 'fresh'
    return 'free'


def item_matches_order_filters(item: dict, block: str = '', fresh_group: str = '') -> bool:
    block_norm = normalize_order_block(block)
    if block_norm in {'all', 'prod'}:
        return True
    item_block = infer_order_block(
        stock_area=str(item.get('stock_area') or ''),
        name=str(item.get('name') or ''),
        explicit_group=str(item.get('order_category') or item.get('fresh_group') or ''),
        raw_category=str(item.get('category') or ''),
        raw_subcategory=str(item.get('subcategory') or ''),
    )
    if item_block != block_norm:
        return False
    if block_norm != 'fresh':
        return True
    wanted_group = normalize_order_fresh_group(fresh_group)
    if not wanted_group or wanted_group == 'all':
        return True
    actual_group = normalize_order_fresh_group(item.get('fresh_group') or classify_order_fresh_group(str(item.get('name') or ''), str(item.get('order_category') or '')))
    return actual_group == wanted_group
