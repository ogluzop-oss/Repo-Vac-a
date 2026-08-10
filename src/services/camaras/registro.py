"""
Registro de cámaras (videovigilancia) — CRUD con AISLAMIENTO ESTRICTO por empresa + departamento.

Ninguna consulta devuelve cámaras de otro departamento (`id_centro`) ni de otra empresa (`id_empresa`).
Los nombres de cámara son personalizables/editables. API-First (sin PyQt).
"""

import logging
import re

from src.db.conexion import _fila_a_dict, _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("camaras.registro")

TIPOS_CENTRO = ("tienda", "almacen", "centro")

# esquema://credenciales@resto  (RTSP/ONVIF). La contraseña con caracteres especiales debe ir URL-encoded.
_RE_CRED = re.compile(r"^(\w+://)([^/@]+)@(.+)$")


def _tiene_credenciales(url) -> bool:
    m = _RE_CRED.match(url or "")
    return bool(m) and ":" in m.group(2)          # usuario:contraseña


def _enmascarar(url) -> str:
    """Quita las credenciales de la URL (para almacenar/mostrar sin la contraseña)."""
    m = _RE_CRED.match(url or "")
    return f"{m.group(1)}{m.group(3)}" if m else url


def _proteger_fuente(fuente):
    """Devuelve (fuente_visible, fuente_cifrada). Si la URL lleva credenciales, CIFRA la URL completa
    (Secret Manager) y deja una versión enmascarada (sin contraseña) como valor visible. Regla del proyecto:
    jamás secretos en claro. Si no hay credenciales o no se puede cifrar, se conserva tal cual."""
    if not fuente or fuente == "simulado" or not _tiene_credenciales(fuente):
        return fuente, None
    try:
        from src.services.seguridad import secret_manager
        cif = secret_manager.cifrar(fuente)
    except Exception as e:
        logger.error("cifrar credencial cámara: %s", e)
        cif = None
    return (_enmascarar(fuente), cif) if cif else (fuente, None)


def fuente_efectiva(camara) -> str | None:
    """URL REAL de conexión de la cámara: descifra las credenciales si están protegidas. Uso interno del
    grabador; NUNCA se muestra ni se registra en logs."""
    cif = (camara or {}).get("fuente_cifrada")
    if cif:
        try:
            from src.services.seguridad import secret_manager
            real = secret_manager.descifrar(cif)
            if real:
                return real
        except Exception as e:
            logger.debug("descifrar fuente cámara: %s", e)
    return (camara or {}).get("fuente")


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


def crear_camara(nombre, *, id_empresa=None, id_centro=None, tipo_centro="centro",
                 fuente="simulado", usuario=None) -> int | None:
    id_empresa = _emp(id_empresa)
    if not id_empresa or id_centro is None:
        return None
    if tipo_centro not in TIPOS_CENTRO:
        tipo_centro = "centro"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(MAX(orden),0)+1 FROM camaras WHERE id_empresa=%s AND "
                        "id_centro=%s", (id_empresa, str(id_centro)))
            r = cur.fetchone()
            orden = int((r[0] if not isinstance(r, dict) else list(r.values())[0]) or 1)
            visible, cifrada = _proteger_fuente(fuente)   # jamás credenciales en claro
            cur.execute("INSERT INTO camaras (id_empresa, id_centro, tipo_centro, nombre, fuente, "
                        "fuente_cifrada, orden, usuario) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                        (id_empresa, str(id_centro), tipo_centro, nombre, visible, cifrada, orden,
                         _usuario(usuario)))
            cid = cur.lastrowid
            conn.commit()
            return cid
    except Exception as e:
        logger.error("crear_camara(%s): %s", nombre, e)
        return None


def renombrar_camara(id_camara, nombre, *, id_empresa=None) -> bool:
    """Renombra una cámara (nombre personalizable). Exige que pertenezca a la empresa (aislamiento)."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE camaras SET nombre=%s, actualizado=NOW() WHERE id=%s AND id_empresa=%s",
                        (nombre, id_camara, id_empresa))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("renombrar_camara(%s): %s", id_camara, e)
        return False


def actualizar_fuente(id_camara, fuente, *, id_empresa=None) -> bool:
    """Cambia la fuente de una cámara PROTEGIENDO las credenciales (cifra la URL con usuario:contraseña).
    Exige pertenencia a la empresa (aislamiento)."""
    id_empresa = _emp(id_empresa)
    visible, cifrada = _proteger_fuente(fuente)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE camaras SET fuente=%s, fuente_cifrada=%s, actualizado=NOW() WHERE id=%s "
                        "AND id_empresa=%s", (visible, cifrada, id_camara, id_empresa))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("actualizar_fuente(%s): %s", id_camara, e)
        return False


def eliminar_camara(id_camara, *, id_empresa=None) -> bool:
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM camaras WHERE id=%s AND id_empresa=%s", (id_camara, id_empresa))
            conn.commit()
            return cur.rowcount > 0
    except Exception as e:
        logger.error("eliminar_camara(%s): %s", id_camara, e)
        return False


def listar_camaras(id_empresa=None, id_centro=None, *, solo_activas=True) -> list:
    """Cámaras de UN departamento de UNA empresa (aislamiento estricto)."""
    id_empresa = _emp(id_empresa)
    if not id_empresa or id_centro is None:
        return []
    q = "SELECT * FROM camaras WHERE id_empresa=%s AND id_centro=%s"
    p = [id_empresa, str(id_centro)]
    if solo_activas:
        q += " AND estado='activa'"
    q += " ORDER BY orden, id"
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(q, p)
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.debug("listar_camaras: %s", e)
        return []


def obtener_camara(id_camara, *, id_empresa=None, permitir_super=False) -> dict | None:
    """Devuelve la cámara SOLO si pertenece a la empresa (aislamiento). `permitir_super` (SUPERADMIN)
    omite el filtro de empresa para acceso multi-sede autorizado."""
    id_empresa = _emp(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            if permitir_super:
                cur.execute("SELECT * FROM camaras WHERE id=%s", (id_camara,))
            else:
                cur.execute("SELECT * FROM camaras WHERE id=%s AND id_empresa=%s",
                            (id_camara, id_empresa))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.debug("obtener_camara(%s): %s", id_camara, e)
        return None


def departamentos(id_empresa=None) -> list:
    """Departamentos de la empresa con cámaras posibles: tiendas + almacenes + centros de trabajo."""
    id_empresa = _emp(id_empresa)
    out = []
    fuentes = [("tiendas", "id", "nombre", "tienda"),
               ("almacen", "id", "nombre", "almacen"),
               ("centros_trabajo", "id_centro", "nombre_centro", "centro")]
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            for tabla, col_id, col_nom, tipo in fuentes:
                try:
                    cur.execute(f"SELECT {col_id} AS id, {col_nom} AS nombre FROM {tabla} WHERE "
                                "id_empresa=%s", (id_empresa,))
                    for r in _filas_a_dicts(cur, cur.fetchall()):
                        out.append({"id_centro": str(r.get("id")), "nombre": r.get("nombre"),
                                    "tipo_centro": tipo})
                except Exception:
                    continue
    except Exception as e:
        logger.debug("departamentos: %s", e)
    return out
