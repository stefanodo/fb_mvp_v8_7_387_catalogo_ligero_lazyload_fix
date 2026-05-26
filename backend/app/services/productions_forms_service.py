PRODUCTION_GROUPS = [
    "Calientes", "Fríos", "Postres", "Salsas", "Guarniciones",
    "Bases", "Masas", "Pastelería", "Porcionados", "Otros",
]


def selected_group_slug(group_value: str | None) -> str:
    return (group_value or "").strip()
