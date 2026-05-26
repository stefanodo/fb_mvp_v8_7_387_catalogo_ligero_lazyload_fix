from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any, Dict

from app.core import db, ensure_columns


def _now() -> str:
    return datetime.utcnow().isoformat(timespec='seconds')


def _j(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _ensure_col(cur, table: str, col: str, ddl: str) -> None:
    try:
        cols = [r['name'] for r in cur.execute(f"PRAGMA table_info({table})").fetchall()]
        if col not in cols:
            cur.execute(f"ALTER TABLE {table} ADD COLUMN {ddl}")
    except Exception:
        pass


def ensure_accounting_lab_schema(cur) -> None:
    ensure_columns(cur)
    cur.execute('''CREATE TABLE IF NOT EXISTS supplier_documents(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id INTEGER,
        center_id INTEGER,
        document_type TEXT,
        document_number TEXT,
        document_date TEXT,
        amount_base REAL DEFAULT 0,
        amount_tax REAL DEFAULT 0,
        amount_total REAL DEFAULT 0,
        ocr_status TEXT,
        reconciliation_status TEXT,
        accounting_status TEXT,
        payment_status TEXT,
        file_path TEXT,
        raw_payload_json TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS supplier_document_reconciliations(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        receipt_document_id INTEGER,
        invoice_document_id INTEGER,
        supplier_id INTEGER,
        center_id INTEGER,
        match_status TEXT,
        difference_amount REAL DEFAULT 0,
        difference_json TEXT,
        reviewed_by TEXT,
        reviewed_at TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS supplier_payment_proposals(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        supplier_id INTEGER,
        center_id INTEGER,
        reconciliation_id INTEGER,
        due_date TEXT,
        amount_total REAL DEFAULT 0,
        payment_method TEXT,
        iban TEXT,
        status TEXT,
        human_approval_required INTEGER DEFAULT 1,
        approved_by TEXT,
        approved_at TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')
    cur.execute('''CREATE TABLE IF NOT EXISTS accounting_packages(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        center_id INTEGER,
        period_start TEXT,
        period_end TEXT,
        supplier_id INTEGER,
        package_status TEXT,
        summary_json TEXT,
        pdf_path TEXT,
        created_by TEXT,
        created_at TEXT,
        updated_at TEXT
    )''')

    # Compatibilidad con bases que ya tenían una tabla supplier_documents parcial.
    for col, ddl in [
        ('supplier_id','supplier_id INTEGER'), ('center_id','center_id INTEGER'), ('document_type','document_type TEXT'),
        ('document_number','document_number TEXT'), ('document_date','document_date TEXT'), ('amount_base','amount_base REAL DEFAULT 0'),
        ('amount_tax','amount_tax REAL DEFAULT 0'), ('amount_total','amount_total REAL DEFAULT 0'), ('ocr_status','ocr_status TEXT'),
        ('reconciliation_status','reconciliation_status TEXT'), ('accounting_status','accounting_status TEXT'), ('payment_status','payment_status TEXT'),
        ('file_path','file_path TEXT'), ('raw_payload_json','raw_payload_json TEXT'), ('created_at','created_at TEXT'), ('updated_at','updated_at TEXT')]:
        _ensure_col(cur, 'supplier_documents', col, ddl)
    for col, ddl in [
        ('receipt_document_id','receipt_document_id INTEGER'), ('invoice_document_id','invoice_document_id INTEGER'), ('supplier_id','supplier_id INTEGER'),
        ('center_id','center_id INTEGER'), ('match_status','match_status TEXT'), ('difference_amount','difference_amount REAL DEFAULT 0'),
        ('difference_json','difference_json TEXT'), ('reviewed_by','reviewed_by TEXT'), ('reviewed_at','reviewed_at TEXT'),
        ('created_at','created_at TEXT'), ('updated_at','updated_at TEXT')]:
        _ensure_col(cur, 'supplier_document_reconciliations', col, ddl)
    for col, ddl in [
        ('supplier_id','supplier_id INTEGER'), ('center_id','center_id INTEGER'), ('reconciliation_id','reconciliation_id INTEGER'),
        ('due_date','due_date TEXT'), ('amount_total','amount_total REAL DEFAULT 0'), ('payment_method','payment_method TEXT'),
        ('iban','iban TEXT'), ('status','status TEXT'), ('human_approval_required','human_approval_required INTEGER DEFAULT 1'),
        ('approved_by','approved_by TEXT'), ('approved_at','approved_at TEXT'), ('created_at','created_at TEXT'), ('updated_at','updated_at TEXT')]:
        _ensure_col(cur, 'supplier_payment_proposals', col, ddl)


def simulate_reconciliation() -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_accounting_lab_schema(cur)
    now = _now()
    supplier = cur.execute('SELECT id,name,COALESCE(payment_frequency,\'\') payment_frequency, COALESCE(payment_method,\'\') payment_method, COALESCE(iban,\'\') iban FROM suppliers ORDER BY id LIMIT 1').fetchone()
    supplier_id = int(supplier['id']) if supplier else 0
    center = cur.execute('SELECT id,name FROM centers ORDER BY id LIMIT 1').fetchone()
    center_id = int(center['id']) if center else 0
    total = 776.08; base = 705.53; tax = 70.55
    cur.execute('''INSERT INTO supplier_documents(supplier_id,center_id,document_type,document_number,document_date,amount_base,amount_tax,amount_total,ocr_status,reconciliation_status,accounting_status,payment_status,file_path,raw_payload_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (supplier_id, center_id, 'albaran', 'LAB-ALB-001', str(datetime.utcnow().date()), base, tax, total, 'ocr_lab', 'pendiente', 'pendiente', 'no_preparado', '', _j({'source':'LAB'}), now, now))
    receipt_doc = int(cur.lastrowid or 0)
    cur.execute('''INSERT INTO supplier_documents(supplier_id,center_id,document_type,document_number,document_date,amount_base,amount_tax,amount_total,ocr_status,reconciliation_status,accounting_status,payment_status,file_path,raw_payload_json,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', (supplier_id, center_id, 'factura', 'LAB-FAC-001', str(datetime.utcnow().date()), base, tax, total, 'ocr_lab', 'pendiente', 'pendiente', 'no_preparado', '', _j({'source':'LAB'}), now, now))
    invoice_doc = int(cur.lastrowid or 0)
    status = 'coincide'
    cur.execute('''INSERT INTO supplier_document_reconciliations(receipt_document_id,invoice_document_id,supplier_id,center_id,match_status,difference_amount,difference_json,reviewed_by,reviewed_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?)''', (receipt_doc, invoice_doc, supplier_id, center_id, status, 0, '{}', '', '', now, now))
    rec_id = int(cur.lastrowid or 0)
    due = (datetime.utcnow() + timedelta(days=15)).date().isoformat()
    cur.execute('''INSERT INTO supplier_payment_proposals(supplier_id,center_id,reconciliation_id,due_date,amount_total,payment_method,iban,status,human_approval_required,approved_by,approved_at,created_at,updated_at)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)''', (supplier_id, center_id, rec_id, due, total, supplier['payment_method'] if supplier else 'pendiente', supplier['iban'] if supplier else '', 'propuesta_no_ejecutable', 1, '', '', now, now))
    pay_id = int(cur.lastrowid or 0)
    conn.commit(); conn.close()
    return {'ok': True, 'mode': 'LAB_NO_PAGO_REAL', 'receipt_document_id': receipt_doc, 'invoice_document_id': invoice_doc, 'reconciliation_id': rec_id, 'payment_proposal_id': pay_id, 'match_status': status, 'amount_total': total, 'due_date': due, 'message': 'Conciliación LAB creada. Pago real desactivado; requiere validación humana final.'}


def accounting_summary(limit: int = 8) -> Dict[str, Any]:
    conn = db(); cur = conn.cursor(); ensure_accounting_lab_schema(cur)
    docs = cur.execute('''SELECT d.id,d.document_type,d.document_number,d.document_date,d.amount_total,d.reconciliation_status,d.accounting_status,d.payment_status,s.name supplier_name
                          FROM supplier_documents d LEFT JOIN suppliers s ON s.id=d.supplier_id ORDER BY d.id DESC LIMIT ?''', (int(limit),)).fetchall()
    recs = cur.execute('''SELECT id,match_status,difference_amount,created_at FROM supplier_document_reconciliations ORDER BY id DESC LIMIT ?''', (int(limit),)).fetchall()
    pays = cur.execute('''SELECT p.id,p.due_date,p.amount_total,p.status,p.human_approval_required,s.name supplier_name FROM supplier_payment_proposals p LEFT JOIN suppliers s ON s.id=p.supplier_id ORDER BY p.id DESC LIMIT ?''', (int(limit),)).fetchall()
    conn.close()
    return {'ok': True, 'documents': [{k: d[k] for k in d.keys()} for d in docs], 'reconciliations': [{k: r[k] for k in r.keys()} for r in recs], 'payment_proposals': [{k: p[k] for k in p.keys()} for p in pays], 'message': 'Bloque documental/contable LAB preparado. No ejecuta pagos.'}
