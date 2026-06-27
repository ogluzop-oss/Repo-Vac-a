"""
Capa de datos del CORREO CORPORATIVO (multi-tenant, multi-buzón, licenciable).

Principio: identidad = empresa → tienda → correo. El correo es un SERVICIO
asociado, nunca la clave principal. Todo cuelga de `id_empresa` (y opcionalmente
`id_tienda`/`id_usuario`). Preparado para licenciamiento SaaS (licencias_correo) y
OAuth 2.0 (tokens SIEMPRE cifrados; NUNCA se guardan contraseñas).

Tablas: correos_corporativos, licencias_correo, oauth_tokens (ver conexion.py).
"""

import logging
import uuid
from datetime import datetime

from src.db.conexion import (
    _fila_a_dict,
    _filas_a_dicts,
    ensure_schema,
    obtener_conexion,
)
from src.db.empresa import empresa_actual_id
from src.utils import cripto

logger = logging.getLogger("correo_db")

# Catálogos (la estructura admite ampliarlos sin tocar la lógica).
TIPOS_CORREO = ("general", "pedidos", "incidencias", "administracion", "rrhh", "logistica")
PROVEEDORES = ("google", "microsoft", "smtp", "simulado")
TIPOS_LICENCIA = (
    "correo_tienda", "correo_almacen", "correo_departamento",
    "correo_empleado", "correo_temporal", "correo_compartido",
)


# ============================================================
# LICENCIAS DE CORREO
# ============================================================
def crear_licencia(tipo_licencia="correo_tienda", id_tienda=None, id_usuario=None,
                   numero_buzon=None, limite_almacenamiento=5120,
                   observaciones=None, id_empresa=None) -> str | None:
    """Crea una licencia de correo y devuelve su id (UUID)."""
    nid = str(uuid.uuid4())
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO licencias_correo
                   (id_licencia, id_empresa, id_tienda, id_usuario, tipo_licencia,
                    numero_buzon, limite_almacenamiento, observaciones)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                (nid, id_empresa, id_tienda, id_usuario, tipo_licencia,
                 numero_buzon, limite_almacenamiento, observaciones),
            )
            conn.commit()
        return nid
    except Exception as e:
        logger.error("Error crear_licencia: %s", e)
        return None


def listar_licencias(id_empresa=None) -> list[dict]:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM licencias_correo WHERE id_empresa=%s ORDER BY fecha_alta DESC",
                (id_empresa,),
            )
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("Error listar_licencias: %s", e)
        return []


def actualizar_licencia(id_licencia: str, **campos) -> bool:
    permitidos = ("tipo_licencia", "estado", "numero_buzon",
                  "limite_almacenamiento", "fecha_baja", "observaciones",
                  "id_tienda", "id_usuario")
    sets = {k: v for k, v in campos.items() if k in permitidos}
    if not sets:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            asign = ", ".join(f"{k}=%s" for k in sets)
            cur.execute(
                f"UPDATE licencias_correo SET {asign} WHERE id_licencia=%s",
                [*sets.values(), id_licencia],
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error actualizar_licencia(%s): %s", id_licencia, e)
        return False


# ============================================================
# CORREOS CORPORATIVOS
# ============================================================
def crear_correo(direccion: str, proveedor="simulado", tipo="general",
                 id_tienda=None, id_usuario=None, id_licencia=None,
                 observaciones=None, id_empresa=None) -> str | None:
    """Crea un buzón corporativo asociado a empresa (y opcionalmente tienda)."""
    nid = str(uuid.uuid4())
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO correos_corporativos
                   (id_correo, id_empresa, id_tienda, id_usuario, direccion,
                    proveedor, tipo, id_licencia, observaciones)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (nid, id_empresa, id_tienda, id_usuario, direccion.strip().lower(),
                 proveedor, tipo, id_licencia, observaciones),
            )
            conn.commit()
        logger.info("Correo corporativo creado: %s (%s)", direccion, proveedor)
        return nid
    except Exception as e:
        logger.error("Error crear_correo(%s): %s", direccion, e)
        return None


def listar_correos(id_empresa=None, id_tienda=None) -> list[dict]:
    """Lista buzones de la empresa (opcionalmente filtrando por tienda) con datos
    de su licencia y nombre de tienda."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            q = """
                SELECT c.*, t.nombre AS tienda_nombre, t.codigo_tienda,
                       l.tipo_licencia, l.estado AS licencia_estado,
                       l.fecha_alta AS licencia_alta, l.numero_buzon
                FROM correos_corporativos c
                LEFT JOIN tiendas t ON t.id = c.id_tienda
                LEFT JOIN licencias_correo l ON l.id_licencia = c.id_licencia
                WHERE c.id_empresa = %s
            """
            params = [id_empresa]
            if id_tienda is not None:
                q += " AND c.id_tienda = %s"
                params.append(id_tienda)
            q += " ORDER BY c.fecha_alta DESC"
            cur.execute(q, params)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("Error listar_correos: %s", e)
        return []


def obtener_correo(id_correo: str) -> dict | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM correos_corporativos WHERE id_correo=%s", (id_correo,))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("Error obtener_correo(%s): %s", id_correo, e)
        return None


def actualizar_correo(id_correo: str, **campos) -> bool:
    permitidos = ("direccion", "proveedor", "tipo", "estado", "id_tienda",
                  "id_usuario", "id_licencia", "observaciones")
    sets = {k: v for k, v in campos.items() if k in permitidos}
    if not sets:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            asign = ", ".join(f"{k}=%s" for k in sets)
            cur.execute(
                f"UPDATE correos_corporativos SET {asign} WHERE id_correo=%s",
                [*sets.values(), id_correo],
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error actualizar_correo(%s): %s", id_correo, e)
        return False


def marcar_sincronizacion(id_correo: str) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "UPDATE correos_corporativos SET ultima_sincronizacion=%s WHERE id_correo=%s",
                (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), id_correo),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error marcar_sincronizacion(%s): %s", id_correo, e)
        return False


def eliminar_correo(id_correo: str) -> bool:
    """Elimina un buzón y revoca/borra sus tokens (revocación inmediata)."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM oauth_tokens WHERE id_correo=%s", (id_correo,))
            cur.execute("DELETE FROM correos_corporativos WHERE id_correo=%s", (id_correo,))
            conn.commit()
        logger.info("Correo %s eliminado (tokens revocados).", id_correo)
        return True
    except Exception as e:
        logger.error("Error eliminar_correo(%s): %s", id_correo, e)
        return False


