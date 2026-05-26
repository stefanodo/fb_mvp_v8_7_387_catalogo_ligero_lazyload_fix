#!/usr/bin/env python3
import sqlite3, re, unicodedata, os, shutil, sys, datetime
from pathlib import Path

PREP_EXACT_OR_PREFIX = {'AGUACHILE','AGUACHILES','FONDO BLANCO','FONDO OSCURO','DEMI GLACE','DEMI-GLACE','CALDO/STOCK LIQUIDO','CALDO STOCK LIQUIDO','SALSA BASE COCINA CENTRAL'}
# Default estimated market prices by product/family, visible €/kg or €/ud.
PRICE_MAP = {
 'ACEITE GIRASOL':1.85,'ACEITE OLIVA VIRGEN EXTRA':7.80,'ACEITUNA NEGRA':4.20,'ACEITUNA VERDE':3.80,'ACELGA':2.10,'AGUACATE':5.90,'AGUACATE HASS':5.90,
 'AJO':5.50,'ALBAHACA':18.00,'ALCACHOFA':3.80,'ALCAPARRAS':7.50,'ALGAS NORI':160.71,'ALMEJA':14.00,'ANCHOA':18.00,'APIO':1.80,
 'ARROZ':1.60,'ARROZ THAI':2.69,'ATUN':18.00,'ATUN EN CONSERVA':9.50,'AZUCAR':1.25,'BACALAO':14.00,'BACON':8.50,'BERENJENA':2.20,
 'BOLSAS BASURA':0.08,'BONIATO':2.20,'BRANDY COCINA':8.50,'BROCOLI':2.80,'CACAO EN POLVO':7.00,'CAJA TAKE AWAY M':0.18,'CALABACIN':1.90,
 'CALABAZA':1.70,'CALAMAR':12.00,'CALDO/STOCK LIQUIDO':1.80,'CANELA':16.00,'CARNE PICADA VACUNO':9.50,'CEBOLLA':1.35,'CEBOLLINO':16.00,
 'CERDO LOMO':6.80,'CERVEZA PARA COCINAR':1.60,'CHAMPINON':3.20,'CHOCOLATE NEGRO':7.50,'CHORIZO':7.50,'CILANTRO':15.90,'CLAVO':22.00,
 'COLIFLOR':2.30,'COMINO':14.00,'COSTILLA CERDO':6.50,'CURRY':13.00,'CURCUMA':12.00,'DEMI-GLACE':2.20,'DESENGRASANTE':1.80,'DETERGENTE LAVAVAJILLAS':1.60,
 'ENELDO':18.00,'ENTRECOT':18.00,'ESPINACA CONGELADA':2.20,'ESPINACA FRESCA':3.50,'ESPARRAGO VERDE':6.50,'FIDEOS':2.20,'FIDEOS UDON':12.73,
 'FILM TRANSPARENTE':0.04,'FONDO BLANCO':1.80,'FONDO OSCURO':2.00,'FRIJOL NEGRO':2.50,'FRIJOL ROJO PEQUENO':6.18,'GAMBA':16.00,'GARBANZOS':2.10,
 'GELATINA HOJAS':25.00,'GUANTES NITRILO':0.08,'GUISANTE':3.20,'GUISANTE CONGELADO':2.50,'HABAS':3.80,'HARINA DE MAIZ PRECOCIDA':2.45,
 'HARINA FUERZA':1.25,'HARINA TRIGO':0.95,'HUESOS DE POLLO':1.20,'HUESOS DE TERNERA':2.20,'HUEVOS':0.24,'JALAPENO EN RODAJAS':15.94,
 'JAMON SERRANO':16.00,'JARABE DE ARCE':37.16,'JENGIBRE FRESCO':7.95,'JUDIA BLANCA':2.30,'JUDIA VERDE':3.50,'KETCHUP':3.50,
 'LANGOSTINO':16.00,'LANGOSTINO CONGELADO':13.00,'LAUREL':15.00,'LECHE ENTERA':1.20,'LECHUGA ICEBERG':1.80,'LECHUGA ROMANA':2.00,'LEJIA':0.70,
 'LENTEJAS':2.10,'LEVADURA SECA':9.00,'LIMA':2.90,'LIMON':2.20,'MAICENA':2.50,'MANTEQUILLA':7.00,'MANZANA':1.90,'MAYONESA':3.80,
 'MAIZ DULCE':3.93,'MEJILLON':4.50,'MENTA':18.00,'MERLUZA':11.50,'MORCILLA':6.00,'MOSTAZA DIJON':5.50,'NARANJA':1.60,
 'NATA PARA COCINAR':2.40,'NUEZ MOSCADA':22.00,'OREGANO':12.00,'PAN PRECOCIDO CONGELADO':0.35,'PAN RALLADO':2.00,'PANKO':23.25,
 'PAPEL ALUMINIO':0.05,'PAPEL HORNO':0.04,'PASTA DE WASABI':52.33,'PASTA SECA':1.80,'PATATA':1.50,'PATATA CONGELADA':1.80,'PAVO PECHUGA':8.50,
 'PEPINILLOS':3.60,'PEPINO':1.60,'PERA':2.10,'PEREJIL':8.00,'PIMENTON DULCE':12.00,'PIMENTON PICANTE':12.00,'PIMIENTA NEGRA':18.00,
 'PIMIENTO ROJO':2.80,'PIMIENTO VERDE':2.20,'PLATANO':1.60,'PLATANO MACHO':2.85,'PLATANO MADURO CONGELADO':12.06,'POLLO MUSLO':4.20,
 'POLLO PECHUGA':6.20,'PUERRO':2.00,'PULPO':18.00,'QUESO AZUL':10.00,'QUESO CHEDDAR RALLADO':21.43,'QUESO MOZZARELLA':7.00,
 'QUESO PARMESANO':18.00,'QUINOA BLANCA':5.37,'RAMEN NOODLES':10.76,'REMOLACHA':1.80,'ROMERO':16.00,'RUCULA':7.00,'SAL':0.55,
 'SALMON':15.50,'SALSA BASE COCINA CENTRAL':2.50,'SALSA CHIPOTLE':20.94,'SALSA DE AJI PICANTE':9.95,'SALSA INGLESA':5.20,'SALSA SOJA':2.80,
 'SECRETO IBERICO':14.00,'SERVILLETA COCINA':0.015,'SETAS MIXTAS':6.00,'SOLOMILLO DE TERNERA':24.00,'SEMOLA':1.80,'TABASCO':18.00,
 'TAPA TAKE AWAY M':0.07,'TOMATE CHERRY':3.20,'TOMATE CONCENTRADO':4.00,'TOMATE PERA':1.70,'TOMATE RAMA':1.80,'TOMATE TRITURADO LATA':1.35,
 'TOMILLO':16.00,'TORTILLA DE TRIGO':5.62,'VINAGRE BALSAMICO':4.50,'VINAGRE VINO':1.60,'VINO BLANCO COCINA':2.20,'VINO TINTO COCINA':2.20,
 'YOGUR NATURAL':2.20,'YUCA':3.29,'YUCA CONGELADA':4.10,'ZANAHORIA':1.35,
 'AGUACHILES':7.00,'AGUACHILE':7.00,
}
UNIT_KEEP_UD = {'HUEVOS','BOLSAS BASURA','CAJA TAKE AWAY M','FILM TRANSPARENTE','GUANTES NITRILO','PAN PRECOCIDO CONGELADO','PAPEL ALUMINIO','PAPEL HORNO','SERVILLETA COCINA','TAPA TAKE AWAY M'}
CLEANING = {'DESENGRASANTE','DETERGENTE LAVAVAJILLAS','LEJIA','BOLSAS BASURA','GUANTES NITRILO'}
FISH = {'ALMEJA','ANCHOA','ATUN','BACALAO','CALAMAR','GAMBA','LANGOSTINO','MEJILLON','MERLUZA','PULPO','SALMON'}
MEAT = {'BACON','CARNE PICADA VACUNO','CERDO LOMO','CHORIZO','COSTILLA CERDO','ENTRECOT','HUESOS DE POLLO','HUESOS DE TERNERA','JAMON SERRANO','MORCILLA','PAVO PECHUGA','POLLO MUSLO','POLLO PECHUGA','SECRETO IBERICO','SOLOMILLO DE TERNERA'}
LACTEOS = {'LECHE ENTERA','MANTEQUILLA','NATA PARA COCINAR','QUESO AZUL','QUESO CHEDDAR RALLADO','QUESO MOZZARELLA','QUESO PARMESANO','YOGUR NATURAL'}
VERD = {'ACELGA','AJO','ALBAHACA','ALCACHOFA','APIO','BERENJENA','BONIATO','BROCOLI','CALABACIN','CALABAZA','CEBOLLA','CEBOLLINO','CHAMPINON','CILANTRO','COLIFLOR','ENELDO','ESPINACA FRESCA','ESPARRAGO VERDE','GUISANTE','HABAS','JENGIBRE FRESCO','JUDIA VERDE','LAUREL','LECHUGA ICEBERG','LECHUGA ROMANA','MENTA','PEPINO','PEREJIL','PIMIENTO ROJO','PIMIENTO VERDE','PUERRO','REMOLACHA','ROMERO','RUCULA','SETAS MIXTAS','TOMATE CHERRY','TOMATE PERA','TOMATE RAMA','TOMILLO','ZANAHORIA','AGUACATE','AGUACATE HASS','LIMA','LIMON','MANZANA','NARANJA','PERA','PLATANO','PLATANO MACHO','YUCA'}
CONG = {'ESPINACA CONGELADA','GUISANTE CONGELADO','LANGOSTINO CONGELADO','PAN PRECOCIDO CONGELADO','PATATA CONGELADA','PLATANO MADURO CONGELADO','YUCA CONGELADA'}

