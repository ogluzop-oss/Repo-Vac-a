"""
Firma / aceptación documental RRHH (F4.11).

Amplía el sistema documental existente (`rrhh_documentos`) con aceptación/rechazo y
trazabilidad (`rrhh_doc_auditoria`), sin reescribirlo ni regenerar PDFs. Inmutabilidad:
una vez aceptado/rechazado, el estado no cambia y se conserva el hash original del PDF
y la referencia documental. Seguridad: un empleado solo actúa sobre SUS documentos.
Multiempresa por id_empresa. Sin Qt.
"""

import datetime as _dt
import hashlib
import logging
import os

from src.db.conexion import (_fila_a_dict, _filas_a_dicts, ensure_schema,
                             obtener_conexion, transaccion)
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("rrhh.firma")

PENDIENTE, ACEPTADO, RECHAZADO, EXPIRADO, ANULADO = (
    "pendiente", "aceptado", "rechazado", "expirado", "anulado")

# Tipos que pueden requerir firma (ampliable).
TIPOS_FIRMABLES = {"contrato", "anexo", "vacaciones", "comunicacion", "certificado",
                   "carta_disciplinaria", "carta_despido", "cert_laboral", "otros"}


class FirmaError(Exception):
    """Operación de firma no permitida (propiedad, estado o documento inexistente)."""


def _hash_fichero(ruta) -> str | None:
    try:
        if ruta and os.path.exists(ruta):
            h = hashlib.sha256()
            with open(ruta, "rb") as f:
                for chunk in iter(lambda: f.read(65536), b""):
                    h.update(chunk)
            return h.hexdigest()
    except Exception as e:
        logger.warning("_hash_fichero(%s): %s", ruta, e)
    return None


def _doc(cur, id_documento, id_empresa) -> dict | None:
    cur.execute("SELECT * FROM rrhh_documentos WHERE id=%s AND id_empresa=%s",
                (id_documento, id_empresa))
    return _fila_a_dict(cur, cur.fetchone())


def _auditar(cur, id_empresa, doc, accion, usuario=None, id_empleado=None, ip=None,
             detalle=None):
    cur.execute(
        "INSERT INTO rrhh_doc_auditoria (id_empresa, id_documento, id_empleado, accion, "
        "usuario, ip, hash_documental, version_doc, detalle) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
        (id_empresa, doc["id"], id_empleado or doc.get("id_empleado"), accion, usuario, ip,
         doc.get("hash_documental"), doc.get("version_doc") or 1, detalle))


# ── Marcar requiere firma ─────────────────────────────────────────────────────
def marcar_requiere_firma(id_documento, expira=None, usuario=None, id_empresa=None) -> bool:
    """Marca un documento como pendiente de firma; ancla el hash del PDF (inmutabilidad)."""
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with transaccion() as conn, conn.cursor() as cur:
            doc = _doc(cur, id_documento, id_empresa)
            if not doc:
                raise FirmaError("Documento no encontrado.")
            h = _hash_fichero(doc.get("ref_documento"))
            cur.execute("UPDATE rrhh_documentos SET requiere_firma=1, estado_firma=%s, "
                        "hash_documental=COALESCE(hash_documental,%s), expira=%s "
                        "WHERE id=%s AND id_empresa=%s",
                        (PENDIENTE, h, expira, id_documento, id_empresa))
            doc["hash_documental"] = doc.get("hash_documental") or h
            _auditar(cur, id_empresa, doc, "requiere_firma", usuario=usuario)
        return True
    except FirmaError:
        raise
    except Exception as e:
        logger.error("marcar_requiere_firma(%s): %s", id_documento, e)
        return False


# ── Aceptar / rechazar (con propiedad e inmutabilidad) ───────────────────────
def _resolver(cur, id_documento, id_empresa, id_empleado):
    doc = _doc(cur, id_documento, id_empresa)
    if not doc:
        raise FirmaError("Documento no encontrado.")
    if id_empleado is not None and doc.get("id_empleado") != id_empleado:
        raise FirmaError("No puede actuar sobre documentos de otro empleado.")
    if not doc.get("requiere_firma"):
        raise FirmaError("El documento no requiere firma.")
    if doc.get("estado_firma") != PENDIENTE:
        raise FirmaError(f"El documento ya está en estado '{doc.get('estado_firma')}'.")
    return doc


def aceptar(id_documento, usuario=None, id_empleado=None, ip=None, id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with transaccion() as conn, conn.cursor() as cur:
            doc = _resolver(cur, id_documento, id_empresa, id_empleado)
            cur.execute("UPDATE rrhh_documentos SET estado_firma=%s, fecha_aceptacion=NOW(), "
                        "firmado_por=%s WHERE id=%s AND id_empresa=%s",
                        (ACEPTADO, usuario, id_documento, id_empresa))
            _auditar(cur, id_empresa, doc, "aceptado", usuario=usuario,
                     id_empleado=doc["id_empleado"], ip=ip)
        return True
    except FirmaError:
        raise
    except Exception as e:
        logger.error("aceptar(%s): %s", id_documento, e)
        return False


def rechazar(id_documento, usuario=None, id_empleado=None, ip=None, motivo=None,
             id_empresa=None) -> bool:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with transaccion() as conn, conn.cursor() as cur:
            doc = _resolver(cur, id_documento, id_empresa, id_empleado)
            cur.execute("UPDATE rrhh_documentos SET estado_firma=%s, fecha_rechazo=NOW(), "
                        "firmado_por=%s WHERE id=%s AND id_empresa=%s",
                        (RECHAZADO, usuario, id_documento, id_empresa))
            _auditar(cur, id_empresa, doc, "rechazado", usuario=usuario,
                     id_empleado=doc["id_empleado"], ip=ip, detalle=motivo)
        return True
    except FirmaError:
        raise
    except Exception as e:
        logger.error("rechazar(%s): %s", id_documento, e)
        return False


def expirar_pendientes(id_empresa=None) -> int:
    """Marca como EXPIRADO los pendientes cuya fecha de expiración ya pasó."""
    id_empresa = id_empresa or empresa_actual_id()
    hoy = _dt.date.today().isoformat()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_documentos WHERE id_empresa=%s AND requiere_firma=1 "
                        "AND estado_firma=%s AND expira IS NOT NULL AND expira < %s",
                        (id_empresa, PENDIENTE, hoy))
            docs = _filas_a_dicts(cur, cur.fetchall())
            for d in docs:
                cur.execute("UPDATE rrhh_documentos SET estado_firma=%s WHERE id=%s",
                            (EXPIRADO, d["id"]))
                _auditar(cur, id_empresa, d, "expirado")
            conn.commit()
            return len(docs)
    except Exception as e:
        logger.error("expirar_pendientes: %s", e)
        return 0


# ── Consultas ────────────────────────────────────────────────────────────────
def listar_pendientes(id_empleado, id_empresa=None) -> list:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_documentos WHERE id_empresa=%s AND id_empleado=%s "
                        "AND requiere_firma=1 AND estado_firma=%s ORDER BY fecha DESC, id DESC",
                        (id_empresa, id_empleado, PENDIENTE))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_pendientes(%s): %s", id_empleado, e)
        return []


def historial(id_documento, id_empresa=None) -> list:
    id_empresa = id_empresa or empresa_actual_id()
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM rrhh_doc_auditoria WHERE id_documento=%s AND id_empresa=%s "
                        "ORDER BY fecha_hora, id", (id_documento, id_empresa))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("historial(%s): %s", id_documento, e)
        return []
