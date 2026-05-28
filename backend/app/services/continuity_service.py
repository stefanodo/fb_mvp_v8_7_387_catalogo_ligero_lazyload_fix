from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime
from typing import Any, Dict

from app.core import db, ensure_columns, safe_insert_returning


def _now() -> str:
    return datetime.utcnow().isoformat(timespec='seconds')


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def ensure_continuity_schema(cur) -> None:
    # Schema for continuity/offline queues is managed by backend/migrate.py.
    # Avoid runtime DDL in the service module; run migrations as an administrative step.
    return


def enqueue_offline_event(module: str, event_type: str, payload: Dict[str, Any], restaurant_id: int = 0, responsible_name: str = 'LAB', device_id: str = 'lab-device', priority: int = 50) -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_continuity_schema(cur)
    now = _now(); event_uuid = str(uuid.uuid4())
    packed = {'module': module, 'event_type': event_type, 'payload': payload, 'restaurant_id': restaurant_id, 'responsible_name': responsible_name, 'device_id': device_id}
    h = hashlib.sha256(_j(packed).encode('utf-8')).hexdigest()
    existing = cur.execute('SELECT id,event_uuid FROM offline_event_queue WHERE deduplication_hash=?', (h,)).fetchone()
    if existing:
        conn.close()
        return {'ok': True, 'duplicate': True, 'event_id': int(existing['id']), 'event_uuid': existing['event_uuid'], 'message': 'Evento offline duplicado detectado.'}
    # Insert offline event (DB-agnostic)
    sqlite_sql = '''INSERT INTO offline_event_queue(event_uuid,local_device_id,restaurant_id,user_id,responsible_name,module,event_type,payload_json,local_created_at,server_received_at,sync_status,retry_count,last_error,deduplication_hash,priority,created_at,updated_at)
           VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)'''
    pg_sql = sqlite_sql.replace('?', '%s')
    event_id = safe_insert_returning(
        cur,
        sqlite_sql,
        (
            event_uuid, device_id, int(restaurant_id or 0), 0, responsible_name, module, event_type, _j(payload), now, '', 'pendiente', 0, '', h, int(priority or 50), now, now,
        ),
        pg_sql=pg_sql,
    ) or 0
    # Try a single UPSERT across DBs; fall back to SELECT+INSERT when not supported.
    # Run a DB-agnostic UPSERT for `sync_devices`. Use Postgres placeholders when available.
    sqlite_sql = 'INSERT INTO sync_devices(local_device_id,device_name,restaurant_id,device_type,last_seen_at,last_sync_at,active,notes) VALUES(?,?,?,?,?,?,?,?) ON CONFLICT (local_device_id) DO NOTHING'
    pg_sql = sqlite_sql.replace('?', '%s')
    try:
        if getattr(cur, '_is_postgres', False):
            cur.execute(pg_sql, (device_id, 'Dispositivo LAB', int(restaurant_id or 0), 'otro', now, '', 1, 'Simulador continuidad'))
        else:
            try:
                cur.execute(sqlite_sql, (device_id, 'Dispositivo LAB', int(restaurant_id or 0), 'otro', now, '', 1, 'Simulador continuidad'))
            except Exception:
                # Fallback: emulate UPSERT with SELECT+INSERT
                exists = cur.execute('SELECT 1 FROM sync_devices WHERE local_device_id=?', (device_id,)).fetchone()
                if not exists:
                    cur.execute('INSERT INTO sync_devices(local_device_id,device_name,restaurant_id,device_type,last_seen_at,last_sync_at,active,notes) VALUES(?,?,?,?,?,?,?,?)',
                                (device_id, 'Dispositivo LAB', int(restaurant_id or 0), 'otro', now, '', 1, 'Simulador continuidad'))
    except Exception:
        # best-effort: ignore errors creating a sync device record
        pass
    conn.commit(); conn.close()
    return {'ok': True, 'duplicate': False, 'event_id': event_id, 'event_uuid': event_uuid, 'sync_status': 'pendiente', 'message': 'Evento offline guardado en cola. No aplica stock real.'}


def simulate_offline_case(case: str = 'merma') -> Dict[str, Any]:
    case = (case or 'merma').strip().lower()
    examples = {
        'merma': ('mermas', 'MERMA_OFFLINE', {'item': 'TOMATE', 'qty': 4, 'unit': 'kg', 'reason': 'podrido'} , 30),
        'produccion': ('producciones', 'PRODUCCION_OFFLINE', {'recipe': 'PICO DE GALLO', 'qty': 3, 'unit': 'kg'}, 25),
        'inventario': ('inventario', 'INVENTARIO_CONTEO_OFFLINE', {'family': 'verduras', 'item': 'PUERRO', 'real_qty': 10, 'unit': 'kg'}, 40),
        'pedido': ('pedidos', 'PEDIDO_BORRADOR_OFFLINE', {'text': 'pedir tomate para mañana'}, 60),
        'tpv': ('tpv', 'VENTA_TPV_OFFLINE', {'ticket': 'OFF-LAB-1', 'line': 'SALMON CON PURE', 'modifier': 'sin salsa'}, 20),
        'oido': ('oido_alfi', 'NOTA_OFFLINE', {'text': 'recordar revisar mise en place'}, 80),
    }
    module, event_type, payload, priority = examples.get(case, examples['merma'])
    return enqueue_offline_event(module, event_type, payload, responsible_name='Mauro LAB', device_id='lab-device', priority=priority)


