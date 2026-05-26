from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any, Dict, List, Tuple

from app.core import db

DEMO_BUSINESS_ID = 'demo_bar_business'
DEMO_RESTAURANT_ID = 'demo_bar_local'
DEMO_BAR_ID = 'demo_main_bar'
DEMO_PROVIDER = 'Proveedor Bar Demo'


def _now() -> str:
    return datetime.utcnow().isoformat(timespec='seconds')


def _j(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True)


def _norm(value: str) -> str:
    txt = str(value or '').strip().lower()
    import unicodedata
    txt = unicodedata.normalize('NFKD', txt)
    txt = ''.join(ch for ch in txt if not unicodedata.combining(ch))
    txt = re.sub(r'[^a-z0-9]+', ' ', txt)
    return ' '.join(txt.split())




def _bar_abv_percent(name: str) -> float:
    """ABV demo/orientativo para calcular alcohol por copa en Barra.
    Mantener en Barra; no afecta Cocina. Se actualizará con ficha/albarán real cuando exista.
    """
    n = _norm(name)
    rules = [
        (('ron',), 40.0),
        (('ginebra', 'gin'), 40.0),
        (('vodka',), 40.0),
        (('tequila',), 38.0),
        (('cointreau', 'triple sec'), 40.0),
        (('vermut',), 15.0),
        (('campari',), 25.0),
        (('bourbon', 'whisky'), 40.0),
        (('angostura',), 44.7),
        (('vino blanco', 'vino tinto', 'vino'), 12.5),
        (('cerveza',), 5.0),
    ]
    for keys, abv in rules:
        if any(k in n for k in keys):
            return abv
    return 0.0


def _cocktail_abv_from_lines(lines, serving_size_ml: float) -> float:
    """% alcohol aprox = ml alcohol puro / ml bebida servida * 100.
    Solo cuenta líneas líquidas de alcohol. Hielo/garnish/sólidos no suman alcohol.
    """
    try:
        serving = float(serving_size_ml or 0.0)
    except Exception:
        serving = 0.0
    if serving <= 0:
        return 0.0
    pure_ml = 0.0
    for ln in lines or []:
        try:
            if isinstance(ln, dict):
                unit = ln.get('unit') or ''
                qty = float(ln.get('qty_net') or 0.0)
                name = ln.get('ingredient_name') or ''
            else:
                unit = ln['unit'] or ''
                qty = float(ln['qty_net'] or 0.0)
                name = ln['ingredient_name'] or ''
        except Exception:
            continue
        u = unit.strip().lower()
        if u not in {'ml', 'cl', 'l'}:
            continue
        if u == 'cl':
            qty *= 10.0
        elif u == 'l':
            qty *= 1000.0
        abv = _bar_abv_percent(name)
        if abv > 0:
            pure_ml += qty * (abv / 100.0)
    return round((pure_ml / serving) * 100.0, 2)

def _safe_float(v: Any, default: float = 0.0) -> float:
    try:
        return float(str(v if v is not None else '').replace(',', '.').strip() or default)
    except Exception:
        return default


def ensure_bar_schema(cur) -> None:
    cur.execute('''CREATE TABLE IF NOT EXISTS bar_businesses(
        business_id TEXT PRIMARY KEY,
        business_name TEXT,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0,
        data_scope TEXT DEFAULT 'demo',
        created_at TEXT,
        updated_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS bar_locations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT,
        restaurant_id TEXT,
        restaurant_name TEXT,
        bar_id TEXT,
        bar_name TEXT,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        created_at TEXT,
        updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id)
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS bar_items(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT,
        restaurant_id TEXT,
        bar_id TEXT,
        code TEXT,
        name TEXT,
        normalized_name TEXT,
        item_type TEXT,
        family TEXT,
        base_unit TEXT,
        purchase_unit TEXT,
        purchase_qty REAL DEFAULT 0,
        purchase_price_2025 REAL DEFAULT 0,
        purchase_price_2026 REAL DEFAULT 0,
        cost_per_base_unit_2026 REAL DEFAULT 0,
        standard_waste_percent REAL DEFAULT 0,
        juice_yield_percent REAL DEFAULT NULL,
        juice_cost_per_ml_2026 REAL DEFAULT NULL,
        supplier_name_demo TEXT,
        min_stock REAL DEFAULT 0,
        max_stock REAL DEFAULT 0,
        location TEXT,
        active INTEGER DEFAULT 1,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0,
        data_scope TEXT DEFAULT 'demo',
        created_at TEXT,
        updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,normalized_name)
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS bar_stock_movements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT,
        restaurant_id TEXT,
        bar_id TEXT,
        bar_item_id INTEGER,
        movement_type TEXT,
        qty REAL DEFAULT 0,
        unit TEXT,
        document_code TEXT,
        source_module TEXT,
        responsible_name TEXT,
        movement_datetime TEXT,
        notes TEXT,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0,
        created_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS bar_productions(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT,
        restaurant_id TEXT,
        bar_id TEXT,
        code TEXT,
        name TEXT,
        production_type TEXT,
        yield_qty REAL DEFAULT 0,
        yield_unit TEXT,
        cost_total_2026 REAL DEFAULT 0,
        cost_per_unit_2026 REAL DEFAULT 0,
        standard_waste_percent REAL DEFAULT 0,
        shelf_life_days INTEGER DEFAULT 0,
        lot TEXT,
        responsible TEXT,
        storage_location TEXT,
        procedure_text TEXT,
        status TEXT,
        stock_actual REAL DEFAULT 0,
        used_in_recipes TEXT,
        es_vendible INTEGER DEFAULT 0,
        sale_price REAL DEFAULT NULL,
        notes TEXT,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0,
        data_scope TEXT DEFAULT 'demo',
        created_at TEXT,
        updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,code)
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS bar_production_lines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bar_production_id INTEGER,
        bar_item_id INTEGER,
        item_name TEXT,
        qty_net REAL DEFAULT 0,
        unit TEXT,
        waste_percent REAL DEFAULT 0,
        qty_gross REAL DEFAULT 0,
        cost_unit_2026 REAL DEFAULT 0,
        cost_total_net_2026 REAL DEFAULT 0,
        cost_total_gross_2026 REAL DEFAULT 0,
        notes TEXT,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS bar_production_stock_movements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT,
        restaurant_id TEXT,
        bar_id TEXT,
        bar_production_id INTEGER,
        movement_type TEXT,
        qty REAL DEFAULT 0,
        unit TEXT,
        source_module TEXT,
        responsible_name TEXT,
        movement_datetime TEXT,
        notes TEXT,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0,
        created_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS cocktail_recipes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT,
        restaurant_id TEXT,
        bar_id TEXT,
        code TEXT,
        name TEXT,
        category TEXT,
        cocktail_type TEXT,
        glass_type TEXT,
        serving_size_ml REAL DEFAULT 0,
        yield_qty REAL DEFAULT 1,
        yield_unit TEXT,
        alcohol_percentage_estimated REAL DEFAULT 0,
        difficulty TEXT,
        preparation_time_minutes REAL DEFAULT 0,
        seasonality TEXT,
        sale_price REAL DEFAULT 0,
        suggested_price REAL DEFAULT 0,
        target_margin_percent REAL DEFAULT 0,
        contingency_percent REAL DEFAULT 0,
        cost_2025_orientative REAL DEFAULT 0,
        cost_2026_net REAL DEFAULT 0,
        cost_2026_gross_with_waste REAL DEFAULT 0,
        margin_percent_2026 REAL DEFAULT 0,
        cost_per_ml REAL DEFAULT 0,
        contains_alcohol INTEGER DEFAULT 1,
        allergens_json TEXT,
        warnings_json TEXT,
        photo_path TEXT,
        notes TEXT,
        status TEXT,
        active INTEGER DEFAULT 1,
        created_by TEXT,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0,
        data_scope TEXT DEFAULT 'demo',
        created_at TEXT,
        updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,code)
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS cocktail_recipe_lines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cocktail_recipe_id INTEGER,
        origin TEXT,
        bar_item_id INTEGER,
        bar_production_id INTEGER,
        ingredient_name TEXT,
        qty_net REAL DEFAULT 0,
        unit TEXT,
        waste_percent REAL DEFAULT 0,
        qty_gross REAL DEFAULT 0,
        cost_unit_2026 REAL DEFAULT 0,
        cost_total_net_2026 REAL DEFAULT 0,
        cost_total_gross_2026 REAL DEFAULT 0,
        supplier_name_demo TEXT,
        stock_available REAL DEFAULT 0,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS cocktail_recipe_steps(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cocktail_recipe_id INTEGER,
        step_number INTEGER,
        instruction TEXT,
        demo_data INTEGER DEFAULT 0
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS cocktail_cost_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cocktail_recipe_id INTEGER,
        cost_per_serving_net_2026 REAL DEFAULT 0,
        cost_per_serving_gross_2026 REAL DEFAULT 0,
        sale_price REAL DEFAULT 0,
        margin_percent REAL DEFAULT 0,
        calculated_at TEXT,
        source TEXT,
        notes TEXT,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS bar_alerts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT,
        restaurant_id TEXT,
        bar_id TEXT,
        alert_code TEXT,
        alert_text TEXT,
        severity TEXT,
        blocking INTEGER DEFAULT 0,
        active INTEGER DEFAULT 1,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0,
        created_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,alert_code)
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS bar_tpv_mappings(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT,
        restaurant_id TEXT,
        bar_id TEXT,
        cocktail_recipe_id INTEGER,
        product_name_raw TEXT,
        product_code_raw TEXT,
        mapping_status TEXT,
        connection_status TEXT,
        demo_data INTEGER DEFAULT 0,
        non_productive_demo INTEGER DEFAULT 0,
        created_at TEXT,
        updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,product_code_raw)
    )''')


def _qty_gross(qty_net: float, waste_percent: float) -> float:
    w = max(0.0, min(99.0, _safe_float(waste_percent)))
    return _safe_float(qty_net) / (1.0 - (w / 100.0)) if w else _safe_float(qty_net)


ITEMS = [
('RON-BLANCO','Ron Blanco','botella_alcohol','alcoholes','ml','botella_700ml',700,12.63,13.29,0.01899,1,None,None,1400,4200,'almacén_bar'),
('GINEBRA','Ginebra','botella_alcohol','alcoholes','ml','botella_700ml',700,12.97,13.65,0.01950,1,None,None,1400,4200,'almacén_bar'),
('VODKA','Vodka','botella_alcohol','alcoholes','ml','botella_700ml',700,11.20,11.79,0.01684,1,None,None,700,2800,'almacén_bar'),
('TEQUILA-BLANCO','Tequila Blanco','botella_alcohol','alcoholes','ml','botella_700ml',700,11.35,11.95,0.01707,1,None,None,700,2800,'almacén_bar'),
('TRIPLE-SEC','Cointreau / Triple Sec','botella_alcohol','alcoholes','ml','botella_700ml',700,19.95,21.00,0.03000,1,None,None,700,2100,'almacén_bar'),
('VERMUT-ROJO-DEMO','Vermut Rojo Demo','botella_alcohol','alcoholes','ml','botella_1l',1000,11.07,11.65,0.01165,2,None,None,1000,3000,'cámara_bar'),
('VERMUT-SECO-DEMO','Vermut Seco Demo','botella_alcohol','alcoholes','ml','botella_1l',1000,11.07,11.65,0.01165,2,None,None,1000,3000,'cámara_bar'),
('CAMPARI','Campari','botella_alcohol','alcoholes','ml','botella_700ml',700,14.72,15.49,0.02213,1,None,None,700,2100,'almacén_bar'),
('BOURBON','Bourbon','botella_alcohol','alcoholes','ml','botella_700ml',700,14.96,15.75,0.02250,1,None,None,700,2100,'almacén_bar'),
('TONICA','Tónica','mixer','mixers','ml','botella_1l',1000,1.95,2.05,0.00205,3,None,None,3000,12000,'almacén_bar'),
('COLA','Cola','refresco','mixers','ml','pack_4l',4000,3.89,4.09,0.00102,3,None,None,4000,16000,'almacén_bar'),
('GINGER-BEER','Ginger Beer','mixer','mixers','ml','botella_200ml',200,1.71,1.80,0.00900,3,None,None,1000,4000,'almacén_bar'),
('SODA','Soda / Agua con Gas','mixer','mixers','ml','botella_1l',1000,0.95,1.00,0.00100,3,None,None,3000,12000,'almacén_bar'),
('AZUCAR-BLANCO','Azúcar Blanco','endulzante','syrups','gr','bolsa_1kg',1000,0.94,0.99,0.00099,0,None,None,1000,5000,'seco_bar'),
('AGUA-FILTRADA','Agua filtrada','agua','syrups','ml','red/filtrada',1000,0.00,0.00,0.00000,0,None,None,1000,10000,'barra'),
('LIMA','Lima','fruta_bar','frutas','gr','kg',1000,3.77,3.97,0.00397,12,40,0.00993,1000,5000,'cámara_bar'),
('LIMON','Limón','fruta_bar','frutas','gr','kg',1000,2.75,2.89,0.00289,10,45,0.00642,1000,5000,'cámara_bar'),
('NARANJA','Naranja','fruta_bar','frutas','gr','kg',1000,2.00,2.10,0.00210,12,50,0.00420,1000,5000,'cámara_bar'),
('HIERBABUENA','Hierbabuena','hierba','garnish','gr','manojo_100g',100,1.42,1.49,0.01490,18,None,None,100,500,'cámara_bar'),
('ANGOSTURA','Angostura','bitter','bitters','ml','botella_200ml',200,15.10,15.89,0.07945,1,None,None,200,600,'barra'),
('HIELO','Hielo','hielo','hielo','gr','bolsa_2kg',2000,1.43,1.50,0.00075,8,None,None,10000,40000,'congelado_bar'),
('ACEITUNA-GARNISH','Aceituna Garnish','garnish','garnish','gr','bote_200g',200,1.90,2.00,0.01000,5,None,None,200,1000,'cámara_bar'),
('SAL','Sal','especia','garnish','gr','paquete_1kg',1000,0.48,0.50,0.00050,0,None,None,1000,3000,'seco_bar'),
('ZUMO-ARANDANO','Zumo Arándano','zumo','mixers','ml','botella_750ml',750,2.38,2.50,0.00333,3,None,None,1500,6000,'cámara_bar'),
('RED-BULL','Red Bull Demo','energy_drink','mixers','ml','lata_250ml',250,1.14,1.20,0.00480,2,None,None,1500,6000,'almacén_bar'),
('WHISKY-ESCOCES','Whisky Escocés Demo','botella_alcohol','alcoholes','ml','botella_700ml',700,13.30,14.00,0.02000,1,None,None,700,2100,'almacén_bar'),
('VINO-BLANCO-DEMO','Vino Blanco Demo','vino','vinos','ml','botella_750ml',750,5.70,6.00,0.00800,3,None,None,1500,4500,'cámara_bar'),
('VINO-TINTO-DEMO','Vino Tinto Demo','vino','vinos','ml','botella_750ml',750,6.18,6.50,0.00867,3,None,None,1500,4500,'cámara_bar'),
('CERVEZA-BOTELLA-DEMO','Cerveza botella Demo','cerveza','cervezas','ml','botella_330ml',330,0.95,1.00,0.00303,1,None,None,3300,9900,'almacén_bar'),
('CERVEZA-BARRIL-DEMO','Cerveza barril Demo','cerveza_barril','cervezas','ml','barril_30l',30000,61.75,65.00,0.00217,8,None,None,30000,90000,'cámara_bar'),
]

INITIAL_STOCK = {'Ron Blanco':4200,'Ginebra':4200,'Vodka':2800,'Tequila Blanco':2800,'Cointreau / Triple Sec':2100,'Vermut Rojo Demo':3000,'Vermut Seco Demo':3000,'Campari':2100,'Bourbon':2100,'Tónica':12000,'Cola':16000,'Ginger Beer':4000,'Soda / Agua con Gas':12000,'Azúcar Blanco':5000,'Agua filtrada':10000,'Lima':5000,'Limón':5000,'Naranja':5000,'Hierbabuena':500,'Angostura':600,'Hielo':40000,'Aceituna Garnish':1000,'Sal':3000,'Zumo Arándano':6000,'Red Bull Demo':6000,'Whisky Escocés Demo':2100,'Vino Blanco Demo':4500,'Vino Tinto Demo':4500,'Cerveza botella Demo':9900,'Cerveza barril Demo':90000}

PRODUCTIONS = [
('BAR-PREP-SYRUP-001','Syrup simple 1:1','syrup',750,'ml',2,7,'cámara_bar','Producción demo. Fórmula orientativa con azúcar y agua. Ajustar rendimiento real según evaporación y método.', [('Azúcar Blanco',500,'gr',0),('Agua filtrada',500,'ml',0)], ['Calentar agua sin hervir agresivamente.','Añadir azúcar.','Remover hasta disolver por completo.','Enfriar rápidamente.','Envasar, etiquetar y guardar en frío.','Registrar fecha de producción y caducidad.']),
('BAR-PREP-LIME-001','Zumo de lima exprimido','zumo_preparado',400,'ml',12,1,'cámara_bar','Rendimiento demo: 1 kg lima = 400 ml zumo. Ajustar con datos reales por calibre/proveedor.', [('Lima',1000,'gr',12)], ['Lavar limas.','Cortar.','Exprimir.','Colar si procede.','Envasar.','Etiquetar con fecha y hora.','Usar preferentemente el mismo día.']),
('BAR-PREP-LEMON-001','Zumo de limón exprimido','zumo_preparado',450,'ml',10,1,'cámara_bar','Rendimiento demo: 1 kg limón = 450 ml zumo. Ajustar con datos reales.', [('Limón',1000,'gr',10)], ['Lavar limones.','Cortar.','Exprimir.','Colar si procede.','Envasar.','Etiquetar con fecha y hora.','Usar preferentemente el mismo día.']),
('BAR-PREP-GARNISH-LIME-001','Garnish de lima preparado','garnish_preparado',880,'gr',12,1,'cámara_bar','Considera 12 % merma por puntas, pérdida, oxidación y descarte.', [('Lima',1000,'gr',12)], ['Lavar limas.','Cortar rodajas o gajos.','Retirar piezas defectuosas.','Guardar en recipiente cerrado.','Etiquetar con fecha y hora.']),
('BAR-PREP-GARNISH-ORANGE-001','Garnish de naranja preparado','garnish_preparado',880,'gr',12,1,'cámara_bar','Garnish demo para Negroni y Old Fashioned.', [('Naranja',1000,'gr',12)], ['Lavar naranjas.','Cortar pieles, twists o medias rodajas según estándar.','Descartar partes dañadas.','Guardar tapado y etiquetado.']),
('BAR-PREP-GARNISH-LEMON-001','Garnish de limón preparado','garnish_preparado',900,'gr',10,1,'cámara_bar','Garnish demo para Gin Tonic. Separado de Cocina.', [('Limón',1000,'gr',10)], ['Lavar limones.','Cortar pieles o rodajas según estándar.','Descartar partes dañadas.','Guardar tapado y etiquetado.']),
]

