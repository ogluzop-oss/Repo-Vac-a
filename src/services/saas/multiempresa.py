"""
Usuarios multiempresa (FASE SAAS-G).

Membresías N:M usuario↔empresa con rol por empresa y tipo de relación (empleado/consultor/
franquiciado/asesoria/admin_externo). NO modifica usuarios.id_empresa (capa legacy intacta);
añade pertenencias adicionales. Multiempresa y auditado.
"""

import logging
from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("saas.multiempresa")
TIPOS = ("empleado", "consultor", "franquiciado", "grupo", "admin_externo", "asesoria")


def _fila(cur, r):
    return r if isinstance(r, dict) else dict(zip([d[0] for d in cur.description], r))


def vincular(id_usuario, id_empresa, *, rol="OPERARIO", tipo_relacion="empleado") -> int | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO usuarios_empresas (id_usuario, id_empresa, rol, tipo_relacion) "
                        "VALUES (%s,%s,%s,%s) ON DUPLICATE KEY UPDATE rol=VALUES(rol), "
                        "tipo_relacion=VALUES(tipo_relacion), estado='activo'",
                        (id_usuario, id_empresa, rol, tipo_relacion))
            conn.commit()
            cur.execute("SELECT id FROM usuarios_empresas WHERE id_usuario=%s AND id_empresa=%s",
                        (id_usuario, id_empresa))
            r = cur.fetchone()
        _audit("USUARIO_VINCULADO", id_empresa, f"usuario={id_usuario} rol={rol}")
        return r[0] if r and not isinstance(r, dict) else (list(r.values())[0] if r else None)
    except Exception as e:
        logger.error("vincular: %s", e)
        return None


def desvincular(id_usuario, id_empresa) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE usuarios_empresas SET estado='baja' WHERE id_usuario=%s AND id_empresa=%s",
                        (id_usuario, id_empresa))
            conn.commit()
        return True
    except Exception as e:
        logger.error("desvincular: %s", e)
        return False


def empresas_de_usuario(id_usuario) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa, rol, tipo_relacion FROM usuarios_empresas "
                        "WHERE id_usuario=%s AND estado='activo'", (id_usuario,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("empresas_de_usuario: %s", e)
        return []


def usuarios_de_empresa(id_empresa) -> list:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_usuario, rol, tipo_relacion FROM usuarios_empresas "
                        "WHERE id_empresa=%s AND estado='activo'", (id_empresa,))
            return [_fila(cur, r) for r in cur.fetchall()]
    except Exception as e:
        logger.error("usuarios_de_empresa: %s", e)
        return []


def rol_en_empresa(id_usuario, id_empresa):
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT rol FROM usuarios_empresas WHERE id_usuario=%s AND id_empresa=%s "
                        "AND estado='activo'", (id_usuario, id_empresa))
            r = cur.fetchone()
            return (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
    except Exception:
        return None


def _audit(accion, id_empresa, detalle):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("saas", accion, "usuarios_empresas", f"{id_empresa}: {detalle}")
    except Exception:
        pass


# ── Login multiempresa (FASE P1.1) ───────────────────────────────────────────
def empresas_disponibles(id_usuario, *, id_empresa_legacy=None) -> list:
    """Empresas a las que el usuario puede acceder: sus membresías (usuarios_empresas) +
    su empresa legacy (usuarios.id_empresa) como fallback. Para el selector de login."""
    out = {x["id_empresa"]: x for x in empresas_de_usuario(id_usuario)}
    if id_empresa_legacy and id_empresa_legacy not in out:
        out[id_empresa_legacy] = {"id_empresa": id_empresa_legacy, "rol": None, "tipo_relacion": "legacy"}
    return list(out.values())


def cambiar_empresa_activa(id_usuario, id_empresa) -> bool:
    """Cambia el tenant activo a `id_empresa` si el usuario pertenece a ella (o es su legacy).
    Fija el TenantContext. Devuelve False si no tiene acceso."""
    disponibles = {e["id_empresa"] for e in empresas_de_usuario(id_usuario)}
    # Permite también la empresa legacy del propio usuario.
    try:
        from src.db.conexion import obtener_conexion as _oc
        with _oc() as conn, conn.cursor() as cur:
            cur.execute("SELECT id_empresa FROM usuarios WHERE id=%s", (id_usuario,))
            r = cur.fetchone()
            if r:
                disponibles.add(r[0] if not isinstance(r, dict) else list(r.values())[0])
    except Exception:
        pass
    if id_empresa not in disponibles:
        return False
    try:
        from src.db.empresa import set_empresa_actual
        set_empresa_actual(id_empresa)
        _audit("TENANT_CAMBIADO", id_empresa, f"usuario={id_usuario}")
        return True
    except Exception as e:
        logger.error("cambiar_empresa_activa: %s", e)
        return False
