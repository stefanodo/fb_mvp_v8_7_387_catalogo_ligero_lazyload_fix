PRODUCTION_GROUPS = [
    "Calientes", "Fríos", "Postres", "Salsas", "Guarniciones",
    "Bases", "Masas", "Pastelería", "Porcionados", "Otros",
]

PRODUCTION_UNITS = ["raciones", "porciones", "ud", "kg", "g", "lotes"]


def production_groups() -> list[str]:
    return list(PRODUCTION_GROUPS)


def production_units() -> list[str]:
    return list(PRODUCTION_UNITS)
