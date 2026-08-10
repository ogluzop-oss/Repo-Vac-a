"""
Corporate Contacts CRM (CCP Fase II · B7) — evolución del Directorio a CRM corporativo.

Añade RELACIONES entre entidades (jerarquías empresa→delegación→sucursal→centro→almacén→departamento→
equipo→persona, responsables, sustitutos, pertenencia) sobre `ccp_relaciones`, SIN duplicar entidades:
los datos siguen resolviéndose por el Corporate Identity Resolver / Recipient Resolution. Multiempresa.
API-First (sin PyQt).
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("ccp.contactos_crm")

ROLES = ("pertenece_a", "responsable", "sustituto", "delegacion", "sucursal", "departamento",
         "equipo", "contacto")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return None


def _usuario(usuario=None):
    if usuario:
        return usuario
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        return str(u.get("nombre") or u.get("usuario") or "") or None
    except Exception:
        return None


def vincular(origen_tipo, origen_id, destino_tipo, destino_id, *, rol="pertenece_a",
             id_empresa=None, observaciones=None, usuario=None) -> int | None:
    """Crea una relación entre dos entidades. Idempotente por (empresa, origen, destino, rol)."""
    id_empresa = _emp(id_empresa)
    if rol not in ROLES:
        rol = "pertenece_a"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO ccp_relaciones (id_empresa, origen_tipo, origen_id, destino_tipo, "
                "destino_id, rol, observaciones, usuario) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE observaciones=VALUES(observaciones)",
                (id_empresa, origen_tipo, str(origen_id), destino_tipo, str(destino_id), rol,
                 observaciones, _usuario(usuario)))
            rid = cur.lastrowid
            conn.commit()
            return rid
    except Exception as e:
        logger.error("vincular: %s", e)
        return None


def desvincular(origen_tipo, origen_id, destino_tipo, destino_id, *, rol=None, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    q = ("DELETE FROM ccp_relaciones WHERE id_empresa=%s AND origen_tipo=%s AND origen_id=%s AND "
         "destino_tipo=%s AND destino_id=%s")
    p = [id_empresa, origen_tipo, str(origen_id), destino_tipo, str(destino_id)]
    if rol:
        q += " AND rol=%s"; p.append(rol)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p); conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("desvincular: %s", e)
        return False


def relaciones(origen_tipo, origen_id, *, rol=None, id_empresa=None) -> list:
    """Relaciones salientes de una entidad (sus hijos/responsables/…)."""
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM ccp_relaciones WHERE id_empresa=%s AND origen_tipo=%s AND origen_id=%s"
    p = [id_empresa, origen_tipo, str(origen_id)]
    if rol:
        q += " AND rol=%s"; p.append(rol)
    return _q(q, p)


def relaciones_inversas(destino_tipo, destino_id, *, rol=None, id_empresa=None) -> list:
    """Relaciones entrantes (a qué pertenece / quién la referencia)."""
    id_empresa = _emp(id_empresa)
    q = "SELECT * FROM ccp_relaciones WHERE id_empresa=%s AND destino_tipo=%s AND destino_id=%s"
    p = [id_empresa, destino_tipo, str(destino_id)]
    if rol:
        q += " AND rol=%s"; p.append(rol)
    return _q(q, p)


def responsables(entidad_tipo, entidad_id, *, id_empresa=None) -> list:
    """Responsables y sustitutos asignados a una entidad."""
    id_empresa = _emp(id_empresa)
    return _q("SELECT * FROM ccp_relaciones WHERE id_empresa=%s AND origen_tipo=%s AND origen_id=%s "
              "AND rol IN ('responsable','sustituto')", [id_empresa, entidad_tipo, str(entidad_id)])


def arbol(origen_tipo, origen_id, *, id_empresa=None, profundidad=6) -> dict:
    """Construye el árbol jerárquico (rol 'pertenece_a' y organizativos) desde una entidad raíz."""
    id_empresa = _emp(id_empresa)

    def _nodo(tipo, ide, prof):
        hijos = []
        if prof > 0:
            for r in relaciones_inversas(tipo, ide, id_empresa=id_empresa):
                if r["rol"] in ("pertenece_a", "delegacion", "sucursal", "departamento", "equipo"):
                    hijos.append(_nodo(r["origen_tipo"], r["origen_id"], prof - 1))
        return {"tipo": tipo, "id": str(ide), "hijos": hijos}

    return _nodo(origen_tipo, str(origen_id), profundidad)


def _q(q, p) -> list:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("_q: %s", e)
        return []