RECIPES = [
('CCT-MOJ-001','Mojito Clásico','clásico','long drink','highball / collins',350,1,'copa',7,'fácil',3,'todo el año / verano',9.50,80,5,1.45,['alcohol'],[], [('stock','Ron Blanco',50,'ml',1),('production','BAR-PREP-LIME-001',25,'ml',0),('production','BAR-PREP-SYRUP-001',20,'ml',2),('stock','Hierbabuena',3,'gr',18),('stock','Soda / Agua con Gas',100,'ml',3),('stock','Hielo',180,'gr',8),('production','BAR-PREP-GARNISH-LIME-001',10,'gr',0)], ['Colocar hierbabuena en el vaso.','Añadir syrup y zumo de lima.','Machacar suavemente sin romper demasiado la hierbabuena.','Añadir ron blanco.','Llenar con hielo.','Completar con soda.','Remover suavemente.','Decorar con garnish de lima y hierbabuena.']),
('CCT-MAR-001','Margarita','clásico','sour / all day','coupette / margarita',120,1,'copa',20,'media',3,'todo el año',10.50,80,5,1.91,['alcohol'],[], [('stock','Tequila Blanco',50,'ml',1),('stock','Cointreau / Triple Sec',25,'ml',1),('production','BAR-PREP-LIME-001',25,'ml',0),('production','BAR-PREP-SYRUP-001',5,'ml',2),('stock','Sal',2,'gr',0),('stock','Hielo',150,'gr',8),('production','BAR-PREP-GARNISH-LIME-001',10,'gr',0)], ['Enfriar la copa.','Escarchar borde con sal.','Añadir tequila, Cointreau, lima y syrup a la coctelera.','Agitar con hielo.','Colar en copa fría.','Decorar con lima.']),
('CCT-DAI-001','Daiquiri','clásico','sour','coupette',100,1,'copa',22,'fácil',2,'todo el año',9.00,80,5,1.45,['alcohol'],[], [('stock','Ron Blanco',60,'ml',1),('production','BAR-PREP-LIME-001',25,'ml',0),('production','BAR-PREP-SYRUP-001',15,'ml',2),('stock','Hielo',150,'gr',8),('production','BAR-PREP-GARNISH-LIME-001',5,'gr',0)], ['Añadir ron, lima y syrup a la coctelera.','Agitar con hielo.','Doble colado.','Servir en copa fría.','Decorar opcionalmente con lima.']),
('CCT-NEG-001','Negroni','clásico','aperitivo','old fashioned',90,1,'copa',24,'fácil',2,'todo el año',11.00,80,5,1.66,['alcohol'],['sulfitos'], [('stock','Ginebra',30,'ml',1),('stock','Campari',30,'ml',1),('stock','Vermut Rojo Demo',30,'ml',2),('stock','Hielo',150,'gr',8),('production','BAR-PREP-GARNISH-ORANGE-001',15,'gr',0)], ['Añadir ginebra, Campari y vermut en vaso.','Agregar hielo.','Remover hasta enfriar.','Decorar con naranja.']),
('CCT-OLD-001','Old Fashioned','clásico','short drink','old fashioned',70,1,'copa',30,'media',4,'todo el año',11.50,80,5,1.54,['alcohol'],[], [('stock','Bourbon',60,'ml',1),('stock','Angostura',1.6,'ml',1),('stock','Azúcar Blanco',4,'gr',0),('stock','Hielo',150,'gr',8),('production','BAR-PREP-GARNISH-ORANGE-001',10,'gr',0)], ['Añadir azúcar y Angostura al vaso.','Integrar hasta disolver.','Añadir bourbon.','Agregar hielo grande.','Remover.','Perfumar con piel de naranja.']),
('CCT-MAR-D-001','Dry Martini','clásico','martini','martini / nick & nora',70,1,'copa',32,'media',3,'todo el año',10.50,80,5,1.42,['alcohol'],['sulfitos'], [('stock','Ginebra',60,'ml',1),('stock','Vermut Seco Demo',10,'ml',2),('stock','Aceituna Garnish',10,'gr',5),('stock','Hielo',150,'gr',8)], ['Enfriar copa.','Añadir ginebra y vermut al vaso mezclador.','Remover con hielo.','Colar en copa fría.','Decorar con aceituna o twist.']),
('CCT-MOS-001','Moscow Mule','clásico','long drink','mug / rocks',190,1,'copa',10,'fácil',2,'todo el año',10.50,78,5,2.13,['alcohol'],[], [('stock','Vodka',50,'ml',1),('production','BAR-PREP-LIME-001',15,'ml',0),('stock','Ginger Beer',120,'ml',3),('stock','Hielo',180,'gr',8),('production','BAR-PREP-GARNISH-LIME-001',10,'gr',0)], ['Llenar mug con hielo.','Añadir vodka.','Añadir zumo de lima.','Completar con ginger beer.','Remover suavemente.','Decorar con lima.']),
('CCT-COS-001','Cosmopolitan','clásico','contemporary classic','cocktail / martini',105,1,'copa',20,'media',3,'todo el año',10.50,80,5,1.51,['alcohol'],[], [('stock','Vodka',45,'ml',1),('stock','Cointreau / Triple Sec',15,'ml',1),('production','BAR-PREP-LIME-001',15,'ml',0),('stock','Zumo Arándano',30,'ml',3),('stock','Hielo',150,'gr',8),('production','BAR-PREP-GARNISH-LIME-001',5,'gr',0)], ['Añadir vodka, Cointreau, lima y arándano en coctelera.','Agitar con hielo.','Colar en copa fría.','Decorar con twist.']),
('CCT-GT-001','Gin Tonic','clásico','long drink','balón / highball',250,1,'copa',8,'fácil',2,'todo el año',9.50,80,5,1.47,['alcohol'],[], [('stock','Ginebra',50,'ml',1),('stock','Tónica',200,'ml',3),('stock','Hielo',180,'gr',8),('production','BAR-PREP-GARNISH-LEMON-001',10,'gr',0)], ['Llenar copa con hielo.','Añadir ginebra.','Completar con tónica.','Integrar suavemente sin romper burbuja.','Decorar con limón.']),
('CCT-CUB-001','Cuba Libre','clásico','long drink','highball',210,1,'copa',9,'fácil',2,'todo el año',8.50,80,5,1.31,['alcohol','cafeína por cola'],[], [('stock','Ron Blanco',50,'ml',1),('stock','Cola',150,'ml',3),('production','BAR-PREP-LIME-001',10,'ml',0),('stock','Hielo',180,'gr',8),('production','BAR-PREP-GARNISH-LIME-001',10,'gr',0)], ['Llenar vaso highball con hielo.','Añadir ron.','Añadir lima.','Completar con cola.','Remover suavemente.','Decorar con lima.']),
]


def _upsert_item(cur, row) -> int:
    now = _now()
    code,name,item_type,family,base_unit,purchase_unit,purchase_qty,p25,p26,cost,waste,juice_yield,juice_cost,min_stock,max_stock,location = row
    norm = _norm(name)
    cur.execute('''INSERT INTO bar_items(business_id,restaurant_id,bar_id,code,name,normalized_name,item_type,family,base_unit,purchase_unit,purchase_qty,purchase_price_2025,purchase_price_2026,cost_per_base_unit_2026,standard_waste_percent,juice_yield_percent,juice_cost_per_ml_2026,supplier_name_demo,min_stock,max_stock,location,active,demo_data,non_productive_demo,data_scope,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(business_id,restaurant_id,bar_id,normalized_name) DO UPDATE SET code=excluded.code,item_type=excluded.item_type,family=excluded.family,base_unit=excluded.base_unit,purchase_unit=excluded.purchase_unit,purchase_qty=excluded.purchase_qty,purchase_price_2025=excluded.purchase_price_2025,purchase_price_2026=excluded.purchase_price_2026,cost_per_base_unit_2026=excluded.cost_per_base_unit_2026,standard_waste_percent=excluded.standard_waste_percent,juice_yield_percent=excluded.juice_yield_percent,juice_cost_per_ml_2026=excluded.juice_cost_per_ml_2026,min_stock=excluded.min_stock,max_stock=excluded.max_stock,location=excluded.location,active=1,demo_data=1,non_productive_demo=1,updated_at=excluded.updated_at''',
                (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,code,name,norm,item_type,family,base_unit,purchase_unit,purchase_qty,p25,p26,cost,waste,juice_yield,juice_cost,DEMO_PROVIDER,min_stock,max_stock,location,1,1,1,'demo',now,now))
    r = cur.execute('SELECT id FROM bar_items WHERE business_id=? AND restaurant_id=? AND bar_id=? AND normalized_name=?', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,norm)).fetchone()
    return int(r['id'])


def _item_by_name(cur, name: str):
    return cur.execute('SELECT * FROM bar_items WHERE business_id=? AND restaurant_id=? AND bar_id=? AND normalized_name=?', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,_norm(name))).fetchone()


def _prod_by_code(cur, code: str):
    return cur.execute('SELECT * FROM bar_productions WHERE business_id=? AND restaurant_id=? AND bar_id=? AND code=?', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,code)).fetchone()


