"""
Resolucion de destinatarios de un evento (Fase 2, SUBFASE 2.2).

Dado un evento y su politica (scope), decide automaticamente QUE terminales deben recibirlo:
empresa completa, tienda concreta, central, almacenes... Reglas extensibles. Los destinos
concretos se resuelven del registro de terminales (`terminales`/edge_nodes); si no hay
terminales registradas, el destino por defecto es la central.
"""

import logging

from src.services.distribucion import terminales as _T

logger = logging.getLogger("distribucion.destinatarios")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def _norm(t) -> dict:
    idt = int(t.get("id_tienda") or 0)
    nombre = t.get("nombre") or ("central" if idt == 0 else f"tienda-{idt}")
    return {"destino": nombre, "tipo_destino": ("central" if idt == 0 else "tienda"),
            "id_tienda": idt}


def resolver(evento: dict, politica: dict, id_empresa=None) -> list:
    """Lista de destinos [{destino, tipo_destino, id_tienda}] para el evento segun el scope."""
    emp = _emp(id_empresa)
    scope = (politica or {}).get("scope", "EMPRESA")
    origen_tienda = int(evento.get("id_tienda") or 0)
    terms = _T.listar(emp)

    if scope == "CENTRAL":
        elegidos = [_T.central(emp)]
    elif scope == "TIENDA":
        elegidos = [t for t in terms if int(t.get("id_tienda") or 0) == origen_tienda]
        if not elegidos:
            elegidos = [{"nombre": f"tienda-{origen_tienda}", "id_tienda": origen_tienda}]
    elif scope == "ALMACEN":
        elegidos = [t for t in terms if (t.get("nombre") or "").lower().startswith(("alm", "cd", "wh"))]
        if not elegidos:
            elegidos = [_T.central(emp)]
    else:  # EMPRESA | GRUPO → todas las terminales
        elegidos = list(terms)

    if not elegidos:
        elegidos = [_T.central(emp)]

    # Normaliza + deduplica por (destino, id_tienda).
    vistos, out = set(), []
    for t in elegidos:
        d = _norm(t)
        clave = (d["destino"], d["id_tienda"])
        if clave not in vistos:
            vistos.add(clave)
            out.append(d)
    return out
