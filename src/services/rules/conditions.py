"""Condiciones del Rules Engine (Fase III · B5) — evaluación SIN código sobre un contexto (dict)."""


def _num(v):
    try:
        return float(str(v).replace(",", "."))
    except (TypeError, ValueError):
        return None


def _cmp(op, a, b) -> bool:
    na, nb = _num(a), _num(b)
    if na is not None and nb is not None:
        a, b = na, nb
    else:
        a, b = str(a), str(b)
    return {
        "==": a == b, "!=": a != b, ">": a > b, "<": a < b, ">=": a >= b, "<=": a <= b,
        "contiene": str(b).lower() in str(a).lower(),
        "empieza": str(a).lower().startswith(str(b).lower()),
        "in": str(a) in [str(x) for x in (b if isinstance(b, (list, tuple)) else [b])],
    }.get(op, False)


def evaluar(condiciones, contexto) -> bool:
    """`condiciones` = lista de {campo, op, valor} unidas por AND (o {or:[...]} para OR). True si todas
    se cumplen. Lista vacía = True."""
    if not condiciones:
        return True
    ctx = contexto or {}
    for c in condiciones:
        if "or" in c:
            if not any(evaluar([x], ctx) for x in c["or"]):
                return False
            continue
        if not _cmp(c.get("op", "=="), ctx.get(c.get("campo")), c.get("valor")):
            return False
    return True