def norm(s):
    s = unicodedata.normalize('NFD', str(s or '').upper())
    s = ''.join(c for c in s if unicodedata.category(c)!='Mn')
    s = re.sub(r'[^A-Z0-9]+',' ',s)
    return re.sub(r'\s+',' ',s).strip()

def est_price(name, area=''):
    n = norm(name)
    if n in PRICE_MAP: return PRICE_MAP[n], 'directa'
    for k,v in PRICE_MAP.items():
        if k in n or n in k:
            return v, 'aprox_nombre'
    a=(area or '').upper()
    if a=='LIMPIEZA': return 1.20, 'familia_limpieza'
    if a=='CONGELADOS': return 3.50, 'familia_congelados'
    if a=='FRESCOS': return 3.20, 'familia_frescos'
    return 2.50, 'familia_general'

def desired_unit(name, old_unit):
    n=norm(name)
    if n in UNIT_KEEP_UD or (old_unit or '').lower()=='ud' and any(x in n for x in ['CAJA','TAPA','PAPEL','BOLSA','GUANTE','SERVILLETA','FILM']): return 'ud'
    return 'kg'

def classify(name, old_area=''):
    n=norm(name); typ='INSUMO'; area=(old_area or '').upper() or '' ; cat=''
    if n in PREP_EXACT_OR_PREFIX or n.startswith('AGUACHILE'):
        typ='PREPARACION'; area='PREPARACIONES'; cat='preparaciones'
    elif n in CLEANING: area='LIMPIEZA'; cat='limpieza'
    elif n in CONG: area='CONGELADOS'; cat='congelados'
    elif n=='HUEVOS': area='FRESCOS'; cat='huevos'
    elif n in FISH: area='FRESCOS'; cat='pescados'
    elif n in MEAT: area='FRESCOS'; cat='carnes'
    elif n in LACTEOS: area='FRESCOS'; cat='lacteos'
    elif n in VERD: area='FRESCOS'; cat='verduras'
    elif area == 'PREPARACIONES':
        # Si venía mal clasificado como preparación en una versión anterior,
        # devolverlo a una familia operativa normal salvo que sea elaboración real.
        area = 'SECOS'
    elif area not in ['SECOS','FRESCOS','CONGELADOS','LIMPIEZA','PREPARACIONES','SIN_CLASIFICACION']:
        area='SECOS'
    return typ, area, cat

