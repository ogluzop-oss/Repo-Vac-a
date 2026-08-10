"""
Histórico de aprendizaje y favoritos del Servicio de Resolución de Destinatarios (Partes D/I/J/Q).

Persiste, POR EMPRESA y POR USUARIO:
  · cada destinatario ya usado (aunque no pertenezca al ERP) con nº de envíos y último envío →
    alimenta "recientes" y el orden por frecuencia (aprendizaje sin IA);
  · los favoritos marcados por el usuario.

Multiempresa estricto: toda fila y toda consulta van atadas a `id_empresa` (+ `id_usuario`). Núcleo
sin PyQt ni dependencia del módulo Correo.
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("destinatarios.historico")


def _ctx(id_empresa=None, id_usuario=None):
    """Resuelve (id_empresa, id_usuario) del contexto si no se pasan explícitos."""
    if not id_empresa:
        try:
            from src.db.empresa import empresa_actual_id
            id_empresa = empresa_actual_id()
        except Exception:
            id_empresa = None
    if id_usuario is None:
        try:
            from src.db.usuario import sesion_global
            u = sesion_global.usuario_actual or {}
            id_usuario = str(u.get("nombre") or u.get("usuario") or u.get("id") or "") or None
        except Exception:
            id_usuario = None
    return id_empresa, id_usuario


# ── Histórico (aprendizaje) ───────────────────────────────────────────────────
def registrar_envio(correo, nombre_mostrado=None, *, id_empresa=None, id_usuario=None,
                    modulo_contexto=None) -> bool:
    """Registra (upsert) un envío a `correo`: +1 envío y actualiza último envío. Idempotente por
    (empresa, usuario, correo). Best-effort: nunca rompe el flujo de envío."""
    correo = (correo or "").strip().lower()
    if not correo or "@" not in correo:
        return False
    id_empresa, id_usuario = _ctx(id_empresa, id_usuario)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO destinatarios_historico
                   (id_empresa, id_usuario, correo, nombre_mostrado, modulo_contexto, num_envios,
                    ultimo_envio)
                   VALUES (%s,%s,%s,%s,%s,1,NOW())
                   ON DUPLICATE KEY UPDATE
                     num_envios = num_envios + 1,
                     ultimo_envio = NOW(),
                     nombre_mostrado = COALESCE(VALUES(nombre_mostrado), nombre_mostrado),
                     modulo_contexto = COALESCE(VALUES(modulo_contexto), modulo_contexto)""",
                (id_empresa, id_usuario, correo, nombre_mostrado, modulo_contexto),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.debug("registrar_envio(%s): %s", correo, e)
        return False


def listar_historico(id_empresa=None, id_usuario=None, *, limite=500) -> list[dict]:
    """Histórico de la empresa (todos los usuarios) ordenado por uso reciente y frecuencia."""
    id_empresa, _ = _ctx(id_empresa, id_usuario)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM destinatarios_historico WHERE id_empresa=%s "
                "ORDER BY ultimo_envio DESC, num_envios DESC LIMIT %s",
                (id_empresa, int(limite)),
            )
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_historico: %s", e)
        return []


# ── Favoritos ─────────────────────────────────────────────────────────────────
def marcar_favorito(correo, nombre_mostrado=None, tipo=None, *, id_empresa=None,
                    id_usuario=None) -> bool:
    correo = (correo or "").strip().lower()
    if not correo:
        return False
    id_empresa, id_usuario = _ctx(id_empresa, id_usuario)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                """INSERT INTO destinatarios_favoritos
                   (id_empresa, id_usuario, correo, nombre_mostrado, tipo)
                   VALUES (%s,%s,%s,%s,%s)
                   ON DUPLICATE KEY UPDATE
                     nombre_mostrado=VALUES(nombre_mostrado), tipo=VALUES(tipo)""",
                (id_empresa, id_usuario, correo, nombre_mostrado, tipo),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.debug("marcar_favorito(%s): %s", correo, e)
        return False


def quitar_favorito(correo, *, id_empresa=None, id_usuario=None) -> bool:
    correo = (correo or "").strip().lower()
    id_empresa, id_usuario = _ctx(id_empresa, id_usuario)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "DELETE FROM destinatarios_favoritos WHERE id_empresa=%s AND id_usuario=%s "
                "AND correo=%s", (id_empresa, id_usuario, correo),
            )
            conn.commit()
        return True
    except Exception as e:
        logger.debug("quitar_favorito(%s): %s", correo, e)
        return False


def listar_favoritos(id_empresa=None, id_usuario=None) -> list[dict]:
    id_empresa, id_usuario = _ctx(id_empresa, id_usuario)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM destinatarios_favoritos WHERE id_empresa=%s AND id_usuario=%s "
                "ORDER BY nombre_mostrado, correo", (id_empresa, id_usuario),
            )
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_favoritos: %s", e)
        return []


def set_favoritos(correos: set, id_empresa=None, id_usuario=None) -> set:
    """Devuelve el subconjunto de `correos` (normalizados) que son favoritos del usuario. Una sola
    consulta para anotar en bloque las sugerencias."""
    favs = {f["correo"] for f in listar_favoritos(id_empresa, id_usuario)}
    return {c for c in (correos or set()) if c in favs}
