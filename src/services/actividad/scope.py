"""
Alcance de la actividad por usuario y empresa (Fase 3, SUBFASE 3.5/3.6).

- 3.6 Multiempresa REAL: la empresa A nunca ve la actividad de la empresa B (todo se filtra
  siempre por id_empresa).
- 3.5 Por usuario: el administrador/gerente ve TODA la actividad de su empresa; un operario
  ve solo lo de SU tienda y lo que el mismo origino.

Devuelve una clausula SQL (fragmento + params) que se anexa a las consultas sobre `eventos`.
"""

_ROLES_GLOBALES = {"ADMINISTRADOR", "GERENTE", "SUPERADMIN"}


def _uid(usuario):
    if isinstance(usuario, dict):
        v = usuario.get("nombre") or usuario.get("usuario") or usuario.get("id")
        return str(v) if v is not None else None
    return str(usuario) if usuario is not None else None


def _tienda(usuario):
    if isinstance(usuario, dict):
        t = usuario.get("id_tienda", usuario.get("tienda"))
        try:
            return int(t) if t is not None else None
        except (TypeError, ValueError):
            return None
    return None


def es_global(perfil) -> bool:
    return str(perfil or "").upper() in _ROLES_GLOBALES


def filtro_sql(usuario=None, perfil=None, alias="e") -> tuple:
    """(fragmento_sql, params) para restringir eventos al alcance del usuario. El id_empresa
    se filtra aparte (siempre). Un rol global no añade restriccion adicional."""
    if isinstance(usuario, dict) and perfil is None:
        perfil = usuario.get("perfil")
    if es_global(perfil):
        return "", []
    # Operario: su tienda O lo que el origino.
    uid = _uid(usuario)
    tienda = _tienda(usuario)
    conds, params = [], []
    if tienda is not None:
        conds.append(f"{alias}.id_tienda=%s"); params.append(tienda)
    if uid:
        conds.append(f"{alias}.usuario=%s"); params.append(uid)
    if not conds:
        return "", []
    return "(" + " OR ".join(conds) + ")", params
