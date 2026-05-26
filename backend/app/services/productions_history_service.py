def build_print_group_rows(cur, center_id: int, production_group: str):
    return cur.execute(
        """SELECT p.id, p.status, p.created_at, p.note,
                  COALESCE(p.production_group,'Otros') production_group,
                  c.name center_name, w.name warehouse_name
             FROM productions p
             JOIN centers c ON c.id=p.center_id
             JOIN warehouses w ON w.id=p.warehouse_id
            WHERE p.center_id=? AND COALESCE(p.production_group,'Otros')=?
            ORDER BY p.status='DRAFT' DESC, p.id DESC""",
        (int(center_id), (production_group or 'Otros').strip() or 'Otros'),
    ).fetchall()