def _is_safe_preview_event(module: str, event_type: str) -> bool:
    module = (module or '').lower()
    event_type = (event_type or '').upper()
    if module in {'oido_alfi', 'pedidos'}:
        return True
    if module == 'tpv' and 'VENTA' in event_type:
        return True
    return False


def sync_offline_events(limit: int = 50) -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_continuity_schema(cur)
    start = _now()
    rows = cur.execute('''SELECT * FROM offline_event_queue WHERE sync_status IN ('pendiente','error')
                          ORDER BY priority ASC, local_created_at ASC LIMIT ?''', (int(limit),)).fetchall()
    attempted = synced = failed = conflicts = 0
    details = []
    for r in rows:
        attempted += 1
        event_id = int(r['id'])
        module = r['module']; event_type = r['event_type']
        try:
            payload = json.loads(r['payload_json'] or '{}')
        except Exception:
            payload = {}
        if _is_safe_preview_event(module, event_type):
            cur.execute("UPDATE offline_event_queue SET sync_status='sincronizado', server_received_at=?, updated_at=?, last_error='' WHERE id=?", (_now(), _now(), event_id))
            synced += 1
            details.append({'event_id': event_id, 'status': 'sincronizado_preview', 'module': module})
        else:
            conflict_type = 'requiere_revision_manual'
            if module == 'inventario': conflict_type = 'inventario_requiere_revision'
            if module == 'mermas': conflict_type = 'stock_afectado_requiere_validacion'
            if module == 'producciones': conflict_type = 'produccion_requiere_validacion'
            cur.execute("UPDATE offline_event_queue SET sync_status='conflicto', server_received_at=?, updated_at=?, last_error=? WHERE id=?", (_now(), _now(), conflict_type, event_id))
            cur.execute('''INSERT INTO sync_conflicts(offline_event_id,module,conflict_type,local_payload_json,server_payload_json,resolution_status,resolution_notes,resolved_by,resolved_at,created_at)
                           VALUES(?,?,?,?,?,?,?,?,?,?)''', (event_id, module, conflict_type, _j(payload), '{}', 'pendiente', 'Evento puede afectar stock/datos críticos. Revisión humana obligatoria.', '', '', _now()))
            conflicts += 1
            details.append({'event_id': event_id, 'status': 'conflicto', 'module': module, 'conflict_type': conflict_type})
    status = 'ok' if failed == 0 else 'parcial'
    finish = _now()
    cur.execute('''INSERT INTO sync_runs(started_at,finished_at,status,events_attempted,events_synced,events_failed,conflicts_created,details_json)
                   VALUES(?,?,?,?,?,?,?,?)''', (start, finish, status, attempted, synced, failed, conflicts, _j(details)))
    conn.commit(); conn.close()
    return {'ok': True, 'status': status, 'events_attempted': attempted, 'events_synced': synced, 'events_failed': failed, 'conflicts_created': conflicts, 'details': details, 'message': f'Sync LAB completada: {synced} preview, {conflicts} conflictos.'}


def continuity_summary(limit: int = 10) -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_continuity_schema(cur)
    pend = cur.execute("SELECT COUNT(*) c FROM offline_event_queue WHERE sync_status='pendiente'").fetchone()
    err = cur.execute("SELECT COUNT(*) c FROM offline_event_queue WHERE sync_status='error'").fetchone()
    conf = cur.execute("SELECT COUNT(*) c FROM sync_conflicts WHERE resolution_status='pendiente'").fetchone()
    last = cur.execute('SELECT * FROM sync_runs ORDER BY id DESC LIMIT 1').fetchone()
    events = cur.execute('SELECT id,local_created_at,module,event_type,responsible_name,sync_status,last_error FROM offline_event_queue ORDER BY id DESC LIMIT ?', (int(limit),)).fetchall()
    conflicts = cur.execute('SELECT id,offline_event_id,module,conflict_type,resolution_status,created_at FROM sync_conflicts ORDER BY id DESC LIMIT ?', (int(limit),)).fetchall()
    conn.close()
    return {'ok': True, 'status': 'ONLINE_LOCAL_BETA', 'last_sync': ({k: last[k] for k in last.keys()} if last else None), 'pending_events': int((pend or {'c':0})['c'] or 0), 'error_events': int((err or {'c':0})['c'] or 0), 'pending_conflicts': int((conf or {'c':0})['c'] or 0), 'events': [{k: e[k] for k in e.keys()} for e in events], 'conflicts': [{k: c[k] for k in c.keys()} for c in conflicts], 'message': 'Continuidad LAB: cola preparada; no aplica movimientos críticos sin revisión.'}