def load_cocktail_bar_demo() -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_bar_schema(cur); now = _now()
    try:
        cur.execute('INSERT OR REPLACE INTO bar_businesses(business_id,business_name,demo_data,non_productive_demo,data_scope,created_at,updated_at) VALUES(?,?,?,?,?,?,?)', (DEMO_BUSINESS_ID,'Negocio Demo Coctelería',1,1,'demo',now,now))
        cur.execute('''INSERT INTO bar_locations(business_id,restaurant_id,restaurant_name,bar_id,bar_name,demo_data,non_productive_demo,active,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(business_id,restaurant_id,bar_id) DO UPDATE SET restaurant_name=excluded.restaurant_name,bar_name=excluded.bar_name,demo_data=1,non_productive_demo=1,active=1,updated_at=excluded.updated_at''', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,'Local Demo Barra',DEMO_BAR_ID,'Barra Principal Demo',1,1,1,now,now))
        item_ids = {}
        for row in ITEMS:
            item_ids[row[1]] = _upsert_item(cur, row)
        cur.execute("DELETE FROM bar_stock_movements WHERE business_id=? AND restaurant_id=? AND bar_id=? AND source_module='carga_demo_cocteleria'", (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID))
        for name, qty in INITIAL_STOCK.items():
            it = _item_by_name(cur, name)
            if not it: continue
            cur.execute('''INSERT INTO bar_stock_movements(business_id,restaurant_id,bar_id,bar_item_id,movement_type,qty,unit,document_code,source_module,responsible_name,movement_datetime,notes,demo_data,non_productive_demo,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                        (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,int(it['id']),'entrada',qty,it['base_unit'],'ALB-BAR-DEMO-2026-0001','carga_demo_cocteleria','Sistema Demo',now,'Stock inicial demo no productivo.',1,1,now))
        prod_count = 0
        for code,name,ptype,yqty,yunit,waste,shelf,loc,notes,lines,steps in PRODUCTIONS:
            total = 0.0; line_calc=[]
            for iname,qty,unit,lwaste in lines:
                it=_item_by_name(cur,iname); cost=float(it['cost_per_base_unit_2026'] if it else 0)
                qg=_qty_gross(qty,lwaste); net=float(qty)*cost; gross=qg*cost; total += gross
                line_calc.append((it, iname, qty, unit, lwaste, qg, cost, net, gross))
            cpu = total / float(yqty or 1)
            cur.execute('''INSERT INTO bar_productions(business_id,restaurant_id,bar_id,code,name,production_type,yield_qty,yield_unit,cost_total_2026,cost_per_unit_2026,standard_waste_percent,shelf_life_days,lot,responsible,storage_location,procedure_text,status,stock_actual,used_in_recipes,es_vendible,sale_price,notes,demo_data,non_productive_demo,data_scope,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(business_id,restaurant_id,bar_id,code) DO UPDATE SET name=excluded.name,production_type=excluded.production_type,yield_qty=excluded.yield_qty,yield_unit=excluded.yield_unit,cost_total_2026=excluded.cost_total_2026,cost_per_unit_2026=excluded.cost_per_unit_2026,standard_waste_percent=excluded.standard_waste_percent,shelf_life_days=excluded.shelf_life_days,responsible=excluded.responsible,storage_location=excluded.storage_location,procedure_text=excluded.procedure_text,status=excluded.status,stock_actual=excluded.stock_actual,used_in_recipes=excluded.used_in_recipes,es_vendible=0,sale_price=NULL,notes=excluded.notes,demo_data=1,non_productive_demo=1,updated_at=excluded.updated_at''',
                        (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,code,name,ptype,yqty,yunit,total,cpu,waste,shelf,f"DEMO-{code}",'Sistema Demo',loc,'\n'.join(f"{i+1}. {s}" for i,s in enumerate(steps)),'plantilla_demo',yqty,'',0,None,notes,1,1,'demo',now,now))
            prod=_prod_by_code(cur,code); pid=int(prod['id']); prod_count+=1
            cur.execute('DELETE FROM bar_production_lines WHERE bar_production_id=?', (pid,))
            for it,iname,qty,unit,lwaste,qg,cost,net,gross in line_calc:
                cur.execute('''INSERT INTO bar_production_lines(bar_production_id,bar_item_id,item_name,qty_net,unit,waste_percent,qty_gross,cost_unit_2026,cost_total_net_2026,cost_total_gross_2026,notes,demo_data,non_productive_demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', (pid, int(it['id']) if it else None, iname, qty, unit, lwaste, qg, cost, net, gross, 'Línea demo no productiva.',1,1))
            cur.execute('DELETE FROM bar_production_stock_movements WHERE bar_production_id=? AND source_module=?', (pid,'carga_demo_cocteleria'))
            cur.execute('''INSERT INTO bar_production_stock_movements(business_id,restaurant_id,bar_id,bar_production_id,movement_type,qty,unit,source_module,responsible_name,movement_datetime,notes,demo_data,non_productive_demo,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,pid,'entrada_demo',yqty,yunit,'carga_demo_cocteleria','Sistema Demo',now,'Stock inicial de preparado demo; no descuenta insumos reales.',1,1,now))
        recipe_count=0; line_count=0; step_count=0
        for rec in RECIPES:
            code,name,cat,ctype,glass,serving,yqty,yunit,abv,diff,ptime,season,sale,target,cont,cost25,warnings,allergens,ingredients,steps = rec
            cur.execute('''INSERT INTO cocktail_recipes(business_id,restaurant_id,bar_id,code,name,category,cocktail_type,glass_type,serving_size_ml,yield_qty,yield_unit,alcohol_percentage_estimated,difficulty,preparation_time_minutes,seasonality,sale_price,suggested_price,target_margin_percent,contingency_percent,cost_2025_orientative,cost_2026_net,cost_2026_gross_with_waste,margin_percent_2026,cost_per_ml,contains_alcohol,allergens_json,warnings_json,photo_path,notes,status,active,created_by,demo_data,non_productive_demo,data_scope,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(business_id,restaurant_id,bar_id,code) DO UPDATE SET name=excluded.name,category=excluded.category,cocktail_type=excluded.cocktail_type,glass_type=excluded.glass_type,serving_size_ml=excluded.serving_size_ml,sale_price=excluded.sale_price,target_margin_percent=excluded.target_margin_percent,contingency_percent=excluded.contingency_percent,cost_2025_orientative=excluded.cost_2025_orientative,contains_alcohol=1,allergens_json=excluded.allergens_json,warnings_json=excluded.warnings_json,photo_path=excluded.photo_path,notes=excluded.notes,status='activo',active=1,demo_data=1,non_productive_demo=1,updated_at=excluded.updated_at''',
                        (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,code,name,cat,ctype,glass,serving,yqty,yunit,abv,diff,ptime,season,sale,0,target,cont,cost25,0,0,0,0,1,_j(allergens),_j(warnings),'pendiente_subir','Cóctel demo no productivo. Precios 2026 orientativos.','activo',1,'Sistema Demo',1,1,'demo',now,now))
            crow=cur.execute('SELECT id FROM cocktail_recipes WHERE business_id=? AND restaurant_id=? AND bar_id=? AND code=?', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,code)).fetchone(); rid=int(crow['id']); recipe_count+=1
            cur.execute('DELETE FROM cocktail_recipe_lines WHERE cocktail_recipe_id=?', (rid,)); cur.execute('DELETE FROM cocktail_recipe_steps WHERE cocktail_recipe_id=?', (rid,))
            net_total=0.0; gross_total=0.0
            for origin, ref, qty, unit, lwaste in ingredients:
                bid=None; pid=None; iname=ref; stock_avail=0.0; supplier=DEMO_PROVIDER
                if origin=='stock':
                    it=_item_by_name(cur,ref); bid=int(it['id']) if it else None; cost=float(it['cost_per_base_unit_2026'] if it else 0); iname=it['name'] if it else ref
                    bal=cur.execute("SELECT COALESCE(SUM(CASE WHEN movement_type LIKE 'entrada%' THEN qty ELSE -qty END),0) q FROM bar_stock_movements WHERE bar_item_id=?", (bid or 0,)).fetchone(); stock_avail=float(bal['q'] or 0)
                else:
                    pr=_prod_by_code(cur,ref); pid=int(pr['id']) if pr else None; cost=float(pr['cost_per_unit_2026'] if pr else 0); iname=pr['name'] if pr else ref; supplier='Producción Bar interna demo'
                    bal=cur.execute("SELECT COALESCE(SUM(CASE WHEN movement_type LIKE 'entrada%' THEN qty ELSE -qty END),0) q FROM bar_production_stock_movements WHERE bar_production_id=?", (pid or 0,)).fetchone(); stock_avail=float(bal['q'] or 0)
                qg=_qty_gross(qty,lwaste); net=float(qty)*cost; gross=qg*cost; net_total += net; gross_total += gross; line_count+=1
                cur.execute('''INSERT INTO cocktail_recipe_lines(cocktail_recipe_id,origin,bar_item_id,bar_production_id,ingredient_name,qty_net,unit,waste_percent,qty_gross,cost_unit_2026,cost_total_net_2026,cost_total_gross_2026,supplier_name_demo,stock_available,demo_data,non_productive_demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                            (rid, 'stock_bar' if origin=='stock' else 'producción_bar', bid, pid, iname, qty, unit, lwaste, qg, cost, net, gross, supplier, stock_avail,1,1))
            margin = ((sale - gross_total) / sale * 100.0) if sale else 0.0
            suggested = gross_total / (1.0 - target/100.0) if target < 100 else 0.0
            cost_ml = gross_total / float(serving or 1)
            cur.execute('UPDATE cocktail_recipes SET suggested_price=?,cost_2026_net=?,cost_2026_gross_with_waste=?,margin_percent_2026=?,cost_per_ml=? WHERE id=?', (suggested,net_total,gross_total,margin,cost_ml,rid))
            for i,s in enumerate(steps,1):
                step_count+=1; cur.execute('INSERT INTO cocktail_recipe_steps(cocktail_recipe_id,step_number,instruction,demo_data) VALUES(?,?,?,1)', (rid,i,s))
            cur.execute('DELETE FROM cocktail_cost_history WHERE cocktail_recipe_id=? AND source=?', (rid,'carga_demo_cocteleria'))
            cur.execute('''INSERT INTO cocktail_cost_history(cocktail_recipe_id,cost_per_serving_net_2026,cost_per_serving_gross_2026,sale_price,margin_percent,calculated_at,source,notes,demo_data,non_productive_demo) VALUES(?,?,?,?,?,?,?,?,?,?)''', (rid,net_total,gross_total,sale,margin,now,'carga_demo_cocteleria','Simulacro con precios orientativos. Sustituir por albaranes reales antes de producción.',1,1))
            cur.execute('''INSERT INTO bar_tpv_mappings(business_id,restaurant_id,bar_id,cocktail_recipe_id,product_name_raw,product_code_raw,mapping_status,connection_status,demo_data,non_productive_demo,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(business_id,restaurant_id,bar_id,product_code_raw) DO UPDATE SET cocktail_recipe_id=excluded.cocktail_recipe_id,product_name_raw=excluded.product_name_raw,mapping_status='preparado_demo',connection_status='TPV_NO_CONECTADO',updated_at=excluded.updated_at''', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,rid,name,code,'preparado_demo','TPV_NO_CONECTADO',1,1,now,now))
        alerts = {
            'PRECIOS_DEMO':'Los precios de estos escandallos son orientativos. Sustituir por albaranes reales antes de uso productivo.',
            'MERMAS_ORIENTATIVAS':'Los porcentajes de merma son estándar operativos. Ajustar por proveedor, temporada, calibre y método de trabajo.',
            'FOTO_PENDIENTE':'Receta sin foto real cargada.',
            'TPV_NO_CONECTADO':'Receta preparada para futuro mapeo TPV, sin conexión real activa.',
            'STOCK_DEMO':'Stock inicial creado como simulacro. No usar para inventario real.',
            'PRODUCCIONES_BAR_DEMO':'Las Producciones Bar cargadas son subrecetas internas a coste, no productos vendibles.',
        }
        for code,txt in alerts.items():
            cur.execute('''INSERT INTO bar_alerts(business_id,restaurant_id,bar_id,alert_code,alert_text,severity,blocking,active,demo_data,non_productive_demo,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(business_id,restaurant_id,bar_id,alert_code) DO UPDATE SET alert_text=excluded.alert_text,active=1,demo_data=1,non_productive_demo=1''', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,code,txt,'info',0,1,1,1,now))
        conn.commit()
        return {'ok': True, 'message': 'Demo Coctelería / Barra cargada correctamente. No productivo.', 'items': len(ITEMS), 'stock_movements': len(INITIAL_STOCK), 'productions': prod_count, 'cocktail_recipes': recipe_count, 'recipe_lines': line_count, 'steps': step_count, 'alerts': len(alerts), 'cost_history': recipe_count, 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    except Exception as exc:
        conn.rollback()
        return {'ok': False, 'message': f'Error cargando demo de Coctelería: {exc}'}
    finally:
        conn.close()


def get_bar_summary() -> Dict[str, Any]:
    conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
    try:
        # Auto-semilla segura: solo demo/no productivo y con upsert; no toca cocina.
        c=cur.execute('SELECT COUNT(*) c FROM cocktail_recipes WHERE business_id=? AND restaurant_id=? AND bar_id=? AND demo_data=1', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID)).fetchone()
        if int(c['c'] or 0) == 0:
            conn.close()
            load_cocktail_bar_demo()
            conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
        counts={}
        for key,table in [('items','bar_items'),('stock_movements','bar_stock_movements'),('productions','bar_productions'),('recipes','cocktail_recipes'),('recipe_lines','cocktail_recipe_lines'),('steps','cocktail_recipe_steps'),('alerts','bar_alerts'),('cost_history','cocktail_cost_history')]:
            row=cur.execute(f'SELECT COUNT(*) c FROM {table} WHERE demo_data=1').fetchone(); counts[key]=int(row['c'] or 0)
        recs=[dict(r) for r in cur.execute('SELECT id,code,name,sale_price,suggested_price,cost_2026_gross_with_waste,margin_percent_2026,photo_path FROM cocktail_recipes WHERE demo_data=1 ORDER BY name LIMIT 50').fetchall()]
        prods=[dict(r) for r in cur.execute('SELECT code,name,yield_qty,yield_unit,cost_total_2026,cost_per_unit_2026,es_vendible,status,stock_actual FROM bar_productions WHERE demo_data=1 ORDER BY name').fetchall()]
        alerts=[dict(r) for r in cur.execute('SELECT alert_code,alert_text FROM bar_alerts WHERE demo_data=1 AND active=1 ORDER BY alert_code').fetchall()]
        return {'ok': True, 'business':'Negocio Demo Coctelería', 'bar':'Barra Principal Demo', 'counts': counts, 'recipes': recs, 'productions': prods, 'alerts': alerts, 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    finally:
        conn.close()


def get_cocktail_detail(recipe_id: int) -> Dict[str, Any]:
    conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
    try:
        rec=cur.execute('SELECT * FROM cocktail_recipes WHERE id=?', (int(recipe_id),)).fetchone()
        if not rec: return {'ok': False, 'message': 'Cóctel no encontrado.'}
        lines=[dict(r) for r in cur.execute('SELECT * FROM cocktail_recipe_lines WHERE cocktail_recipe_id=? ORDER BY id', (int(recipe_id),)).fetchall()]
        steps=[dict(r) for r in cur.execute('SELECT step_number,instruction FROM cocktail_recipe_steps WHERE cocktail_recipe_id=? ORDER BY step_number', (int(recipe_id),)).fetchall()]
        recipe = dict(rec)
        abv_calc = _cocktail_abv_from_lines(lines, recipe.get('serving_size_ml') or 0)
        recipe['alcohol_percentage_calculated'] = abv_calc
        recipe['alcohol_percentage_estimated'] = abv_calc or recipe.get('alcohol_percentage_estimated') or 0
        recipe['photo_status'] = 'pendiente_subir' if not recipe.get('photo_path') or recipe.get('photo_path') == 'pendiente_subir' else 'foto_cargada'
        return {'ok': True, 'recipe': recipe, 'lines': lines, 'steps': steps, 'calculation_rules': ['Alcohol % = ml alcohol puro / ml bebida servida x 100', 'ABV demo/orientativo hasta cargar fichas reales de botella', 'No toca Cocina ni Stock real']}
    finally:
        conn.close()



# ==============================================================================
# EDITOR FICHA TÉCNICA CÓCTELES · LAB NO PRODUCTIVO
# ==============================================================================

def _code_from_name(name: str) -> str:
    base = _norm(name).upper().replace(' ', '-')[:40] or 'COCKTAIL'
    return 'CCT-' + base


def _resolve_bar_source(cur, origin: str, ingredient_name: str):
    o = (origin or '').strip().lower()
    n = _norm(ingredient_name)
    if o in ('produccion_bar','producción_bar','bar_production','production_bar'):
        row = None
        for r in cur.execute('SELECT id,name,cost_per_unit_2026,stock_actual FROM bar_productions WHERE business_id=? AND restaurant_id=? AND bar_id=?',
                             (DEMO_BUSINESS_ID, DEMO_RESTAURANT_ID, DEMO_BAR_ID)).fetchall():
            if _norm(r['name']) == n:
                row = r; break
        if row:
            return 'produccion_bar', None, int(row['id']), float(row['cost_per_unit_2026'] or 0), 'Producción Bar', float(row['stock_actual'] or 0)
    row = cur.execute('SELECT id,name,cost_per_base_unit_2026,supplier_name_demo FROM bar_items WHERE business_id=? AND restaurant_id=? AND bar_id=? AND normalized_name=?',
                      (DEMO_BUSINESS_ID, DEMO_RESTAURANT_ID, DEMO_BAR_ID, n)).fetchone()
    if row:
        stock = cur.execute("SELECT COALESCE(SUM(CASE WHEN movement_type='entrada' THEN qty ELSE -qty END),0) q FROM bar_stock_movements WHERE bar_item_id=?", (int(row['id']),)).fetchone()
        return 'stock_bar', int(row['id']), None, float(row['cost_per_base_unit_2026'] or 0), row['supplier_name_demo'] or DEMO_PROVIDER, float(stock['q'] or 0)
    return (o or 'stock_bar'), None, None, 0.0, DEMO_PROVIDER, 0.0


def _recalculate_cocktail(cur, cocktail_recipe_id: int) -> None:
    lines = [dict(r) for r in cur.execute('SELECT * FROM cocktail_recipe_lines WHERE cocktail_recipe_id=? ORDER BY id', (int(cocktail_recipe_id),)).fetchall()]
    net = sum(float(x.get('cost_total_net_2026') or 0) for x in lines)
    gross = sum(float(x.get('cost_total_gross_2026') or 0) for x in lines)
    rec = cur.execute('SELECT serving_size_ml,sale_price,target_margin_percent FROM cocktail_recipes WHERE id=?', (int(cocktail_recipe_id),)).fetchone()
    if not rec:
        return
    sale = float(rec['sale_price'] or 0)
    target = float(rec['target_margin_percent'] or 0)
    margin = ((sale - gross) / sale * 100.0) if sale else 0.0
    suggested = (gross / (1.0 - target / 100.0)) if target and target < 100 else sale
    serving = float(rec['serving_size_ml'] or 0)
    cost_per_ml = gross / serving if serving else 0.0
    abv = _cocktail_abv_from_lines(lines, serving)
    cur.execute("""UPDATE cocktail_recipes SET cost_2026_net=?,cost_2026_gross_with_waste=?,margin_percent_2026=?,suggested_price=?,cost_per_ml=?,alcohol_percentage_estimated=?,updated_at=? WHERE id=?""",
                (round(net, 6), round(gross, 6), round(margin, 3), round(suggested, 3), round(cost_per_ml, 6), round(abv, 2), _now(), int(cocktail_recipe_id)))
    cur.execute("""INSERT INTO cocktail_cost_history(cocktail_recipe_id,cost_per_serving_net_2026,cost_per_serving_gross_2026,sale_price,margin_percent,calculated_at,source,notes,demo_data,non_productive_demo)
                   VALUES(?,?,?,?,?,?,?,?,?,?)""",
                (int(cocktail_recipe_id), round(net, 6), round(gross, 6), sale, round(margin,3), _now(), 'editor_ficha_coctel_lab', 'Recalculo al guardar ficha/linea. No productivo.', 1, 1))


def search_cocktails(q: str = '') -> Dict[str, Any]:
    conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
    try:
        term = '%' + (q or '').strip().lower() + '%'
        rows = [dict(r) for r in cur.execute("""SELECT id,code,name,category,cocktail_type,sale_price,cost_2026_gross_with_waste,margin_percent_2026,alcohol_percentage_estimated,photo_path
                                                FROM cocktail_recipes
                                                WHERE business_id=? AND restaurant_id=? AND bar_id=? AND active=1 AND lower(name) LIKE ?
                                                ORDER BY name LIMIT 50""",
                                                (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,term)).fetchall()]
        return {'ok': True, 'recipes': rows, 'query': q or ''}
    finally:
        conn.close()


def get_bar_editor_options() -> Dict[str, Any]:
    conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
    try:
        if int(cur.execute('SELECT COUNT(*) c FROM bar_items WHERE demo_data=1').fetchone()['c'] or 0) == 0:
            conn.close(); load_cocktail_bar_demo(); conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
        items=[dict(r) for r in cur.execute('SELECT id,name,base_unit,cost_per_base_unit_2026,standard_waste_percent,family,item_type FROM bar_items WHERE active=1 ORDER BY name').fetchall()]
        prods=[dict(r) for r in cur.execute('SELECT id,code,name,yield_unit,cost_per_unit_2026,standard_waste_percent,production_type FROM bar_productions WHERE es_vendible=0 ORDER BY name').fetchall()]
        return {'ok': True, 'items': items, 'productions': prods, 'origins': ['stock_bar','produccion_bar']}
    finally:
        conn.close()


def _unique_cocktail_code(cur, base_code: str, exclude_id: int = 0) -> str:
    base = (base_code or 'CCT-LAB').strip().upper()[:32] or 'CCT-LAB'
    code = base
    i = 2
    while True:
        row = cur.execute('SELECT id FROM cocktail_recipes WHERE business_id=? AND restaurant_id=? AND bar_id=? AND code=?', (DEMO_BUSINESS_ID, DEMO_RESTAURANT_ID, DEMO_BAR_ID, code)).fetchone()
        if not row or int(row['id']) == int(exclude_id or 0):
            return code
        suffix = f'-{i}'
        code = (base[:max(1, 32-len(suffix))] + suffix).upper()
        i += 1

def _allowed_bar_unit(default_unit: str) -> str:
    u = (default_unit or '').strip().lower()
    if u in ('ml','gr','ud'):
        return u
    if u in ('g','gramo','gramos'):
        return 'gr'
    if u in ('unidad','unidades','u'):
        return 'ud'
    return 'ml'

def _normalized_cocktail_name_exists(cur, name: str, exclude_id: int = 0) -> bool:
    wanted = _norm(name)
    rows = cur.execute('SELECT id,name FROM cocktail_recipes WHERE business_id=? AND restaurant_id=? AND bar_id=? AND active=1', (DEMO_BUSINESS_ID, DEMO_RESTAURANT_ID, DEMO_BAR_ID)).fetchall()
    for r in rows:
        if int(r['id']) != int(exclude_id or 0) and _norm(r['name']) == wanted:
            return True
    return False

def save_cocktail(payload: Dict[str, Any]) -> Dict[str, Any]:
    conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
    try:
        rid = int(payload.get('id') or 0)
        name = (payload.get('name') or '').strip()
        if not name:
            return {'ok': False, 'message': 'Nombre requerido.'}
        if _normalized_cocktail_name_exists(cur, name, int(payload.get('id') or 0)):
            return {'ok': False, 'message': 'Ya existe un cóctel demo con ese nombre.'}
        now = _now()
        existing_code = ''
        if rid > 0:
            row = cur.execute('SELECT code FROM cocktail_recipes WHERE id=?', (rid,)).fetchone()
            existing_code = (row['code'] if row else '') or ''
        generated_code = _unique_cocktail_code(cur, existing_code or _code_from_name(name), rid)
        vals = {
            'code': generated_code,
            'name': name,
            'category': (payload.get('category') or 'clásico').strip(),
            'cocktail_type': (payload.get('cocktail_type') or '').strip(),
            'glass_type': (payload.get('glass_type') or '').strip(),
            'serving_size_ml': _safe_float(payload.get('serving_size_ml'), 0),
            'yield_qty': _safe_float(payload.get('yield_qty'), 1),
            'yield_unit': (payload.get('yield_unit') or 'copa').strip(),
            'difficulty': (payload.get('difficulty') or '').strip(),
            'preparation_time_minutes': _safe_float(payload.get('preparation_time_minutes'), 0),
            'seasonality': (payload.get('seasonality') or '').strip(),
            'sale_price': _safe_float(payload.get('sale_price'), 0),
            'target_margin_percent': _safe_float(payload.get('target_margin_percent'), 80),
            'contingency_percent': _safe_float(payload.get('contingency_percent'), 5),
            'photo_path': (payload.get('photo_path') or 'pendiente_subir').strip(),
            'notes': (payload.get('notes') or '').strip(),
            'status': (payload.get('status') or 'activo').strip(),
        }
        if rid > 0:
            cur.execute("""UPDATE cocktail_recipes SET code=?,name=?,category=?,cocktail_type=?,glass_type=?,serving_size_ml=?,yield_qty=?,yield_unit=?,difficulty=?,preparation_time_minutes=?,seasonality=?,sale_price=?,target_margin_percent=?,contingency_percent=?,photo_path=?,notes=?,status=?,updated_at=? WHERE id=?""",
                        (vals['code'],vals['name'],vals['category'],vals['cocktail_type'],vals['glass_type'],vals['serving_size_ml'],vals['yield_qty'],vals['yield_unit'],vals['difficulty'],vals['preparation_time_minutes'],vals['seasonality'],vals['sale_price'],vals['target_margin_percent'],vals['contingency_percent'],vals['photo_path'],vals['notes'],vals['status'],now,rid))
        else:
            cur.execute("""INSERT INTO cocktail_recipes(business_id,restaurant_id,bar_id,code,name,category,cocktail_type,glass_type,serving_size_ml,yield_qty,yield_unit,difficulty,preparation_time_minutes,seasonality,sale_price,target_margin_percent,contingency_percent,photo_path,notes,status,active,created_by,demo_data,non_productive_demo,data_scope,created_at,updated_at,contains_alcohol,allergens_json,warnings_json)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,vals['code'],vals['name'],vals['category'],vals['cocktail_type'],vals['glass_type'],vals['serving_size_ml'],vals['yield_qty'],vals['yield_unit'],vals['difficulty'],vals['preparation_time_minutes'],vals['seasonality'],vals['sale_price'],vals['target_margin_percent'],vals['contingency_percent'],vals['photo_path'],vals['notes'],vals['status'],1,'Usuario LAB',1,1,'demo',now,now,1,_j([]),_j(['TPV_NO_CONECTADO','FOTO_PENDIENTE'])))
            rid = int(cur.lastrowid)
        _recalculate_cocktail(cur, rid)
        conn.commit()
        detail = get_cocktail_detail(rid)
        return {'ok': True, 'message': 'Ficha de cóctel guardada. No productivo.', 'recipe_id': rid, 'detail': detail}
    except Exception as exc:
        conn.rollback(); return {'ok': False, 'message': f'Error guardando cóctel: {exc}'}
    finally:
        conn.close()


def save_cocktail_line(cocktail_recipe_id: int, payload: Dict[str, Any]) -> Dict[str, Any]:
    conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
    try:
        rid = int(cocktail_recipe_id)
        if not cur.execute('SELECT id FROM cocktail_recipes WHERE id=?', (rid,)).fetchone():
            return {'ok': False, 'message': 'Cóctel no encontrado.'}
        line_id = int(payload.get('line_id') or 0)
        name = (payload.get('ingredient_name') or '').strip()
        if not name:
            return {'ok': False, 'message': 'Ingrediente requerido.'}
        requested_unit = (payload.get('unit') or '').strip()
        qty_net = _safe_float(payload.get('qty_net'), 0)
        waste = _safe_float(payload.get('waste_percent'), 0)
        origin_req = (payload.get('origin') or 'stock_bar').strip()
        origin, item_id, prod_id, auto_cost, supplier, stock = _resolve_bar_source(cur, origin_req, name)
        default_unit = 'ml'
        if item_id:
            row_u = cur.execute('SELECT base_unit FROM bar_items WHERE id=?', (item_id,)).fetchone()
            default_unit = row_u['base_unit'] if row_u else 'ml'
        elif prod_id:
            row_u = cur.execute('SELECT yield_unit FROM bar_productions WHERE id=?', (prod_id,)).fetchone()
            default_unit = row_u['yield_unit'] if row_u else 'ml'
        allowed_unit = _allowed_bar_unit(default_unit)
        unit = _allowed_bar_unit(requested_unit or allowed_unit)
        if unit != allowed_unit:
            unit = allowed_unit
        cost_unit = float(auto_cost or 0)  # coste automático: Stock Bar / Producción Bar; no override normal desde UI
        qty_gross = _qty_gross(qty_net, waste)
        net = qty_net * cost_unit
        gross = qty_gross * cost_unit
        vals = (origin, item_id, prod_id, name, qty_net, unit, waste, qty_gross, cost_unit, net, gross, supplier, stock, 1, 1)
        if line_id > 0:
            cur.execute("""UPDATE cocktail_recipe_lines SET origin=?,bar_item_id=?,bar_production_id=?,ingredient_name=?,qty_net=?,unit=?,waste_percent=?,qty_gross=?,cost_unit_2026=?,cost_total_net_2026=?,cost_total_gross_2026=?,supplier_name_demo=?,stock_available=?,demo_data=?,non_productive_demo=? WHERE id=? AND cocktail_recipe_id=?""", vals + (line_id, rid))
        else:
            cur.execute("""INSERT INTO cocktail_recipe_lines(cocktail_recipe_id,origin,bar_item_id,bar_production_id,ingredient_name,qty_net,unit,waste_percent,qty_gross,cost_unit_2026,cost_total_net_2026,cost_total_gross_2026,supplier_name_demo,stock_available,demo_data,non_productive_demo)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (rid,) + vals)
            line_id = int(cur.lastrowid)
        _recalculate_cocktail(cur, rid)
        conn.commit()
        return {'ok': True, 'message': 'Línea de escandallo guardada.', 'recipe_id': rid, 'line_id': line_id, 'detail': get_cocktail_detail(rid)}
    except Exception as exc:
        conn.rollback(); return {'ok': False, 'message': f'Error guardando línea: {exc}'}
    finally:
        conn.close()


def delete_cocktail_line(cocktail_recipe_id: int, line_id: int) -> Dict[str, Any]:
    conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
    try:
        cur.execute('DELETE FROM cocktail_recipe_lines WHERE cocktail_recipe_id=? AND id=?', (int(cocktail_recipe_id), int(line_id)))
        _recalculate_cocktail(cur, int(cocktail_recipe_id))
        conn.commit()
        return {'ok': True, 'message': 'Línea quitada.', 'recipe_id': int(cocktail_recipe_id), 'detail': get_cocktail_detail(int(cocktail_recipe_id))}
    except Exception as exc:
        conn.rollback(); return {'ok': False, 'message': f'Error quitando línea: {exc}'}
    finally:
        conn.close()


def save_cocktail_steps(cocktail_recipe_id: int, steps_text: str) -> Dict[str, Any]:
    conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
    try:
        rid=int(cocktail_recipe_id)
        steps=[]
        for raw in (steps_text or '').splitlines():
            t=raw.strip()
            if not t: continue
            t=re.sub(r'^\s*\d+[\).:-]?\s*','',t).strip()
            if t: steps.append(t)
        cur.execute('DELETE FROM cocktail_recipe_steps WHERE cocktail_recipe_id=?', (rid,))
        for i,txt in enumerate(steps,1):
            cur.execute('INSERT INTO cocktail_recipe_steps(cocktail_recipe_id,step_number,instruction,demo_data) VALUES(?,?,?,1)', (rid,i,txt))
        conn.commit()
        return {'ok': True, 'message': 'Procedimiento guardado.', 'recipe_id': rid, 'steps': len(steps), 'detail': get_cocktail_detail(rid)}
    except Exception as exc:
        conn.rollback(); return {'ok': False, 'message': f'Error guardando pasos: {exc}'}
    finally:
        conn.close()

# ==============================================================================
# PEDIDOS CONSOLIDADOS COCINA + BARRA · LAB SEGURO / DEMO NO PRODUCTIVO
# ==============================================================================

def _ensure_col(cur, table: str, col: str, ddl: str) -> None:
    try:
        cols = [r['name'] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
    except Exception:
        pass


def ensure_bar_order_schema(cur) -> None:
    ensure_bar_schema(cur)
    _ensure_col(cur, 'bar_items', 'purchase_link_mode', "TEXT DEFAULT 'bar_only'")
    _ensure_col(cur, 'bar_items', 'kitchen_item_id', 'INTEGER DEFAULT NULL')
    _ensure_col(cur, 'bar_items', 'consolidation_allowed', 'INTEGER DEFAULT 0')
    cur.execute("""CREATE TABLE IF NOT EXISTS lab_consolidated_order_runs(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_code TEXT UNIQUE,
        supplier_name TEXT,
        status TEXT,
        receipt_variant TEXT,
        demo_data INTEGER DEFAULT 1,
        non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT,
        notes TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS lab_area_order_lines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER,
        area TEXT,
        source_item_table TEXT,
        source_item_id INTEGER,
        item_name TEXT,
        normalized_name TEXT,
        supplier_name TEXT,
        current_stock REAL DEFAULT 0,
        min_stock REAL DEFAULT 0,
        max_stock REAL DEFAULT 0,
        suggested_qty REAL DEFAULT 0,
        unit TEXT,
        purchase_link_mode TEXT,
        consolidation_allowed INTEGER DEFAULT 0,
        demo_data INTEGER DEFAULT 1,
        non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS lab_consolidated_order_lines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER,
        supplier_name TEXT,
        item_name TEXT,
        normalized_name TEXT,
        total_qty REAL DEFAULT 0,
        unit TEXT,
        can_consolidate INTEGER DEFAULT 0,
        consolidation_reason TEXT,
        split_json TEXT,
        demo_data INTEGER DEFAULT 1,
        non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS lab_receipt_split_lines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        run_id INTEGER,
        consolidated_line_id INTEGER,
        item_name TEXT,
        ordered_qty REAL DEFAULT 0,
        received_qty REAL DEFAULT 0,
        unit TEXT,
        auto_split_status TEXT,
        split_json TEXT,
        notes TEXT,
        demo_data INTEGER DEFAULT 1,
        non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT
    )""")


def _update_bar_purchase_modes(cur) -> None:
    common = {'lima', 'limon', 'naranja', 'hierbabuena', 'azucar blanco', 'sal'}
    for row in cur.execute('SELECT id,name,family FROM bar_items WHERE demo_data=1').fetchall():
        n = _norm(row['name'])
        if n in common:
            mode = 'common_purchase_split_stock'
            allowed = 1
        else:
            mode = 'bar_only'
            allowed = 0
        cur.execute('UPDATE bar_items SET purchase_link_mode=?, consolidation_allowed=? WHERE id=?', (mode, allowed, int(row['id'])))


def _demo_kitchen_needs() -> List[Dict[str, Any]]:
    """Necesidades demo de Cocina. No consulta ni modifica stock real de Cocina."""
    return [
        {'area':'cocina','item_name':'Lima','normalized_name':_norm('Lima'),'supplier_name':DEMO_PROVIDER,'current_stock':2500,'min_stock':4000,'max_stock':10000,'unit':'gr','suggested_qty':7500,'purchase_link_mode':'common_purchase_split_stock','consolidation_allowed':1},
        {'area':'cocina','item_name':'Azúcar Blanco','normalized_name':_norm('Azúcar Blanco'),'supplier_name':DEMO_PROVIDER,'current_stock':4000,'min_stock':5000,'max_stock':15000,'unit':'gr','suggested_qty':11000,'purchase_link_mode':'common_purchase_split_stock','consolidation_allowed':1},
        {'area':'cocina','item_name':'Sal','normalized_name':_norm('Sal'),'supplier_name':DEMO_PROVIDER,'current_stock':900,'min_stock':1000,'max_stock':4000,'unit':'gr','suggested_qty':3100,'purchase_link_mode':'common_purchase_split_stock','consolidation_allowed':1},
        {'area':'cocina','item_name':'Tomate','normalized_name':_norm('Tomate'),'supplier_name':DEMO_PROVIDER,'current_stock':3000,'min_stock':5000,'max_stock':12000,'unit':'gr','suggested_qty':9000,'purchase_link_mode':'kitchen_only','consolidation_allowed':0},
    ]


def _demo_bar_needs(cur) -> List[Dict[str, Any]]:
    """Necesidades demo de Barra calculadas con min/max propios. No toca stock real definitivo."""
    desired_current = {
        'lima': 800,
        'azucar blanco': 700,
        'sal': 600,
        'hierbabuena': 80,
        'ginebra': 500,
        'ron blanco': 500,
        'tonica': 2500,
    }
    out: List[Dict[str, Any]] = []
    for row in cur.execute('SELECT * FROM bar_items WHERE demo_data=1 ORDER BY name').fetchall():
        n = _norm(row['name'])
        if n not in desired_current:
            continue
        current = float(desired_current[n])
        min_stock = float(row['min_stock'] or 0)
        max_stock = float(row['max_stock'] or 0)
        suggested = max(0.0, max_stock - current) if current < min_stock else 0.0
        if suggested <= 0:
            continue
        out.append({
            'area':'barra',
            'source_item_table':'bar_items',
            'source_item_id':int(row['id']),
            'item_name':row['name'],
            'normalized_name':n,
            'supplier_name':row['supplier_name_demo'] or DEMO_PROVIDER,
            'current_stock':current,
            'min_stock':min_stock,
            'max_stock':max_stock,
            'unit':row['base_unit'],
            'suggested_qty':suggested,
            'purchase_link_mode':row['purchase_link_mode'] or 'bar_only',
            'consolidation_allowed':int(row['consolidation_allowed'] or 0),
        })
    return out


def _insert_area_line(cur, run_id: int, line: Dict[str, Any]) -> None:
    cur.execute("""INSERT INTO lab_area_order_lines(run_id,area,source_item_table,source_item_id,item_name,normalized_name,supplier_name,current_stock,min_stock,max_stock,suggested_qty,unit,purchase_link_mode,consolidation_allowed,demo_data,non_productive_demo,created_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (run_id, line.get('area'), line.get('source_item_table','demo_lab'), int(line.get('source_item_id') or 0), line.get('item_name'), line.get('normalized_name'), line.get('supplier_name',DEMO_PROVIDER), float(line.get('current_stock') or 0), float(line.get('min_stock') or 0), float(line.get('max_stock') or 0), float(line.get('suggested_qty') or 0), line.get('unit'), line.get('purchase_link_mode'), int(line.get('consolidation_allowed') or 0), 1, 1, _now()))


def simulate_consolidated_bar_kitchen_order(receipt_variant: str = 'match') -> Dict[str, Any]:
    """Simula pedido independiente Cocina/Barra, consolidación por proveedor y reparto en recepción.
    LAB seguro: no crea pedidos reales, no modifica stock Cocina ni Stock Bar productivo.
    """
    conn = db(); cur = conn.cursor(); ensure_bar_order_schema(cur)
    try:
        c = cur.execute('SELECT COUNT(*) c FROM bar_items WHERE demo_data=1').fetchone()
        if int(c['c'] or 0) == 0:
            conn.close(); load_cocktail_bar_demo(); conn = db(); cur = conn.cursor(); ensure_bar_order_schema(cur)
        _update_bar_purchase_modes(cur)
        now = _now()
        variant = (receipt_variant or 'match').strip().lower()
        
        import uuid
        run_code = 'LAB-CONSOLIDADO-' + now.replace(':','').replace('-','').replace('T','-') + '-' + uuid.uuid4().hex[:6]
        cur.execute("""INSERT INTO lab_consolidated_order_runs(run_code,supplier_name,status,receipt_variant,demo_data,non_productive_demo,created_at,notes)
                       VALUES(?,?,?,?,?,?,?,?)""", (run_code, DEMO_PROVIDER, 'simulado_no_productivo', variant, 1, 1, now, 'Cocina y Barra calculan min/max propios. Solo se consolida envío a proveedor; recepción reparte stock por área.'))
        run_id = int(cur.lastrowid)
        area_lines = _demo_kitchen_needs() + _demo_bar_needs(cur)
        area_lines = [x for x in area_lines if float(x.get('suggested_qty') or 0) > 0]
        for line in area_lines:
            _insert_area_line(cur, run_id, line)
        groups: Dict[Tuple[str, str, str, bool], List[Dict[str, Any]]] = {}
        for ln in area_lines:
            can = bool(int(ln.get('consolidation_allowed') or 0)) and ln.get('purchase_link_mode') == 'common_purchase_split_stock'
            key = (ln.get('supplier_name', DEMO_PROVIDER), ln['normalized_name'] if can else (ln['normalized_name'] + '|' + ln['area']), ln.get('unit') or '', can)
            groups.setdefault(key, []).append(ln)
        consolidated = []
        receipt_rows = []
        for (_supplier, _norm_name, unit, can), lines in groups.items():
            total = sum(float(x.get('suggested_qty') or 0) for x in lines)
            display = lines[0]['item_name']
            split = {x['area']: {'qty': float(x.get('suggested_qty') or 0), 'unit': unit, 'stock_destino': 'Stock Cocina' if x['area']=='cocina' else 'Stock Bar'} for x in lines}
            reason = 'consolidado_por_proveedor_con_reparto_stock' if can and len(lines) > 1 else ('pedido_area_independiente_no_consolidable' if not can else 'pedido_area_unica')
            cur.execute("""INSERT INTO lab_consolidated_order_lines(run_id,supplier_name,item_name,normalized_name,total_qty,unit,can_consolidate,consolidation_reason,split_json,demo_data,non_productive_demo,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (run_id, _supplier, display, lines[0]['normalized_name'], total, unit, 1 if can else 0, reason, _j(split), 1, 1, now))
            cid = int(cur.lastrowid)
            consolidated.append({'id': cid, 'item_name': display, 'total_qty': total, 'unit': unit, 'can_consolidate': can, 'reason': reason, 'split': split})
            received = total
            status = 'ok_auto_split'
            notes = 'Recepción coincide con pedido consolidado. Reparto automático por desglose original.'
            split_received = split
            if variant in ('short','diferencia') and _norm(display) == 'lima':
                received = max(0.0, total - 700.0)
                status = 'revision_diferencia_cantidad'
                notes = 'Recibido menor que pedido. No se valida stock; se sugiere reparto proporcional para revisión humana.'
                ratio = received / total if total else 0
                split_received = {area: {**vals, 'qty_original': vals['qty'], 'qty_sugerida_recibida': round(vals['qty'] * ratio, 3)} for area, vals in split.items()}
            cur.execute("""INSERT INTO lab_receipt_split_lines(run_id,consolidated_line_id,item_name,ordered_qty,received_qty,unit,auto_split_status,split_json,notes,demo_data,non_productive_demo,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""", (run_id, cid, display, total, received, unit, status, _j(split_received), notes, 1, 1, now))
            receipt_rows.append({'item_name': display, 'ordered_qty': total, 'received_qty': received, 'unit': unit, 'auto_split_status': status, 'split': split_received, 'notes': notes})
        conn.commit()
        return {'ok': True, 'message': 'Simulacro de pedidos Cocina + Barra ejecutado. No productivo.', 'mode': 'LAB_PEDIDOS_CONSOLIDADOS_NO_PRODUCTIVO', 'run_id': run_id, 'run_code': run_code, 'receipt_variant': variant, 'area_order_lines': area_lines, 'consolidated_order_lines': consolidated, 'receipt_split_lines': receipt_rows, 'rules': ['Cocina calcula min/max propios.', 'Barra calcula min/max propios.', 'El pedido se consolida solo por proveedor/artículo/unidad compatible.', 'La recepción reparte automáticamente si coincide.', 'Si hay diferencia, queda en revisión y no valida stock.'], 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    except Exception as exc:
        conn.rollback()
        return {'ok': False, 'message': f'Error en simulacro de pedidos consolidados: {exc}'}
    finally:
        conn.close()


def get_consolidated_order_summary() -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_bar_order_schema(cur)
    try:
        rows = [dict(r) for r in cur.execute('SELECT * FROM lab_consolidated_order_runs ORDER BY id DESC LIMIT 5').fetchall()]
        latest = rows[0] if rows else None
        lines=[]; receipts=[]; area=[]
        if latest:
            rid = int(latest['id'])
            area = [dict(r) for r in cur.execute('SELECT area,item_name,current_stock,min_stock,max_stock,suggested_qty,unit,purchase_link_mode FROM lab_area_order_lines WHERE run_id=? ORDER BY area,item_name', (rid,)).fetchall()]
            lines = [dict(r) for r in cur.execute('SELECT item_name,total_qty,unit,can_consolidate,consolidation_reason,split_json FROM lab_consolidated_order_lines WHERE run_id=? ORDER BY item_name', (rid,)).fetchall()]
            receipts = [dict(r) for r in cur.execute('SELECT item_name,ordered_qty,received_qty,unit,auto_split_status,split_json,notes FROM lab_receipt_split_lines WHERE run_id=? ORDER BY item_name', (rid,)).fetchall()]
        return {'ok': True, 'runs': rows, 'latest': latest, 'area_order_lines': area, 'consolidated_order_lines': lines, 'receipt_split_lines': receipts, 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    finally:
        conn.close()

# ==============================================================================
# ALBARÁN ÚNICO COMPARTIDO PROVEEDOR → REPARTO COCINA/BARRA · LAB SEGURO
# ==============================================================================

def ensure_shared_supplier_receipt_schema(cur) -> None:
    """LAB seguro para un único albarán de proveedor con líneas compartidas.
    No crea dos albaranes. Guarda un documento único y split interno por destino de stock.
    """
    ensure_bar_order_schema(cur)
    cur.execute("""CREATE TABLE IF NOT EXISTS lab_shared_item_split_rules(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT, restaurant_id TEXT, bar_id TEXT,
        normalized_name TEXT, item_name TEXT, supplier_name TEXT,
        kitchen_percent REAL DEFAULT 0, bar_percent REAL DEFAULT 0,
        active INTEGER DEFAULT 1, demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,normalized_name,supplier_name)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS lab_shared_supplier_receipts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        document_code TEXT UNIQUE,
        supplier_name TEXT, receipt_date TEXT,
        source_module TEXT DEFAULT 'ocr_albaran_unico_compartido_lab',
        status TEXT, split_policy TEXT,
        demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT, notes TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS lab_shared_supplier_receipt_lines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_id INTEGER,
        raw_text TEXT, item_name TEXT, normalized_name TEXT,
        received_qty REAL DEFAULT 0, unit TEXT,
        matched_consolidated_order INTEGER DEFAULT 0,
        split_source TEXT, split_status TEXT,
        split_json TEXT, notes TEXT,
        demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT
    )""")


def _seed_shared_split_rules(cur) -> None:
    now = _now()
    rules = [
        ('Lima', 60, 40),
        ('Limón', 65, 35),
        ('Naranja', 55, 45),
        ('Azúcar Blanco', 70, 30),
        ('Sal', 80, 20),
        ('Hierbabuena', 20, 80),
    ]
    for name, kp, bp in rules:
        cur.execute("""INSERT INTO lab_shared_item_split_rules(business_id,restaurant_id,bar_id,normalized_name,item_name,supplier_name,kitchen_percent,bar_percent,active,demo_data,non_productive_demo,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(business_id,restaurant_id,bar_id,normalized_name,supplier_name)
                       DO UPDATE SET item_name=excluded.item_name,kitchen_percent=excluded.kitchen_percent,bar_percent=excluded.bar_percent,active=1,updated_at=excluded.updated_at""",
                    (DEMO_BUSINESS_ID, DEMO_RESTAURANT_ID, DEMO_BAR_ID, _norm(name), name, DEMO_PROVIDER, float(kp), float(bp), 1, 1, 1, now, now))


def _demo_exact_order_split_by_name(cur) -> Dict[str, Dict[str, Any]]:
    """Calcula el split exacto de pedidos previos LAB sin tocar pedidos reales."""
    if int(cur.execute('SELECT COUNT(*) c FROM bar_items WHERE demo_data=1').fetchone()['c'] or 0) == 0:
        load_cocktail_bar_demo()
    _update_bar_purchase_modes(cur)
    area_lines = _demo_kitchen_needs() + _demo_bar_needs(cur)
    out: Dict[str, Dict[str, Any]] = {}
    for ln in area_lines:
        if not (int(ln.get('consolidation_allowed') or 0) and ln.get('purchase_link_mode') == 'common_purchase_split_stock'):
            continue
        n = ln['normalized_name']; unit = ln.get('unit') or ''
        if n not in out:
            out[n] = {'unit': unit, 'ordered_total': 0.0, 'areas': {}}
        out[n]['ordered_total'] += float(ln.get('suggested_qty') or 0)
        out[n]['areas'][ln['area']] = {'qty': float(ln.get('suggested_qty') or 0), 'unit': unit, 'stock_destino': 'Stock Cocina' if ln['area']=='cocina' else 'Stock Bar'}
    return out


def _split_by_percentage_rule(cur, item_name: str, received_qty: float, unit: str) -> Tuple[Dict[str, Any] | None, str]:
    rule = cur.execute("""SELECT * FROM lab_shared_item_split_rules
                          WHERE business_id=? AND restaurant_id=? AND bar_id=? AND normalized_name=? AND supplier_name=? AND active=1""",
                       (DEMO_BUSINESS_ID, DEMO_RESTAURANT_ID, DEMO_BAR_ID, _norm(item_name), DEMO_PROVIDER)).fetchone()
    if not rule:
        return None, 'sin_regla_porcentaje'
    kp = float(rule['kitchen_percent'] or 0); bp = float(rule['bar_percent'] or 0); total = kp + bp
    if total <= 0:
        return None, 'regla_porcentaje_invalida'
    cocina = round(float(received_qty) * kp / total, 3)
    barra = round(float(received_qty) - cocina, 3)
    return {
        'cocina': {'qty': cocina, 'unit': unit, 'percent': kp, 'stock_destino': 'Stock Cocina'},
        'barra': {'qty': barra, 'unit': unit, 'percent': bp, 'stock_destino': 'Stock Bar'},
    }, 'porcentaje_defecto'


def simulate_single_shared_supplier_receipt(receipt_variant: str = 'pedido_previo') -> Dict[str, Any]:
    """Simula un único albarán de verduras/secos compartidos.
    Prioridad: pedido previo exacto → porcentaje configurado → revisión.
    No crea dos albaranes ni toca stock real/productivo.
    """
    conn = db(); cur = conn.cursor(); ensure_shared_supplier_receipt_schema(cur)
    try:
        if int(cur.execute('SELECT COUNT(*) c FROM bar_items WHERE demo_data=1').fetchone()['c'] or 0) == 0:
            conn.close(); load_cocktail_bar_demo(); conn = db(); cur = conn.cursor(); ensure_shared_supplier_receipt_schema(cur)
        _seed_shared_split_rules(cur)
        now = _now()
        import uuid
        variant = (receipt_variant or 'pedido_previo').strip().lower()
        doc = 'ALB-UNICO-COMPARTIDO-DEMO-' + uuid.uuid4().hex[:6].upper()
        exact = _demo_exact_order_split_by_name(cur)

        if variant in ('porcentaje','percentage','sin_pedido'):
            raw_lines = [
                {'name':'Naranja','qty':10000,'unit':'gr'},
                {'name':'Hierbabuena','qty':1000,'unit':'gr'},
                {'name':'Limón','qty':5000,'unit':'gr'},
            ]
            policy = 'porcentaje_defecto_sin_pedido_previo'
        elif variant in ('revision','sin_regla'):
            raw_lines = [
                {'name':'Menta fresca especial','qty':800,'unit':'gr'},
                {'name':'Lima','qty':6000,'unit':'gr'},
            ]
            policy = 'mixto_revision_y_porcentaje'
        else:
            # Un único albarán que coincide con las necesidades previas consolidadas LAB.
            raw_lines = [
                {'name':'Lima','qty':exact.get(_norm('Lima'),{}).get('ordered_total',11700),'unit':'gr'},
                {'name':'Azúcar Blanco','qty':exact.get(_norm('Azúcar Blanco'),{}).get('ordered_total',15300),'unit':'gr'},
                {'name':'Sal','qty':exact.get(_norm('Sal'),{}).get('ordered_total',5500),'unit':'gr'},
            ]
            if variant in ('diferencia','short'):
                raw_lines[0]['qty'] = max(0.0, float(raw_lines[0]['qty']) - 700.0)
                policy = 'pedido_previo_con_diferencia_reparto_proporcional'
            else:
                policy = 'pedido_previo_desglose_exacto'

        cur.execute("""INSERT INTO lab_shared_supplier_receipts(document_code,supplier_name,receipt_date,status,split_policy,demo_data,non_productive_demo,created_at,updated_at,notes)
                       VALUES(?,?,?,?,?,?,?,?,?,?)""",
                    (doc, DEMO_PROVIDER, now[:10], 'simulado_no_productivo', policy, 1, 1, now, now, 'Un único albarán proveedor con reparto interno Cocina/Barra. No se crean dos albaranes.'))
        receipt_id = int(cur.lastrowid)
        results=[]; auto=0; review=0
        for rl in raw_lines:
            name = rl['name']; n = _norm(name); qty = float(rl['qty'] or 0); unit = rl.get('unit') or 'gr'
            matched_order = 0; split_source = ''; split_status = ''; notes = ''; split = None
            ex = exact.get(n)
            if ex and variant not in ('porcentaje','percentage','sin_pedido'):
                matched_order = 1
                ordered = float(ex.get('ordered_total') or 0)
                areas = ex.get('areas') or {}
                if ordered > 0 and abs(qty - ordered) < 0.0001:
                    split = areas
                    split_source = 'pedido_previo'
                    split_status = 'ok_auto_split_pedido_previo'
                    notes = 'Cantidad recibida coincide con pedido previo consolidado. Reparto exacto por desglose original.'
                else:
                    ratio = qty / ordered if ordered else 0
                    split = {area: {**vals, 'qty_original_pedido': vals['qty'], 'qty': round(float(vals['qty']) * ratio, 3), 'reparto': 'proporcional_a_recibido'} for area, vals in areas.items()}
                    split_source = 'pedido_previo_proporcional'
                    split_status = 'ok_auto_split_diferencia_proporcional_lab'
                    notes = 'Cantidad recibida difiere del pedido. LAB reparte proporcionalmente según peso del pedido original; en productivo puede requerir aviso/revisión según tolerancia.'
            else:
                split, reason = _split_by_percentage_rule(cur, name, qty, unit)
                if split:
                    split_source = reason
                    split_status = 'ok_auto_split_porcentaje_defecto'
                    notes = 'Sin pedido previo claro. Se aplica regla porcentual configurada por artículo/proveedor/local/área.'
                else:
                    split_source = reason
                    split_status = 'revision_sin_pedido_ni_porcentaje'
                    notes = 'No hay pedido previo ni regla porcentual. No se reparte ni valida stock automáticamente.'
            if split_status.startswith('ok_auto'):
                auto += 1
            else:
                review += 1
            cur.execute("""INSERT INTO lab_shared_supplier_receipt_lines(receipt_id,raw_text,item_name,normalized_name,received_qty,unit,matched_consolidated_order,split_source,split_status,split_json,notes,demo_data,non_productive_demo,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (receipt_id, f"{name} {qty} {unit}", name, n, qty, unit, matched_order, split_source, split_status, _j(split or {}), notes, 1, 1, now, now))
            results.append({'item_name':name,'received_qty':qty,'unit':unit,'split_source':split_source,'split_status':split_status,'split':split or {},'notes':notes})
        status = 'auto_split_ok' if review == 0 else 'revision_parcial'
        cur.execute('UPDATE lab_shared_supplier_receipts SET status=?,updated_at=? WHERE id=?', (status, now, receipt_id))
        conn.commit()
        return {'ok': True, 'message':'Albarán único compartido simulado. No productivo.', 'mode':'LAB_ALBARAN_UNICO_COMPARTIDO_NO_PRODUCTIVO', 'receipt_id':receipt_id, 'document_code':doc, 'variant':variant, 'status':status, 'auto_split_lines':auto, 'review_lines_count':review, 'lines':results, 'rules':['Un único albarán proveedor; no se duplican documentos.', 'Prioridad 1: reparto por pedido previo Cocina/Barra.', 'Prioridad 2: regla porcentual por artículo/proveedor/local/área.', 'Sin pedido ni porcentaje: revisión.', 'El split genera destinos internos separados: Stock Cocina y Stock Bar.'], 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    except Exception as exc:
        conn.rollback(); return {'ok': False, 'message': f'Error simulando albarán único compartido: {exc}'}
    finally:
        conn.close()


def get_shared_supplier_receipt_summary() -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_shared_supplier_receipt_schema(cur)
    try:
        receipts=[dict(r) for r in cur.execute('SELECT id,document_code,supplier_name,receipt_date,status,split_policy,created_at FROM lab_shared_supplier_receipts ORDER BY id DESC LIMIT 5').fetchall()]
        latest=receipts[0] if receipts else None
        lines=[]; rules=[]
        if latest:
            lines=[dict(r) for r in cur.execute('SELECT item_name,received_qty,unit,matched_consolidated_order,split_source,split_status,split_json,notes FROM lab_shared_supplier_receipt_lines WHERE receipt_id=? ORDER BY id', (int(latest['id']),)).fetchall()]
        rules=[dict(r) for r in cur.execute('SELECT item_name,supplier_name,kitchen_percent,bar_percent,active FROM lab_shared_item_split_rules WHERE active=1 ORDER BY item_name').fetchall()]
        return {'ok': True, 'latest': latest, 'receipts': receipts, 'lines': lines, 'split_rules': rules, 'rules_text':['Un albarán único puede repartir varias líneas hacia Stock Cocina y Stock Bar.', 'Si hay pedido consolidado previo se usa ese desglose.', 'Si no hay pedido, se usa porcentaje configurado.', 'Si falta regla, revisión.'], 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    finally:
        conn.close()


# ==============================================================================
# BEBIDAS POR SERVICIO · BARRA LAB / DEMO NO PRODUCTIVO
# ==============================================================================

def ensure_bar_beverage_schema(cur) -> None:
    ensure_bar_schema(cur)
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_pour_sizes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT, restaurant_id TEXT, bar_id TEXT, code TEXT, name TEXT,
        service_type TEXT, qty_ml REAL DEFAULT 0, active INTEGER DEFAULT 1,
        demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,code)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_beverage_services(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT, restaurant_id TEXT, bar_id TEXT, code TEXT, name TEXT,
        service_type TEXT, sale_format TEXT, billing_mode TEXT DEFAULT 'bundle_price',
        bundle_sale_price REAL DEFAULT 0, separate_sale_price_total REAL DEFAULT 0,
        suggested_price REAL DEFAULT 0, target_margin_percent REAL DEFAULT 0,
        contingency_percent REAL DEFAULT 0, bottle_ml REAL DEFAULT 0, service_ml REAL DEFAULT 0,
        theoretical_servings REAL DEFAULT 0, waste_percent REAL DEFAULT 0,
        cost_total_2026 REAL DEFAULT 0, margin_percent_2026 REAL DEFAULT 0,
        tpv_ready INTEGER DEFAULT 1, affects_stock_pool TEXT DEFAULT 'stock_bar', notes TEXT,
        active INTEGER DEFAULT 1, demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        data_scope TEXT DEFAULT 'demo', created_at TEXT, updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,code)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_beverage_service_lines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        beverage_service_id INTEGER, line_type TEXT DEFAULT 'stock_bar', bar_item_id INTEGER,
        item_name TEXT, qty_net REAL DEFAULT 0, unit TEXT, waste_percent REAL DEFAULT 0,
        qty_gross REAL DEFAULT 0, cost_unit_2026 REAL DEFAULT 0,
        cost_total_net_2026 REAL DEFAULT 0, cost_total_gross_2026 REAL DEFAULT 0,
        sale_price_component REAL DEFAULT 0, component_role TEXT,
        demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_open_bottles(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT, restaurant_id TEXT, bar_id TEXT, bar_item_id INTEGER, item_name TEXT,
        bottle_code TEXT, bottle_ml REAL DEFAULT 0, opened_at TEXT, opened_by TEXT,
        theoretical_ml_remaining REAL DEFAULT 0, servings_sold REAL DEFAULT 0,
        oxidation_waste_percent REAL DEFAULT 0, shelf_life_days INTEGER DEFAULT 0,
        status TEXT DEFAULT 'abierta_demo', demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,bottle_code)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_beverage_service_history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        beverage_service_id INTEGER, cost_total_2026 REAL DEFAULT 0,
        bundle_sale_price REAL DEFAULT 0, margin_percent_2026 REAL DEFAULT 0,
        calculated_at TEXT, source TEXT, notes TEXT,
        demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1
    )""")


def _bar_item_by_name(cur) -> Dict[str, Any]:
    return {_norm(r['name']): dict(r) for r in cur.execute('SELECT * FROM bar_items WHERE demo_data=1').fetchall()}

POUR_SIZES = [
    ('POUR-CHUPITO-30','Chupito 30 ml','espirituoso_chupito',30),
    ('POUR-COPA-50','Copa estándar 50 ml','espirituoso_copa',50),
    ('POUR-PREMIUM-60','Copa premium 60 ml','espirituoso_copa',60),
    ('WINE-100','Vino copa 100 ml','vino_por_copas',100),
    ('WINE-125','Vino copa 125 ml','vino_por_copas',125),
    ('WINE-150','Vino copa 150 ml','vino_por_copas',150),
    ('BEER-CANA-250','Caña 250 ml','cerveza_barril',250),
    ('BEER-DOBLE-400','Doble 400 ml','cerveza_barril',400),
]

BEVERAGE_SERVICES = [
    {'code':'BAR-SVC-VODKA-REDBULL-001','name':'Vodka Red Bull Demo','service_type':'combinado','sale_format':'vodka_50ml_lata_250ml','billing_mode':'operator_choice','bundle_sale_price':10.50,'separate_sale_price_total':11.00,'target_margin_percent':78,'contingency_percent':5,'bottle_ml':700,'service_ml':300,'waste_percent':2,'notes':'Puede cobrarse como precio completo único o como vodka + lata Red Bull separados. Stock descuenta ambos componentes.','lines':[('Vodka',50,'ml',1,6.50,'alcohol'),('Red Bull Demo',250,'ml',2,4.50,'mixer')]},
    {'code':'BAR-SVC-WHISKY-COLA-001','name':'Whisky Cola Demo','service_type':'combinado','sale_format':'whisky_50ml_cola_200ml','billing_mode':'operator_choice','bundle_sale_price':9.50,'separate_sale_price_total':9.80,'target_margin_percent':78,'contingency_percent':5,'bottle_ml':700,'service_ml':250,'waste_percent':2,'notes':'Recomendado ticket con precio completo; alternativa: cuenta separada whisky + refresco.','lines':[('Whisky Escocés Demo',50,'ml',1,6.20,'alcohol'),('Cola',200,'ml',3,2.80,'mixer'),('Hielo',180,'gr',8,0.00,'hielo')]},
    {'code':'BAR-SVC-VINO-BLANCO-125-001','name':'Vino blanco copa 125 ml Demo','service_type':'vino_por_copas','sale_format':'copa_125ml','billing_mode':'single_item','bundle_sale_price':4.50,'separate_sale_price_total':4.50,'target_margin_percent':75,'contingency_percent':5,'bottle_ml':750,'service_ml':125,'waste_percent':3,'notes':'Botella 750 ml. 6 copas teóricas de 125 ml. Control de botella abierta, oxidación y diferencia al cierre.','lines':[('Vino Blanco Demo',125,'ml',3,4.50,'vino')]},
    {'code':'BAR-SVC-VINO-TINTO-150-001','name':'Vino tinto copa 150 ml Demo','service_type':'vino_por_copas','sale_format':'copa_150ml','billing_mode':'single_item','bundle_sale_price':5.00,'separate_sale_price_total':5.00,'target_margin_percent':75,'contingency_percent':5,'bottle_ml':750,'service_ml':150,'waste_percent':3,'notes':'Botella 750 ml. 5 copas teóricas de 150 ml. Control de botella abierta y merma/oxidación.','lines':[('Vino Tinto Demo',150,'ml',3,5.00,'vino')]},
    {'code':'BAR-SVC-CERVEZA-BOTELLA-330-001','name':'Cerveza botella 330 ml Demo','service_type':'cerveza','sale_format':'botella_330ml','billing_mode':'single_item','bundle_sale_price':3.50,'separate_sale_price_total':3.50,'target_margin_percent':70,'contingency_percent':5,'bottle_ml':330,'service_ml':330,'waste_percent':1,'notes':'Producto vendible solo. Stock Barra separado.','lines':[('Cerveza botella Demo',330,'ml',1,3.50,'cerveza')]},
    {'code':'BAR-SVC-CANA-250-001','name':'Caña 250 ml Demo','service_type':'cerveza_barril','sale_format':'caña_250ml','billing_mode':'single_item','bundle_sale_price':2.80,'separate_sale_price_total':2.80,'target_margin_percent':75,'contingency_percent':5,'bottle_ml':30000,'service_ml':250,'waste_percent':8,'notes':'Barril 30 l. Rendimiento teórico 120 cañas antes de merma; merma por espuma/servicio incluida.','lines':[('Cerveza barril Demo',250,'ml',8,2.80,'cerveza_barril')]},
    {'code':'BAR-SVC-REFRESCO-COLA-001','name':'Cola sola vaso 237 ml Demo','service_type':'refresco_solo','sale_format':'vaso_237ml','billing_mode':'single_item','bundle_sale_price':3.00,'separate_sale_price_total':3.00,'target_margin_percent':75,'contingency_percent':5,'bottle_ml':4000,'service_ml':237,'waste_percent':3,'notes':'El mismo insumo Cola puede venderse solo o usarse como mixer.','lines':[('Cola',237,'ml',3,3.00,'refresco')]},
    {'code':'BAR-SVC-WHISKY-COPA-50-001','name':'Whisky copa 50 ml Demo','service_type':'espirituoso_por_copa','sale_format':'copa_50ml','billing_mode':'single_item','bundle_sale_price':7.00,'separate_sale_price_total':7.00,'target_margin_percent':78,'contingency_percent':5,'bottle_ml':700,'service_ml':50,'waste_percent':1,'notes':'Servicio simple de espirituoso por copa. 14 servicios teóricos por botella 700 ml antes de merma.','lines':[('Whisky Escocés Demo',50,'ml',1,7.00,'alcohol')]},
    {'code':'BAR-SVC-VODKA-CHUPITO-30-001','name':'Vodka chupito 30 ml Demo','service_type':'espirituoso_chupito','sale_format':'chupito_30ml','billing_mode':'single_item','bundle_sale_price':4.00,'separate_sale_price_total':4.00,'target_margin_percent':78,'contingency_percent':5,'bottle_ml':700,'service_ml':30,'waste_percent':1,'notes':'Chupito demo con medida configurable.','lines':[('Vodka',30,'ml',1,4.00,'alcohol')]},
]


def _ensure_beverage_items(cur) -> None:
    now = _now()
    for code,name,item_type,family,base_unit,purchase_unit,purchase_qty,p25,p26,cost,waste,jy,jc,min_s,max_s,loc in ITEMS:
        cur.execute("""INSERT INTO bar_items(business_id,restaurant_id,bar_id,code,name,normalized_name,item_type,family,base_unit,purchase_unit,purchase_qty,purchase_price_2025,purchase_price_2026,cost_per_base_unit_2026,standard_waste_percent,juice_yield_percent,juice_cost_per_ml_2026,supplier_name_demo,min_stock,max_stock,location,active,demo_data,non_productive_demo,data_scope,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                       ON CONFLICT(business_id,restaurant_id,bar_id,normalized_name) DO UPDATE SET code=excluded.code,item_type=excluded.item_type,family=excluded.family,base_unit=excluded.base_unit,purchase_unit=excluded.purchase_unit,purchase_qty=excluded.purchase_qty,purchase_price_2025=excluded.purchase_price_2025,purchase_price_2026=excluded.purchase_price_2026,cost_per_base_unit_2026=excluded.cost_per_base_unit_2026,standard_waste_percent=excluded.standard_waste_percent,min_stock=excluded.min_stock,max_stock=excluded.max_stock,location=excluded.location,updated_at=excluded.updated_at""",
                    (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,code,name,_norm(name),item_type,family,base_unit,purchase_unit,purchase_qty,p25,p26,cost,waste,jy,jc,DEMO_PROVIDER,min_s,max_s,loc,1,1,1,'demo',now,now))
    for name,qty in INITIAL_STOCK.items():
        row=cur.execute('SELECT id,base_unit FROM bar_items WHERE normalized_name=? AND demo_data=1', (_norm(name),)).fetchone()
        if row:
            exists=cur.execute('SELECT COUNT(*) c FROM bar_stock_movements WHERE bar_item_id=? AND document_code=? AND source_module=?', (int(row['id']),'ALB-BAR-DEMO-2026-0001','carga_demo_cocteleria')).fetchone()
            if int(exists['c'] or 0)==0:
                cur.execute("""INSERT INTO bar_stock_movements(business_id,restaurant_id,bar_id,bar_item_id,movement_type,qty,unit,document_code,source_module,responsible_name,movement_datetime,notes,demo_data,non_productive_demo,created_at)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,int(row['id']),'entrada',qty,row['base_unit'],'ALB-BAR-DEMO-2026-0001','carga_demo_cocteleria','Sistema Demo',now,'Stock inicial demo no productivo.',1,1,now))


def load_bar_beverage_demo() -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_bar_beverage_schema(cur)
    try:
        if int(cur.execute('SELECT COUNT(*) c FROM bar_items WHERE demo_data=1').fetchone()['c'] or 0) == 0:
            conn.close(); load_cocktail_bar_demo(); conn = db(); cur = conn.cursor(); ensure_bar_beverage_schema(cur)
        _ensure_beverage_items(cur)
        now = _now()
        for code,name,stype,qty in POUR_SIZES:
            cur.execute("""INSERT INTO bar_pour_sizes(business_id,restaurant_id,bar_id,code,name,service_type,qty_ml,active,demo_data,non_productive_demo,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(business_id,restaurant_id,bar_id,code) DO UPDATE SET name=excluded.name,service_type=excluded.service_type,qty_ml=excluded.qty_ml,updated_at=excluded.updated_at""",
                        (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,code,name,stype,qty,1,1,1,now,now))
        item_map = _bar_item_by_name(cur)
        service_count = 0; line_count = 0
        for svc in BEVERAGE_SERVICES:
            cost_total = 0.0; prepared_lines = []
            for item_name, qty, unit, waste, sale_component, role in svc['lines']:
                item = item_map.get(_norm(item_name))
                if not item: raise RuntimeError(f'Falta insumo de Barra para servicio: {item_name}')
                gross = _qty_gross(qty, waste); cost_unit = float(item.get('cost_per_base_unit_2026') or 0)
                net = float(qty) * cost_unit; gross_cost = gross * cost_unit; cost_total += gross_cost
                prepared_lines.append((item, item_name, qty, unit, waste, gross, cost_unit, net, gross_cost, sale_component, role))
            target = float(svc.get('target_margin_percent') or 0)
            suggested = cost_total / (1 - target / 100.0) if target and target < 100 else 0.0
            sale = float(svc.get('bundle_sale_price') or 0)
            margin = ((sale - cost_total) / sale * 100.0) if sale else 0.0
            theoretical_servings = (float(svc.get('bottle_ml') or 0) / float(svc.get('service_ml') or 1)) if float(svc.get('service_ml') or 0) else 0.0
            cur.execute("""INSERT INTO bar_beverage_services(business_id,restaurant_id,bar_id,code,name,service_type,sale_format,billing_mode,bundle_sale_price,separate_sale_price_total,suggested_price,target_margin_percent,contingency_percent,bottle_ml,service_ml,theoretical_servings,waste_percent,cost_total_2026,margin_percent_2026,tpv_ready,affects_stock_pool,notes,active,demo_data,non_productive_demo,data_scope,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(business_id,restaurant_id,bar_id,code) DO UPDATE SET name=excluded.name,service_type=excluded.service_type,sale_format=excluded.sale_format,billing_mode=excluded.billing_mode,bundle_sale_price=excluded.bundle_sale_price,separate_sale_price_total=excluded.separate_sale_price_total,suggested_price=excluded.suggested_price,target_margin_percent=excluded.target_margin_percent,contingency_percent=excluded.contingency_percent,bottle_ml=excluded.bottle_ml,service_ml=excluded.service_ml,theoretical_servings=excluded.theoretical_servings,waste_percent=excluded.waste_percent,cost_total_2026=excluded.cost_total_2026,margin_percent_2026=excluded.margin_percent_2026,tpv_ready=excluded.tpv_ready,notes=excluded.notes,updated_at=excluded.updated_at""",
                        (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,svc['code'],svc['name'],svc['service_type'],svc['sale_format'],svc['billing_mode'],sale,float(svc.get('separate_sale_price_total') or sale),suggested,target,float(svc.get('contingency_percent') or 0),float(svc.get('bottle_ml') or 0),float(svc.get('service_ml') or 0),theoretical_servings,float(svc.get('waste_percent') or 0),cost_total,margin,1,'stock_bar',svc.get('notes',''),1,1,1,'demo',now,now))
            service_id = int(cur.execute('SELECT id FROM bar_beverage_services WHERE business_id=? AND restaurant_id=? AND bar_id=? AND code=?', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,svc['code'])).fetchone()['id'])
            cur.execute('DELETE FROM bar_beverage_service_lines WHERE beverage_service_id=?', (service_id,))
            for item,item_name,qty,unit,waste,gross,cost_unit,net,gross_cost,sale_component,role in prepared_lines:
                cur.execute("""INSERT INTO bar_beverage_service_lines(beverage_service_id,line_type,bar_item_id,item_name,qty_net,unit,waste_percent,qty_gross,cost_unit_2026,cost_total_net_2026,cost_total_gross_2026,sale_price_component,component_role,demo_data,non_productive_demo)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                            (service_id,'stock_bar',int(item['id']),item_name,qty,unit,waste,gross,cost_unit,net,gross_cost,float(sale_component or 0),role,1,1))
                line_count += 1
            cur.execute("""INSERT INTO bar_beverage_service_history(beverage_service_id,cost_total_2026,bundle_sale_price,margin_percent_2026,calculated_at,source,notes,demo_data,non_productive_demo)
                           VALUES(?,?,?,?,?,?,?,?,?)""", (service_id,cost_total,sale,margin,now,'carga_demo_bebidas_servicio','Demo bebidas por servicio no productivo.',1,1))
            service_count += 1
        item_map = _bar_item_by_name(cur)
        for bottle_code, item_name, bottle_ml, remaining, shelf, ox in [('OPEN-WINE-WHITE-DEMO-001','Vino Blanco Demo',750,500,2,3),('OPEN-WINE-RED-DEMO-001','Vino Tinto Demo',750,450,2,3)]:
            item = item_map.get(_norm(item_name))
            if item:
                cur.execute("""INSERT INTO bar_open_bottles(business_id,restaurant_id,bar_id,bar_item_id,item_name,bottle_code,bottle_ml,opened_at,opened_by,theoretical_ml_remaining,servings_sold,oxidation_waste_percent,shelf_life_days,status,demo_data,non_productive_demo,created_at,updated_at)
                               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                               ON CONFLICT(business_id,restaurant_id,bar_id,bottle_code) DO UPDATE SET theoretical_ml_remaining=excluded.theoretical_ml_remaining,servings_sold=excluded.servings_sold,updated_at=excluded.updated_at""",
                            (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,int(item['id']),item_name,bottle_code,bottle_ml,now,'Sistema Demo',remaining,(bottle_ml-remaining),ox,shelf,'abierta_demo',1,1,now,now))
        conn.commit()
        return {'ok': True, 'message': 'Demo bebidas por servicio cargada correctamente. No productivo.', 'services': service_count, 'service_lines': line_count, 'pour_sizes': len(POUR_SIZES), 'open_bottles_demo': 2, 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    except Exception as exc:
        conn.rollback(); return {'ok': False, 'message': f'Error cargando bebidas por servicio: {exc}'}
    finally:
        conn.close()






def _bar_stock_group(item: Dict[str, Any]) -> str:
    """Familia operativa visible para no mezclar alcoholes, vinos, cervezas, mixers y secos/garnish."""
    fam = _norm(str(item.get('family') or ''))
    typ = _norm(str(item.get('item_type') or ''))
    name = _norm(str(item.get('name') or ''))
    loc = _norm(str(item.get('location') or ''))
    if fam in ('alcoholes', 'bitters') or 'alcohol' in typ or 'bitter' in typ or any(x in name for x in ('ron','ginebra','vodka','tequila','bourbon','whisky','campari','cointreau','triple sec','vermut','angostura')):
        return 'Alcoholes / espirituosos'
    if 'vino' in fam or 'vino' in typ or 'vino' in name:
        return 'Vinos'
    if 'cerveza' in fam or 'cerveza' in typ or 'cerveza' in name or 'barril' in typ:
        return 'Cervezas'
    if fam in ('mixers',) or typ in ('mixer','refresco','zumo') or any(x in name for x in ('tonica','tónica','cola','ginger','soda','red bull','arandano','arándano','refresco')):
        return 'Mixers / refrescos / zumos'
    if fam in ('frutas','garnish') or typ in ('fruta_bar','garnish','hierba','especia') or any(x in name for x in ('lima','limon','limón','naranja','hierbabuena','aceituna','sal')):
        return 'Frutas / garnish / especias'
    if fam in ('syrups',) or typ in ('endulzante',) or any(x in name for x in ('azucar','azúcar','syrup','agua filtrada')) or 'seco' in loc:
        return 'Secos / syrups / azúcar'
    if fam in ('hielo',) or typ == 'hielo' or 'hielo' in name:
        return 'Hielo'
    return 'Otros insumos Barra'

# ==============================================================================
# BARRA LAB · STOCK E INVENTARIO VISUAL SEPARADO
# ==============================================================================

def get_bar_stock_summary() -> Dict[str, Any]:
    """Pantalla de Stock Bar LAB.
    Se calcula desde movimientos demo/no productivos y no mezcla Cocina.
    """
    conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
    try:
        row=cur.execute('SELECT COUNT(*) c FROM bar_items WHERE business_id=? AND restaurant_id=? AND bar_id=? AND demo_data=1', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID)).fetchone()
        if int(row['c'] or 0) == 0:
            conn.close(); load_cocktail_bar_demo(); load_bar_beverage_demo(); load_bar_mixer_container_demo()
            conn=db(); cur=conn.cursor(); ensure_bar_schema(cur)
        rows=[]
        sql = """SELECT i.id,i.name,i.item_type,i.family,i.base_unit,i.purchase_unit,i.purchase_qty,
                        i.purchase_price_2026,i.cost_per_base_unit_2026,i.standard_waste_percent,
                        i.min_stock,i.max_stock,i.location,i.supplier_name_demo,
                        COALESCE(SUM(CASE WHEN m.movement_type LIKE 'entrada%' THEN m.qty ELSE -m.qty END),0) AS stock_qty
                 FROM bar_items i
                 LEFT JOIN bar_stock_movements m ON m.bar_item_id=i.id AND m.demo_data=1
                 WHERE i.business_id=? AND i.restaurant_id=? AND i.bar_id=? AND i.demo_data=1 AND i.active=1
                 GROUP BY i.id
                 ORDER BY i.family,i.location,i.name"""
        for r in cur.execute(sql, (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID)).fetchall():
            d=dict(r)
            stock=float(d.get('stock_qty') or 0)
            min_s=float(d.get('min_stock') or 0)
            max_s=float(d.get('max_stock') or 0)
            cost=float(d.get('cost_per_base_unit_2026') or 0)
            status='ok'
            if max_s and stock > max_s: status='sobre_max'
            if min_s and stock < min_s: status='bajo_min'
            d.update({'stock_qty':round(stock,3),'stock_value_2026':round(stock*cost,3),'stock_status':status})
            d['stock_group'] = _bar_stock_group(d)
            rows.append(d)
        families={}
        total_value=0.0
        for x in rows:
            fam=x.get('family') or 'sin_familia'
            families.setdefault(fam, {'family':fam,'items':0,'value_2026':0.0,'below_min':0})
            families[fam]['items']+=1
            families[fam]['value_2026']+=float(x.get('stock_value_2026') or 0)
            if x.get('stock_status')=='bajo_min': families[fam]['below_min']+=1
            total_value += float(x.get('stock_value_2026') or 0)
        group_order = ['Alcoholes / espirituosos','Vinos','Cervezas','Mixers / refrescos / zumos','Frutas / garnish / especias','Secos / syrups / azúcar','Hielo','Otros insumos Barra']
        groups = []
        for g in group_order:
            gr = [x for x in rows if x.get('stock_group') == g]
            if gr:
                groups.append({'name': g, 'items': len(gr), 'value_2026': round(sum(float(x.get('stock_value_2026') or 0) for x in gr), 2), 'below_min': sum(1 for x in gr if x.get('stock_status') == 'bajo_min')})
        return {'ok':True,'mode':'BAR_STOCK_LAB_NO_PRODUCTIVO','items':rows,'groups':groups,'families':list(families.values()),'totals':{'items':len(rows),'value_2026':round(total_value,2),'below_min':sum(1 for x in rows if x.get('stock_status')=='bajo_min')},'rules':['Stock Bar separado de Cocina.','Unidades Barra: ml/gr/ud.','Demo no productivo.','Vista agrupada por familia operativa para no mezclar bebidas, secos y garnish.'],'demo_data':True,'DATOS_DEMO_NO_PRODUCTIVOS':True}
    finally:
        conn.close()


def get_bar_inventory_summary() -> Dict[str, Any]:
    """Inventario Bar LAB preparado: vista de conteo teórico sin cerrar inventario real."""
    stock = get_bar_stock_summary()
    if not stock.get('ok'):
        return stock
    items=[]
    for x in stock.get('items',[]):
        items.append({
            'item_id': x.get('id'),
            'name': x.get('name'),
            'family': x.get('family'),
            'location': x.get('location'),
            'theoretical_qty': x.get('stock_qty'),
            'unit': x.get('base_unit'),
            'counted_qty': None,
            'difference_qty': None,
            'status':'pendiente_conteo_demo',
            'stock_value_2026': x.get('stock_value_2026'),
        })
    return {'ok':True,'mode':'BAR_INVENTORY_LAB_PREPARADO','items':items,'totals':stock.get('totals',{}),'rules':['Inventario Bar separado.','El conteo real se implementará como sesión propia: responsable, estado y auditoría.','Esta pantalla solo muestra stock teórico demo para preparar el flujo.'],'demo_data':True,'DATOS_DEMO_NO_PRODUCTIVOS':True}


def get_bar_beverage_summary() -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_bar_beverage_schema(cur)
    try:
        if int(cur.execute('SELECT COUNT(*) c FROM bar_beverage_services WHERE demo_data=1').fetchone()['c'] or 0) == 0:
            conn.close(); load_bar_beverage_demo(); conn = db(); cur = conn.cursor(); ensure_bar_beverage_schema(cur)
        counts = {}
        for key, table in [('services','bar_beverage_services'),('service_lines','bar_beverage_service_lines'),('pour_sizes','bar_pour_sizes'),('open_bottles','bar_open_bottles')]:
            row = cur.execute(f'SELECT COUNT(*) c FROM {table} WHERE demo_data=1').fetchone(); counts[key] = int(row['c'] or 0)
        services = [dict(r) for r in cur.execute('SELECT id,code,name,service_type,billing_mode,bundle_sale_price,separate_sale_price_total,suggested_price,cost_total_2026,margin_percent_2026,theoretical_servings,notes FROM bar_beverage_services WHERE demo_data=1 ORDER BY service_type,name').fetchall()]
        pours = [dict(r) for r in cur.execute('SELECT code,name,service_type,qty_ml FROM bar_pour_sizes WHERE demo_data=1 ORDER BY service_type,qty_ml').fetchall()]
        open_bottles = [dict(r) for r in cur.execute('SELECT item_name,bottle_code,bottle_ml,theoretical_ml_remaining,oxidation_waste_percent,shelf_life_days,status FROM bar_open_bottles WHERE demo_data=1 ORDER BY item_name').fetchall()]
        return {'ok': True, 'counts': counts, 'services': services, 'pour_sizes': pours, 'open_bottles': open_bottles, 'rules': ['Refresco puede venderse solo o usarse como mixer.', 'Combinado puede cobrarse como precio completo o líneas separadas según TPV.', 'Stock siempre descuenta componentes reales.', 'Vino por copas controla botella abierta, copas teóricas y merma/oxidación.'], 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    finally:
        conn.close()


def get_bar_beverage_detail(service_id: int) -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_bar_beverage_schema(cur)
    try:
        svc = cur.execute('SELECT * FROM bar_beverage_services WHERE id=?', (int(service_id),)).fetchone()
        if not svc: return {'ok': False, 'message': 'Servicio de bebida no encontrado.'}
        lines = [dict(r) for r in cur.execute('SELECT * FROM bar_beverage_service_lines WHERE beverage_service_id=? ORDER BY id', (int(service_id),)).fetchall()]
        return {'ok': True, 'service': dict(svc), 'lines': lines}
    finally:
        conn.close()


def simulate_bar_beverage_sale(service_code: str = 'BAR-SVC-VODKA-REDBULL-001', billing_mode: str = '') -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_bar_beverage_schema(cur)
    try:
        if int(cur.execute('SELECT COUNT(*) c FROM bar_beverage_services WHERE demo_data=1').fetchone()['c'] or 0) == 0:
            conn.close(); load_bar_beverage_demo(); conn = db(); cur = conn.cursor(); ensure_bar_beverage_schema(cur)
        svc = cur.execute('SELECT * FROM bar_beverage_services WHERE code=? AND demo_data=1', ((service_code or '').strip(),)).fetchone()
        if not svc: return {'ok': False, 'message': 'Servicio no encontrado.'}
        lines = [dict(r) for r in cur.execute('SELECT * FROM bar_beverage_service_lines WHERE beverage_service_id=? ORDER BY id', (int(svc['id']),)).fetchall()]
        mode = (billing_mode or svc['billing_mode'] or 'bundle_price').strip()
        if mode == 'separate_lines':
            ticket_lines = [{'name': ln['item_name'], 'qty': 1, 'price': float(ln['sale_price_component'] or 0), 'role': ln.get('component_role')} for ln in lines if float(ln.get('sale_price_component') or 0) > 0]
            total_ticket = sum(x['price'] for x in ticket_lines)
        else:
            ticket_lines = [{'name': svc['name'], 'qty': 1, 'price': float(svc['bundle_sale_price'] or 0), 'role': 'bundle'}]
            total_ticket = float(svc['bundle_sale_price'] or 0)
        consumption = [{'item_name': ln['item_name'], 'qty_theoretical': float(ln['qty_gross'] or 0), 'unit': ln['unit'], 'cost_total_preview': float(ln['cost_total_gross_2026'] or 0), 'stock_pool': 'Stock Bar'} for ln in lines]
        return {'ok': True, 'message': 'Venta bebida Barra simulada en PREVIEW. No descuenta stock.', 'mode': 'BAR_BEVERAGE_SERVICE_PREVIEW_NO_PRODUCTIVO', 'service': dict(svc), 'billing_mode_used': mode, 'ticket_lines_preview': ticket_lines, 'ticket_total_preview': total_ticket, 'consumption_preview': consumption, 'cost_total_preview': float(svc['cost_total_2026'] or 0), 'margin_percent_preview': ((total_ticket - float(svc['cost_total_2026'] or 0)) / total_ticket * 100.0) if total_ticket else 0.0, 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    finally:
        conn.close()


# ==============================================================================
# ALBARANES/OCR BEBIDAS → STOCK BAR / INVENTARIO BAR · LAB SEGURO
# ==============================================================================

def ensure_bar_receipt_schema(cur) -> None:
    ensure_bar_beverage_schema(cur)
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_stock_balances(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT, restaurant_id TEXT, bar_id TEXT, bar_item_id INTEGER,
        item_name TEXT, qty_available REAL DEFAULT 0, unit TEXT,
        last_movement_at TEXT, demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,bar_item_id)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_receipts(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT, restaurant_id TEXT, bar_id TEXT,
        document_code TEXT, supplier_name TEXT, receipt_date TEXT,
        source_module TEXT DEFAULT 'ocr_bebidas_lab', status TEXT,
        classification_status TEXT, total_amount REAL DEFAULT 0,
        demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,document_code)
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_receipt_lines(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bar_receipt_id INTEGER, raw_text TEXT, item_name_raw TEXT,
        bar_item_id INTEGER, matched_item_name TEXT,
        qty REAL DEFAULT 0, unit TEXT, purchase_unit TEXT,
        unit_price REAL DEFAULT 0, amount REAL DEFAULT 0,
        classification TEXT, destination_area TEXT, destination_stock TEXT,
        validation_status TEXT, split_required INTEGER DEFAULT 0,
        notes TEXT, demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_supplier_item_prices(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT, restaurant_id TEXT, bar_id TEXT,
        supplier_name TEXT, bar_item_id INTEGER, item_name TEXT,
        purchase_unit TEXT, purchase_qty REAL DEFAULT 0,
        purchase_price REAL DEFAULT 0, cost_per_base_unit REAL DEFAULT 0,
        source_receipt_id INTEGER, source_receipt_line_id INTEGER,
        price_year TEXT DEFAULT '2026', active INTEGER DEFAULT 1,
        demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_inventory_movements(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT, restaurant_id TEXT, bar_id TEXT,
        bar_item_id INTEGER, item_name TEXT,
        movement_type TEXT, qty REAL DEFAULT 0, unit TEXT,
        source_module TEXT, source_receipt_id INTEGER, source_receipt_line_id INTEGER,
        affects_inventory INTEGER DEFAULT 1, notes TEXT,
        demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT
    )""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_receipt_cost_recalc_log(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bar_receipt_id INTEGER, bar_receipt_line_id INTEGER, bar_item_id INTEGER,
        item_name TEXT, affected_type TEXT, affected_id INTEGER, affected_name TEXT,
        old_cost REAL DEFAULT 0, new_cost REAL DEFAULT 0,
        recalculated_at TEXT, demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1
    )""")


def _classify_bar_receipt_line(name: str) -> Dict[str, Any]:
    n = _norm(name)
    alcohol = ['ron','ginebra','vodka','tequila','cointreau','triple sec','campari','bourbon','whisky','vermut','angostura']
    wine = ['vino','cava','champagne','prosecco']
    beer = ['cerveza','barril','lager','ipa']
    mixer = ['tonica','tónica','cola','ginger beer','soda','red bull','arandano','arándano','refresco']
    shared = ['lima','limon','limón','naranja','hierbabuena','azucar','azúcar','sal']
    if any(k in n for k in alcohol):
        return {'classification':'barra_alcohol','destination_area':'barra_bebidas','destination_stock':'Stock Bar','split_required':0}
    if any(k in n for k in wine):
        return {'classification':'barra_vino','destination_area':'barra_bebidas','destination_stock':'Stock Bar','split_required':0}
    if any(k in n for k in beer):
        return {'classification':'barra_cerveza','destination_area':'barra_bebidas','destination_stock':'Stock Bar','split_required':0}
    if any(k in n for k in mixer):
        return {'classification':'barra_mixer_refresco','destination_area':'barra_bebidas','destination_stock':'Stock Bar','split_required':0}
    if any(k in n for k in shared):
        return {'classification':'compartido_cocina_barra_revision','destination_area':'revision_reparto','destination_stock':'Pendiente reparto','split_required':1}
    return {'classification':'revision','destination_area':'revision','destination_stock':'Pendiente revisión','split_required':1}


def _ensure_bar_item_for_receipt(cur, name: str, unit: str, qty: float, amount: float, classification: str) -> int | None:
    item_map = _bar_item_by_name(cur)
    row = item_map.get(_norm(name))
    if row:
        return int(row['id'])
    # Solo alta automática en LAB para bebidas claramente de Barra. Cocina/compartidos quedan revisión.
    if not str(classification or '').startswith('barra_'):
        return None
    now = _now()
    cost_unit = (float(amount or 0) / float(qty or 1)) if float(qty or 0) else 0.0
    family = 'bebidas'
    item_type = 'bebida_bar'
    if classification == 'barra_alcohol': family='alcoholes'; item_type='botella_alcohol'
    elif classification == 'barra_vino': family='vinos'; item_type='vino'
    elif classification == 'barra_cerveza': family='cervezas'; item_type='cerveza'
    elif classification == 'barra_mixer_refresco': family='mixers'; item_type='mixer'
    code = 'AUTO-BAR-' + re.sub(r'[^A-Z0-9]+','-', _norm(name).upper()).strip('-')[:40]
    cur.execute("""INSERT INTO bar_items(business_id,restaurant_id,bar_id,code,name,normalized_name,item_type,family,base_unit,purchase_unit,purchase_qty,purchase_price_2025,purchase_price_2026,cost_per_base_unit_2026,standard_waste_percent,supplier_name_demo,min_stock,max_stock,location,active,demo_data,non_productive_demo,data_scope,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                   ON CONFLICT(business_id,restaurant_id,bar_id,normalized_name) DO UPDATE SET updated_at=excluded.updated_at""",
                (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,code,name,_norm(name),item_type,family,unit,unit,float(qty or 0),0,float(amount or 0),cost_unit,1,DEMO_PROVIDER,0,0,'almacén_bar',1,1,1,'demo',now,now))
    return int(cur.execute('SELECT id FROM bar_items WHERE business_id=? AND restaurant_id=? AND bar_id=? AND normalized_name=?', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,_norm(name))).fetchone()['id'])


def _update_bar_balance(cur, item_id: int, item_name: str, qty: float, unit: str, now: str) -> None:
    row = cur.execute('SELECT qty_available FROM bar_stock_balances WHERE business_id=? AND restaurant_id=? AND bar_id=? AND bar_item_id=?', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,int(item_id))).fetchone()
    if row:
        new_qty = float(row['qty_available'] or 0) + float(qty or 0)
        cur.execute('UPDATE bar_stock_balances SET qty_available=?,unit=?,last_movement_at=?,updated_at=? WHERE business_id=? AND restaurant_id=? AND bar_id=? AND bar_item_id=?', (new_qty,unit,now,now,DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,int(item_id)))
    else:
        cur.execute('INSERT INTO bar_stock_balances(business_id,restaurant_id,bar_id,bar_item_id,item_name,qty_available,unit,last_movement_at,demo_data,non_productive_demo,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,int(item_id),item_name,float(qty or 0),unit,now,1,1,now,now))


def _recalc_bar_costs_for_item(cur, item_id: int, item_name: str, receipt_id: int, receipt_line_id: int, now: str) -> List[Dict[str, Any]]:
    affected: List[Dict[str, Any]] = []
    # Cócteles: líneas directas de Stock Bar.
    for ln in cur.execute('SELECT * FROM cocktail_recipe_lines WHERE bar_item_id=?', (int(item_id),)).fetchall():
        old = float(ln['cost_total_gross_2026'] or 0)
        item = cur.execute('SELECT cost_per_base_unit_2026 FROM bar_items WHERE id=?', (int(item_id),)).fetchone()
        cost_unit = float(item['cost_per_base_unit_2026'] or 0) if item else float(ln['cost_unit_2026'] or 0)
        net = float(ln['qty_net'] or 0) * cost_unit
        gross = _qty_gross(float(ln['qty_net'] or 0), float(ln['waste_percent'] or 0)) * cost_unit
        cur.execute('UPDATE cocktail_recipe_lines SET cost_unit_2026=?,cost_total_net_2026=?,cost_total_gross_2026=? WHERE id=?', (cost_unit,net,gross,int(ln['id'])))
        rid = int(ln['cocktail_recipe_id'])
        sums = cur.execute('SELECT COALESCE(SUM(cost_total_net_2026),0) net, COALESCE(SUM(cost_total_gross_2026),0) gross FROM cocktail_recipe_lines WHERE cocktail_recipe_id=?', (rid,)).fetchone()
        rec = cur.execute('SELECT name,sale_price,target_margin_percent,serving_size_ml FROM cocktail_recipes WHERE id=?', (rid,)).fetchone()
        if rec:
            gross_total = float(sums['gross'] or 0); net_total=float(sums['net'] or 0); sale=float(rec['sale_price'] or 0); target=float(rec['target_margin_percent'] or 0)
            margin = ((sale-gross_total)/sale*100.0) if sale else 0.0
            suggested = gross_total/(1-target/100.0) if target and target<100 else 0.0
            cost_ml = gross_total/float(rec['serving_size_ml'] or 1)
            cur.execute('UPDATE cocktail_recipes SET cost_2026_net=?,cost_2026_gross_with_waste=?,margin_percent_2026=?,suggested_price=?,cost_per_ml=?,updated_at=? WHERE id=?', (net_total,gross_total,margin,suggested,cost_ml,now,rid))
            cur.execute('INSERT INTO cocktail_cost_history(cocktail_recipe_id,cost_per_serving_net_2026,cost_per_serving_gross_2026,sale_price,margin_percent,calculated_at,source,notes,demo_data,non_productive_demo) VALUES(?,?,?,?,?,?,?,?,?,?)', (rid,net_total,gross_total,sale,margin,now,'bar_receipt_lab','Recalculado por albarán OCR bebidas LAB.',1,1))
            cur.execute('INSERT INTO bar_receipt_cost_recalc_log(bar_receipt_id,bar_receipt_line_id,bar_item_id,item_name,affected_type,affected_id,affected_name,old_cost,new_cost,recalculated_at,demo_data,non_productive_demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (receipt_id,receipt_line_id,item_id,item_name,'cocktail_recipe',rid,rec['name'],old,gross,now,1,1))
            affected.append({'type':'cocktail_recipe','id':rid,'name':rec['name'],'old_line_cost':old,'new_line_cost':gross})
    # Bebidas por servicio.
    for ln in cur.execute('SELECT * FROM bar_beverage_service_lines WHERE bar_item_id=?', (int(item_id),)).fetchall():
        old = float(ln['cost_total_gross_2026'] or 0)
        item = cur.execute('SELECT cost_per_base_unit_2026 FROM bar_items WHERE id=?', (int(item_id),)).fetchone()
        cost_unit = float(item['cost_per_base_unit_2026'] or 0) if item else float(ln['cost_unit_2026'] or 0)
        net = float(ln['qty_net'] or 0) * cost_unit
        gross = _qty_gross(float(ln['qty_net'] or 0), float(ln['waste_percent'] or 0)) * cost_unit
        cur.execute('UPDATE bar_beverage_service_lines SET cost_unit_2026=?,cost_total_net_2026=?,cost_total_gross_2026=? WHERE id=?', (cost_unit,net,gross,int(ln['id'])))
        sid = int(ln['beverage_service_id'])
        total = cur.execute('SELECT COALESCE(SUM(cost_total_gross_2026),0) gross FROM bar_beverage_service_lines WHERE beverage_service_id=?', (sid,)).fetchone()
        svc = cur.execute('SELECT name,bundle_sale_price,target_margin_percent FROM bar_beverage_services WHERE id=?', (sid,)).fetchone()
        if svc:
            gross_total=float(total['gross'] or 0); sale=float(svc['bundle_sale_price'] or 0); target=float(svc['target_margin_percent'] or 0)
            margin=((sale-gross_total)/sale*100.0) if sale else 0.0
            suggested=gross_total/(1-target/100.0) if target and target<100 else 0.0
            cur.execute('UPDATE bar_beverage_services SET cost_total_2026=?,margin_percent_2026=?,suggested_price=?,updated_at=? WHERE id=?', (gross_total,margin,suggested,now,sid))
            cur.execute('INSERT INTO bar_beverage_service_history(beverage_service_id,cost_total_2026,bundle_sale_price,margin_percent_2026,calculated_at,source,notes,demo_data,non_productive_demo) VALUES(?,?,?,?,?,?,?,?,?)', (sid,gross_total,sale,margin,now,'bar_receipt_lab','Recalculado por albarán OCR bebidas LAB.',1,1))
            cur.execute('INSERT INTO bar_receipt_cost_recalc_log(bar_receipt_id,bar_receipt_line_id,bar_item_id,item_name,affected_type,affected_id,affected_name,old_cost,new_cost,recalculated_at,demo_data,non_productive_demo) VALUES(?,?,?,?,?,?,?,?,?,?,?,?)', (receipt_id,receipt_line_id,item_id,item_name,'beverage_service',sid,svc['name'],old,gross,now,1,1))
            affected.append({'type':'beverage_service','id':sid,'name':svc['name'],'old_line_cost':old,'new_line_cost':gross})
    return affected


def simulate_bar_beverage_receipt(receipt_variant: str = 'beverages') -> Dict[str, Any]:
    """Simula lectura OCR/validación de albarán de bebidas hacia Stock Bar e Inventario Bar.
    LAB seguro: solo demo/no productivo. No toca Stock Cocina salvo líneas compartidas con revisión.
    """
    conn = db(); cur = conn.cursor(); ensure_bar_receipt_schema(cur)
    try:
        if int(cur.execute('SELECT COUNT(*) c FROM bar_items WHERE demo_data=1').fetchone()['c'] or 0) == 0:
            conn.close(); load_cocktail_bar_demo(); conn = db(); cur = conn.cursor(); ensure_bar_receipt_schema(cur)
        if int(cur.execute('SELECT COUNT(*) c FROM bar_beverage_services WHERE demo_data=1').fetchone()['c'] or 0) == 0:
            conn.close(); load_bar_beverage_demo(); conn = db(); cur = conn.cursor(); ensure_bar_receipt_schema(cur)
        now = _now()
        import uuid
        doc = 'ALB-BEBIDAS-DEMO-2026-' + uuid.uuid4().hex[:6].upper()
        raw_lines = [
            {'name':'Ginebra','qty':4200,'unit':'ml','purchase_unit':'6 botellas 700ml','amount':81.90},
            {'name':'Vodka','qty':2800,'unit':'ml','purchase_unit':'4 botellas 700ml','amount':47.16},
            {'name':'Vino Blanco Demo','qty':4500,'unit':'ml','purchase_unit':'6 botellas 750ml','amount':36.00},
            {'name':'Cerveza botella Demo','qty':9900,'unit':'ml','purchase_unit':'30 botellas 330ml','amount':30.00},
            {'name':'Cola','qty':8000,'unit':'ml','purchase_unit':'2 packs 4l','amount':8.18},
            {'name':'Red Bull Demo','qty':3000,'unit':'ml','purchase_unit':'12 latas 250ml','amount':14.40},
        ]
        if (receipt_variant or '').strip().lower() in ('shared','compartido'):
            raw_lines.append({'name':'Lima','qty':3000,'unit':'gr','purchase_unit':'3 kg','amount':11.91})
        total = sum(float(x['amount']) for x in raw_lines)
        cur.execute("""INSERT INTO bar_receipts(business_id,restaurant_id,bar_id,document_code,supplier_name,receipt_date,source_module,status,classification_status,total_amount,demo_data,non_productive_demo,created_at,updated_at)
                       VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,doc,DEMO_PROVIDER,now[:10],'ocr_bebidas_lab','validado_demo','clasificado_barra',total,1,1,now,now))
        receipt_id = int(cur.lastrowid)
        validated=[]; review=[]; movements=[]; recalculated=[]
        for rl in raw_lines:
            cls = _classify_bar_receipt_line(rl['name'])
            item_id = _ensure_bar_item_for_receipt(cur, rl['name'], rl['unit'], rl['qty'], rl['amount'], cls['classification'])
            unit_price = float(rl['amount'] or 0) / float(rl['qty'] or 1)
            validation_status = 'validado_stock_bar' if item_id and not cls['split_required'] else 'revision_reparto_o_clasificacion'
            cur.execute("""INSERT INTO bar_receipt_lines(bar_receipt_id,raw_text,item_name_raw,bar_item_id,matched_item_name,qty,unit,purchase_unit,unit_price,amount,classification,destination_area,destination_stock,validation_status,split_required,notes,demo_data,non_productive_demo,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                        (receipt_id,f"{rl['name']} {rl['qty']} {rl['unit']} {rl['amount']}€",rl['name'],item_id,rl['name'] if item_id else '',float(rl['qty']),rl['unit'],rl['purchase_unit'],unit_price,float(rl['amount']),cls['classification'],cls['destination_area'],cls['destination_stock'],validation_status,int(cls['split_required']),'OCR bebidas LAB demo. Validación humana simulada.' if validation_status.startswith('validado') else 'Línea compartida/dudosa: no entra en Cocina ni Barra sin reparto validado.',1,1,now,now))
            line_id = int(cur.lastrowid)
            if item_id and validation_status == 'validado_stock_bar':
                cur.execute('UPDATE bar_items SET purchase_price_2026=?,cost_per_base_unit_2026=?,supplier_name_demo=?,updated_at=? WHERE id=?', (float(rl['amount']),unit_price,DEMO_PROVIDER,now,int(item_id)))
                cur.execute('INSERT INTO bar_supplier_item_prices(business_id,restaurant_id,bar_id,supplier_name,bar_item_id,item_name,purchase_unit,purchase_qty,purchase_price,cost_per_base_unit,source_receipt_id,source_receipt_line_id,price_year,active,demo_data,non_productive_demo,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,DEMO_PROVIDER,int(item_id),rl['name'],rl['purchase_unit'],float(rl['qty']),float(rl['amount']),unit_price,receipt_id,line_id,'2026',1,1,1,now,now))
                cur.execute('INSERT INTO bar_stock_movements(business_id,restaurant_id,bar_id,bar_item_id,movement_type,qty,unit,document_code,source_module,responsible_name,movement_datetime,notes,demo_data,non_productive_demo,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,int(item_id),'entrada',float(rl['qty']),rl['unit'],doc,'ocr_bebidas_lab','Sistema Demo',now,'Entrada por albarán de bebidas LAB validado. Afecta Stock Bar e Inventario Bar.',1,1,now))
                _update_bar_balance(cur, int(item_id), rl['name'], float(rl['qty']), rl['unit'], now)
                cur.execute('INSERT INTO bar_inventory_movements(business_id,restaurant_id,bar_id,bar_item_id,item_name,movement_type,qty,unit,source_module,source_receipt_id,source_receipt_line_id,affects_inventory,notes,demo_data,non_productive_demo,created_at) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)', (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,int(item_id),rl['name'],'entrada_inventario_bar',float(rl['qty']),rl['unit'],'ocr_bebidas_lab',receipt_id,line_id,1,'Inventario Bar actualizado por entrada validada de albarán bebidas LAB.',1,1,now))
                movements.append({'item_name':rl['name'],'qty':rl['qty'],'unit':rl['unit'],'destination':'Stock Bar + Inventario Bar','cost_per_base_unit':unit_price})
                recalculated.extend(_recalc_bar_costs_for_item(cur,int(item_id),rl['name'],receipt_id,line_id,now))
                validated.append({'item_name':rl['name'],'classification':cls['classification'],'qty':rl['qty'],'unit':rl['unit'],'destination':'Stock Bar / Inventario Bar'})
            else:
                review.append({'item_name':rl['name'],'classification':cls['classification'],'qty':rl['qty'],'unit':rl['unit'],'status':'revision','reason':'Compartido o clasificación dudosa; requiere reparto antes de validar.'})
        conn.commit()
        return {'ok': True, 'message':'Albarán OCR bebidas LAB simulado y validado hacia Stock Bar. No productivo.', 'mode':'BAR_RECEIPT_OCR_TO_STOCK_BAR_PREVIEW_NO_PRODUCTIVO', 'receipt_id':receipt_id, 'document_code':doc, 'validated_lines':validated, 'review_lines':review, 'stock_movements_created':movements, 'cost_recalculations':recalculated, 'rules':['Bebidas/alcohol/vino/cerveza/mixers entran en Stock Bar e Inventario Bar.', 'Líneas compartidas como lima/azúcar/sal quedan en revisión salvo reparto validado.', 'No se toca Stock Cocina desde albarán de bebidas.', 'Costes de cócteles y bebidas por servicio se recalculan con el nuevo coste unitario.'], 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    except Exception as exc:
        conn.rollback(); return {'ok': False, 'message': f'Error simulando albarán bebidas: {exc}'}
    finally:
        conn.close()


def get_bar_receipt_summary() -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_bar_receipt_schema(cur)
    try:
        receipts=[dict(r) for r in cur.execute('SELECT id,document_code,supplier_name,receipt_date,status,classification_status,total_amount,created_at FROM bar_receipts WHERE demo_data=1 ORDER BY id DESC LIMIT 5').fetchall()]
        latest=receipts[0] if receipts else None
        lines=[]; movements=[]; recalcs=[]
        if latest:
            rid=int(latest['id'])
            lines=[dict(r) for r in cur.execute('SELECT item_name_raw,qty,unit,classification,destination_stock,validation_status,split_required,notes FROM bar_receipt_lines WHERE bar_receipt_id=? ORDER BY id', (rid,)).fetchall()]
            movements=[dict(r) for r in cur.execute('SELECT item_name,qty,unit,movement_type,source_module,created_at FROM bar_inventory_movements WHERE source_receipt_id=? ORDER BY id', (rid,)).fetchall()]
            recalcs=[dict(r) for r in cur.execute('SELECT item_name,affected_type,affected_name,old_cost,new_cost,recalculated_at FROM bar_receipt_cost_recalc_log WHERE bar_receipt_id=? ORDER BY id DESC LIMIT 50', (rid,)).fetchall()]
        counts={}
        for key,table in [('receipts','bar_receipts'),('lines','bar_receipt_lines'),('stock_movements','bar_stock_movements'),('inventory_movements','bar_inventory_movements'),('price_updates','bar_supplier_item_prices')]:
            try:
                row=cur.execute(f'SELECT COUNT(*) c FROM {table} WHERE demo_data=1').fetchone(); counts[key]=int(row['c'] or 0)
            except Exception: counts[key]=0
        return {'ok': True, 'counts':counts, 'receipts':receipts, 'latest':latest, 'lines':lines, 'inventory_movements':movements, 'cost_recalculations':recalcs, 'rules':['Albarán bebidas → Stock Bar / Inventario Bar.', 'Compartidos → revisión/reparto.', 'No Stock Cocina salvo reparto validado.'], 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    finally:
        conn.close()


# ==============================================================================
# MIXERS / REFRESCOS MULTI-SERVICIO · BARRA LAB
# ==============================================================================

def ensure_bar_mixer_container_schema(cur) -> None:
    ensure_bar_beverage_schema(cur)
    _ensure_col(cur, 'bar_items', 'container_type', "TEXT DEFAULT ''")
    _ensure_col(cur, 'bar_items', 'container_volume_ml', 'REAL DEFAULT 0')
    _ensure_col(cur, 'bar_items', 'is_multi_serve', 'INTEGER DEFAULT 0')
    _ensure_col(cur, 'bar_items', 'opened_container_tracking', 'INTEGER DEFAULT 0')
    _ensure_col(cur, 'bar_items', 'shelf_life_after_opening_hours', 'REAL DEFAULT 0')
    _ensure_col(cur, 'bar_items', 'gas_loss_percent', 'REAL DEFAULT 0')
    _ensure_col(cur, 'bar_items', 'standard_serving_ml', 'REAL DEFAULT 0')
    cur.execute("""CREATE TABLE IF NOT EXISTS bar_open_mixer_containers(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        business_id TEXT, restaurant_id TEXT, bar_id TEXT,
        bar_item_id INTEGER, item_name TEXT, container_code TEXT,
        container_type TEXT, initial_ml REAL DEFAULT 0, used_ml REAL DEFAULT 0,
        remaining_ml REAL DEFAULT 0, waste_ml REAL DEFAULT 0,
        opened_at TEXT, responsible TEXT, location TEXT, status TEXT,
        demo_data INTEGER DEFAULT 1, non_productive_demo INTEGER DEFAULT 1,
        created_at TEXT, updated_at TEXT,
        UNIQUE(business_id,restaurant_id,bar_id,container_code)
    )""")


def load_bar_mixer_container_demo() -> Dict[str, Any]:
    conn=db(); cur=conn.cursor(); ensure_bar_mixer_container_schema(cur)
    try:
        if int(cur.execute('SELECT COUNT(*) c FROM bar_items WHERE demo_data=1').fetchone()['c'] or 0) == 0:
            conn.close(); load_cocktail_bar_demo(); conn=db(); cur=conn.cursor(); ensure_bar_mixer_container_schema(cur)
        now=_now()
        configs={
            'Cola': {'container_type':'botella_multi_servicio','container_volume_ml':2000,'is_multi_serve':1,'opened_container_tracking':1,'shelf_life_after_opening_hours':24,'gas_loss_percent':5,'standard_serving_ml':200},
            'Soda / Agua con Gas': {'container_type':'botella_multi_servicio','container_volume_ml':1000,'is_multi_serve':1,'opened_container_tracking':1,'shelf_life_after_opening_hours':12,'gas_loss_percent':7,'standard_serving_ml':100},
            'Tónica': {'container_type':'botella_multi_servicio','container_volume_ml':1000,'is_multi_serve':1,'opened_container_tracking':1,'shelf_life_after_opening_hours':12,'gas_loss_percent':5,'standard_serving_ml':200},
            'Red Bull Demo': {'container_type':'lata_individual','container_volume_ml':250,'is_multi_serve':0,'opened_container_tracking':0,'shelf_life_after_opening_hours':0,'gas_loss_percent':0,'standard_serving_ml':250},
            'Ginger Beer': {'container_type':'botella_individual','container_volume_ml':200,'is_multi_serve':0,'opened_container_tracking':0,'shelf_life_after_opening_hours':0,'gas_loss_percent':0,'standard_serving_ml':120},
        }
        item_map=_bar_item_by_name(cur); updated=0
        for name,cfg in configs.items():
            row=item_map.get(_norm(name))
            if not row: continue
            cur.execute('UPDATE bar_items SET container_type=?,container_volume_ml=?,is_multi_serve=?,opened_container_tracking=?,shelf_life_after_opening_hours=?,gas_loss_percent=?,standard_serving_ml=?,updated_at=? WHERE id=?', (cfg['container_type'],cfg['container_volume_ml'],cfg['is_multi_serve'],cfg['opened_container_tracking'],cfg['shelf_life_after_opening_hours'],cfg['gas_loss_percent'],cfg['standard_serving_ml'],now,int(row['id'])))
            updated += 1
        # Envase abierto demo de Cola 2L con usos parciales: whisky cola, cuba libre y cola sola.
        cola=item_map.get(_norm('Cola'))
        if cola:
            initial=2000.0; used=200+150+237; remaining=initial-used; waste=0.0
            cur.execute("""INSERT INTO bar_open_mixer_containers(business_id,restaurant_id,bar_id,bar_item_id,item_name,container_code,container_type,initial_ml,used_ml,remaining_ml,waste_ml,opened_at,responsible,location,status,demo_data,non_productive_demo,created_at,updated_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                           ON CONFLICT(business_id,restaurant_id,bar_id,container_code) DO UPDATE SET used_ml=excluded.used_ml,remaining_ml=excluded.remaining_ml,updated_at=excluded.updated_at""", (DEMO_BUSINESS_ID,DEMO_RESTAURANT_ID,DEMO_BAR_ID,int(cola['id']),'Cola','OPEN-COLA-2L-DEMO-001','botella_multi_servicio',initial,used,remaining,waste,now,'Sistema Demo','barra','abierto_demo',1,1,now,now))
        conn.commit(); return {'ok': True, 'message':'Mixers/refrescos multi-servicio configurados. No productivo.', 'items_updated':updated, 'open_container_demo':'OPEN-COLA-2L-DEMO-001', 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    except Exception as exc:
        conn.rollback(); return {'ok': False, 'message': f'Error cargando envases multi-servicio: {exc}'}
    finally:
        conn.close()


def get_bar_mixer_container_summary() -> Dict[str, Any]:
    conn=db(); cur=conn.cursor(); ensure_bar_mixer_container_schema(cur)
    try:
        # carga automática segura
        if int(cur.execute('SELECT COUNT(*) c FROM bar_open_mixer_containers WHERE demo_data=1').fetchone()['c'] or 0) == 0:
            conn.close(); load_bar_mixer_container_demo(); conn=db(); cur=conn.cursor(); ensure_bar_mixer_container_schema(cur)
        items=[dict(r) for r in cur.execute("SELECT name,container_type,container_volume_ml,is_multi_serve,opened_container_tracking,shelf_life_after_opening_hours,gas_loss_percent,standard_serving_ml FROM bar_items WHERE demo_data=1 AND family='mixers' ORDER BY name").fetchall()]
        open_containers=[dict(r) for r in cur.execute('SELECT item_name,container_code,container_type,initial_ml,used_ml,remaining_ml,waste_ml,status FROM bar_open_mixer_containers WHERE demo_data=1 ORDER BY id DESC LIMIT 10').fetchall()]
        return {'ok': True, 'items':items, 'open_containers':open_containers, 'rules':['Envase individual: descuenta envase/servicio completo si procede.', 'Envase multi-servicio: descuenta ml servidos.', 'Controla ml iniciales, usados, restantes, merma/gas y caducidad tras apertura.'], 'demo_data': True, 'DATOS_DEMO_NO_PRODUCTIVOS': True}
    finally:
        conn.close()