# ============================================================
# TOKENS OAUTH (cifrados en reposo) — NUNCA contraseñas
# ============================================================
def guardar_tokens(id_correo: str, proveedor: str, access_token=None,
                   refresh_token=None, scope=None, expira_en=None) -> bool:
    """Cifra y guarda (upsert) los tokens OAuth de un buzón."""
    at = cripto.cifrar(access_token)
    rt = cripto.cifrar(refresh_token)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO oauth_tokens
                   (id_token, id_correo, proveedor, access_token_cifrado,
                    refresh_token_cifrado, scope, expira_en)
                   VALUES (%s,%s,%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                     proveedor=VALUES(proveedor),
                     access_token_cifrado=VALUES(access_token_cifrado),
                     refresh_token_cifrado=VALUES(refresh_token_cifrado),
                     scope=VALUES(scope), expira_en=VALUES(expira_en)""",
                (str(uuid.uuid4()), id_correo, proveedor, at, rt, scope, expira_en),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error guardar_tokens(%s): %s", id_correo, e)
        return False


def obtener_tokens(id_correo: str) -> dict | None:
    """Devuelve los tokens DESCIFRADOS de un buzón, o None."""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM oauth_tokens WHERE id_correo=%s", (id_correo,))
            row = _fila_a_dict(cur, cur.fetchone())
        if not row:
            return None
        return {
            "proveedor": row.get("proveedor"),
            "access_token": cripto.descifrar(row.get("access_token_cifrado")),
            "refresh_token": cripto.descifrar(row.get("refresh_token_cifrado")),
            "scope": row.get("scope"),
            "expira_en": row.get("expira_en"),
        }
    except Exception as e:
        logger.error("Error obtener_tokens(%s): %s", id_correo, e)
        return None


def revocar_tokens(id_correo: str) -> bool:
    """Borra los tokens de un buzón (revocación inmediata)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM oauth_tokens WHERE id_correo=%s", (id_correo,))
            conn.commit()
        return True
    except Exception as e:
        logger.error("Error revocar_tokens(%s): %s", id_correo, e)
        return False


# ── Correo recibido (FASE COM-4) — recepción/sincronización IMAP/Graph ───────
def _emp_corr(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def guardar_recibido(id_correo, remitente, asunto, cuerpo=None, *, message_id=None,
                     fecha=None, adjuntos=None, id_empresa=None):
    """Persiste (idempotente por message_id) un correo recibido y sus adjuntos. Audita."""
    id_empresa = _emp_corr(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT IGNORE INTO correos_recibidos (id_empresa, id_correo, remitente, "
                        "asunto, cuerpo, message_id, fecha) VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, id_correo, remitente, asunto, cuerpo, message_id, fecha))
            rid = cur.lastrowid
            if not rid:        # ya existía (idempotente)
                cur.execute("SELECT id FROM correos_recibidos WHERE id_empresa=%s AND id_correo=%s "
                            "AND message_id=%s", (id_empresa, id_correo, message_id))
                r = cur.fetchone()
                rid = (r[0] if not isinstance(r, dict) else list(r.values())[0]) if r else None
            for adj in (adjuntos or []):
                cur.execute("INSERT INTO correos_adjuntos (id_empresa, id_correo_recibido, nombre, ruta) "
                            "VALUES (%s,%s,%s,%s)", (id_empresa, rid, adj.get("nombre"), adj.get("ruta")))
            conn.commit()
        try:
            from src.db.conexion import log_auditoria
            log_auditoria("sistema", "CORREO_RECIBIDO", "correos_recibidos", f"id={rid} de {remitente}")
        except Exception:
            pass
        return rid
    except Exception as e:
        logger.error("guardar_recibido: %s", e)
        return None


def listar_recibidos(id_correo=None, *, solo_no_leidos=False, id_empresa=None):
    id_empresa = _emp_corr(id_empresa)
    q = "SELECT * FROM correos_recibidos WHERE id_empresa=%s"
    p = [id_empresa]
    if id_correo:
        q += " AND id_correo=%s"; p.append(id_correo)
    if solo_no_leidos:
        q += " AND leido=0"
    q += " ORDER BY fecha DESC, id DESC LIMIT 500"
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_recibidos: %s", e)
        return []


def marcar_recibido_leido(id_recibido, id_empresa=None):
    id_empresa = _emp_corr(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE correos_recibidos SET leido=1 WHERE id=%s AND id_empresa=%s",
                        (id_recibido, id_empresa))
            conn.commit()
        try:
            from src.db.conexion import log_auditoria
            log_auditoria("sistema", "CORREO_ABIERTO", "correos_recibidos", f"id={id_recibido}")
        except Exception:
            pass
        return True
    except Exception as e:
        logger.error("marcar_recibido_leido: %s", e)
        return False