def coladd(cur, table, name, decl):
    cols={r[1] for r in cur.execute(f'pragma table_info({table})').fetchall()}
    if name not in cols:
        cur.execute(f'alter table {table} add column {name} {decl}')

def normalize_db(path):
    p=Path(path)
    if not p.exists():
        return {'db':str(p),'exists':False}
    backup=p.with_name(p.stem+'_backup_catalogo_'+datetime.datetime.now().strftime('%Y%m%d_%H%M%S')+p.suffix)
    try: shutil.copy2(p,backup)
    except Exception: backup=None
    con=sqlite3.connect(p); con.row_factory=sqlite3.Row; cur=con.cursor()
    for name,decl in [
        ('max_qty','REAL NOT NULL DEFAULT 0'),('current_price','REAL NOT NULL DEFAULT 0'),('waste_default_pct','REAL NOT NULL DEFAULT 0'),
        ('stock_area',"TEXT NOT NULL DEFAULT ''"),('order_category',"TEXT NOT NULL DEFAULT ''"),
        ('item_type',"TEXT NOT NULL DEFAULT 'INSUMO'"),('price_status',"TEXT NOT NULL DEFAULT ''"),('price_source',"TEXT NOT NULL DEFAULT ''"),
        ('price_confidence',"TEXT NOT NULL DEFAULT ''"),('price_reference_year',"TEXT NOT NULL DEFAULT ''"),('price_operational_unit',"TEXT NOT NULL DEFAULT ''"),
        ('price_operational_value',"REAL NOT NULL DEFAULT 0"),('price_notes',"TEXT NOT NULL DEFAULT ''")]:
        coladd(cur,'items',name,decl)
    # produced_item_id if recipes exists
    try: coladd(cur,'recipes','produced_item_id','INTEGER')
    except Exception: pass
    rows=cur.execute('select * from items order by id').fetchall()
    changed=[]; zero_before=0
    for r in rows:
        name=(r['name'] or '').strip(); n=norm(name); old_unit=(r['unit'] or 'kg').lower(); old_price=float(r['current_price'] or 0); old_area=(r['stock_area'] or '')
        if old_price<=0: zero_before += 1
        new_name=name.upper()
        u=desired_unit(n, old_unit)
        typ, area, cat = classify(n, old_area)
        price_eur, why = est_price(n, area)
        # convert any old confirmed? here all non-albaran/proveedor in seed are treated as estimated; preserve no price as estimated.
        if u=='kg': price_base=price_eur
        elif u=='ud': price_base=price_eur
        else: price_base=price_eur
        # min/max conversion if old unit g to kg
        minq=float(r['min_qty'] or 0); maxq=float(r['max_qty'] or 0)
        if old_unit=='g' and u=='kg':
            minq = minq/1000.0 if minq else 0
            maxq = maxq/1000.0 if maxq else 0
        # status: all are estimated unless explicit receipt price source already says confirmed
        status='PRECIO_ESTIMADO'
        source='MERCADO_ESTIMADO_ESP_2025_2026'
        confidence='media' if why in ['directa','aprox_nombre'] else 'baja'
        notes=f'Normalización catálogo: unidad {old_unit}->{u}; precio anterior {old_price:g}; estimación {why}. No confirmado por albarán.'
        cur.execute('''update items set name=?, unit=?, min_qty=?, max_qty=?, current_price=?, stock_area=?, order_category=?, item_type=?, price_status=?, price_source=?, price_confidence=?, price_reference_year=?, price_operational_unit=?, price_operational_value=?, price_notes=? where id=?''',
                    (new_name,u,minq,maxq,price_base,area,cat,typ,status,source,confidence,'2025/2026',u,price_eur,notes,int(r['id'])))
        if old_unit!=u or old_price<=0 or name!=new_name or old_area!=area or (r['order_category'] if 'order_category' in r.keys() else '')!=cat or typ!='INSUMO':
            changed.append((r['id'], name, old_unit, u, old_price, price_base, old_area, area, cat, typ))
    # bind recipes to matching preparation items if names match
    try:
        recipes=cur.execute('select id,name from recipes').fetchall()
        item_by_name={norm(r['name']):r['id'] for r in cur.execute("select id,name from items where item_type='PREPARACION'").fetchall()}
        for rr in recipes:
            key=norm(rr['name'])
            if key in item_by_name:
                cur.execute('update recipes set produced_item_id=? where id=?',(item_by_name[key],rr['id']))
    except Exception: pass
    con.commit();
    zero_after=cur.execute('select count(*) from items where current_price<=0 or current_price is null').fetchone()[0]
    units=cur.execute('select unit,count(*) from items group by unit').fetchall()
    preps=cur.execute("select count(*) from items where item_type='PREPARACION'").fetchone()[0]
    con.close()
    return {'db':str(p),'exists':True,'backup':str(backup) if backup else '', 'items':len(rows),'changed':len(changed),'zero_before':zero_before,'zero_after':zero_after,'units':[(u,c) for u,c in units],'preps':preps,'changed_rows':changed[:200]}

if __name__=='__main__':
    for arg in sys.argv[1:]:
        res=normalize_db(arg)
        print(res)
