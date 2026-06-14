"""
Centro documental unificado — capa de datos (registro, NO almacén).

`documentos_registro` es el ÍNDICE único de todos los documentos que el sistema
genera (tickets, facturas, albaranes, contratos, informes, Excel...). No guarda
el binario: referencia la ruta del fichero ya generado en `documentos/`.

Multi-tenant: cada registro cuelga de `id_empresa` (y `id_tienda` cuando aplica),
resueltos por el TenantContext si no se indican. Pensado para evolución SaaS y
cadenas de tiendas (ver [[project_multitenant]]).

API:
    registrar_documento(ruta, tipo, ...)   → alta idempotente (clave: ruta)
    listar_documentos(**filtros)           → tabla del visor
    buscar_documentos(texto)               → buscador global
    obtener_documento(id) / eliminar_documento(id)
    reconciliar_carpeta()                  → importa ficheros existentes
    contar_por_tipo()                      → contadores de la barra lateral
"""

import hashlib
import logging
import os
import uuid

from src.db.conexion import (
    EMPRESA_DEFAULT_ID,
    _fila_a_dict,
    _filas_a_dicts,
    ensure_schema,
    obtener_conexion,
)

logger = logging.getLogger("documentos_db")

# Catálogo de tipos documentales (clave lógica → clave i18n del visor).
TIPOS = {
    "contrato":   "doc.tipo_contrato",
    "factura":    "doc.tipo_factura",
    "factura_rect": "doc.tipo_factura_rect",
    "ticket":     "doc.tipo_ticket",
    "albaran":    "doc.tipo_albaran",
    "pedido":     "doc.tipo_pedido",
    "traspaso":   "doc.tipo_traspaso",
    "recepcion":  "doc.tipo_recepcion",
    "merma":      "doc.tipo_merma",
    "informe":    "doc.tipo_informe",
    "exportacion": "doc.tipo_exportacion",
    "certificado": "doc.tipo_certificado",
    "rrhh":       "doc.tipo_rrhh",
    "auditoria":  "doc.tipo_auditoria",
    "otros":      "doc.tipo_otros",
}

# Nombre de subcarpeta de documentos/ → tipo (para reconciliar ficheros legacy).
_CARPETA_TIPO = {
    "tickets": "ticket", "facturacion": "factura", "facturación": "factura",
    "facturas": "factura", "albaranes": "albaran", "contratos": "contrato",
    "pedidos": "pedido", "traspasos": "traspaso", "recepciones": "recepcion",
    "mermas": "merma", "informes": "informe", "informes de reposicion": "informe",
    "informes de reposición": "informe", "reposicion": "informe",
    "certificados": "certificado", "rrhh": "rrhh", "nominas": "rrhh",
    "nóminas": "rrhh", "exportaciones": "exportacion", "excel": "exportacion",
    "etiquetas": "otros", "stocks": "informe", "qr ubicaciones": "otros",
    "historial": "otros",
}

# Extensiones consideradas "documentos" al reconciliar (se ignoran imágenes sueltas).
_EXT_DOC = {".pdf", ".xlsx", ".xls", ".csv", ".docx", ".doc", ".eml", ".txt"}


def _dir_documentos() -> str:
    try:
        from src.utils.recursos import ruta_datos
        return ruta_datos()
    except Exception:
        return os.path.normpath(
            os.path.join(os.path.dirname(__file__), "..", "..", "documentos"))


def _hash_fichero(ruta: str) -> str | None:
    try:
        h = hashlib.sha256()
        with open(ruta, "rb") as f:
            for bloque in iter(lambda: f.read(65536), b""):
                h.update(bloque)
        return h.hexdigest()
    except Exception:
        return None


def _ctx():
    """(id_empresa, id_tienda, id_usuario, nombre_usuario) del contexto actual."""
    id_empresa, id_tienda = EMPRESA_DEFAULT_ID, None
    id_usuario, nombre_usuario = None, None
    try:
        from src.db.empresa import empresa_actual_id, tienda_actual_id
        id_empresa = empresa_actual_id()
        id_tienda = tienda_actual_id()
    except Exception:
        pass
    try:
        from src.db.usuario import sesion_global
        u = sesion_global.usuario_actual or {}
        id_usuario = u.get("id")
        nombre_usuario = u.get("nombre") or u.get("usuario")
    except Exception:
        pass
    return id_empresa, id_tienda, id_usuario, nombre_usuario


def registrar_documento(ruta: str, tipo: str = "otros", nombre: str | None = None,
                        referencia: str | None = None, cliente: str | None = None,
                        trabajador: str | None = None, importe=None,
                        estado: str = "generado", hash_documental: str | None = None,
                        id_empresa: str | None = None, id_tienda=None,
                        id_usuario=None) -> str | None:
    """Da de alta (o actualiza) un documento en el registro. Idempotente por `ruta`:
    si ya existe esa ruta, refresca metadatos en vez de duplicar. Devuelve el id."""
    if not ruta:
        return None
    if tipo not in TIPOS:
        tipo = "otros"
    ctx_emp, ctx_tienda, ctx_user, ctx_nombre = _ctx()
    id_empresa = id_empresa or ctx_emp
    if id_tienda is None:
        id_tienda = ctx_tienda
    if id_usuario is None:
        id_usuario = ctx_user
    if trabajador is None:
        trabajador = ctx_nombre
    nombre = nombre or os.path.basename(ruta)
    if hash_documental is None and os.path.exists(ruta):
        hash_documental = _hash_fichero(ruta)
    nuevo_id = str(uuid.uuid4())
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO documentos_registro "
                "(id_documento, id_empresa, id_tienda, id_usuario, tipo_documento, "
                " nombre, referencia, ruta, hash_documental, cliente, trabajador, "
                " importe, estado) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE "
                " tipo_documento=VALUES(tipo_documento), nombre=VALUES(nombre), "
                " referencia=VALUES(referencia), hash_documental=VALUES(hash_documental), "
                " cliente=VALUES(cliente), trabajador=VALUES(trabajador), "
                " importe=VALUES(importe), estado=VALUES(estado)",
                (nuevo_id, id_empresa, id_tienda, id_usuario, tipo, nombre, referencia,
                 ruta, hash_documental, cliente, trabajador, importe, estado))
            conn.commit()
        return nuevo_id
    except Exception as e:
        logger.error("Error registrar_documento(%s): %s", ruta, e)
        return None


def listar_documentos(tipo=None, id_empresa=None, id_tienda=None, fecha_desde=None,
                      fecha_hasta=None, usuario=None, cliente=None, trabajador=None,
                      referencia=None, texto=None, limite=2000) -> list[dict]:
    """Lista documentos del registro aplicando filtros. Orden: más recientes primero."""
    filtros, params = [], []
    if tipo:
        filtros.append("tipo_documento=%s"); params.append(tipo)
    if id_empresa:
        filtros.append("id_empresa=%s"); params.append(id_empresa)
    if id_tienda not in (None, ""):
        filtros.append("id_tienda=%s"); params.append(id_tienda)
    if fecha_desde:
        filtros.append("DATE(fecha_generacion)>=%s"); params.append(fecha_desde)
    if fecha_hasta:
        filtros.append("DATE(fecha_generacion)<=%s"); params.append(fecha_hasta)
    if usuario:
        filtros.append("(trabajador LIKE %s OR id_usuario=%s)")
        params += [f"%{usuario}%", usuario]
    if cliente:
        filtros.append("cliente LIKE %s"); params.append(f"%{cliente}%")
    if trabajador:
        filtros.append("trabajador LIKE %s"); params.append(f"%{trabajador}%")
    if referencia:
        filtros.append("referencia LIKE %s"); params.append(f"%{referencia}%")
    if texto:
        filtros.append("(nombre LIKE %s OR referencia LIKE %s OR hash_documental LIKE %s "
                       "OR cliente LIKE %s OR trabajador LIKE %s OR CAST(importe AS CHAR) LIKE %s)")
        params += [f"%{texto}%"] * 6
    where = (" WHERE " + " AND ".join(filtros)) if filtros else ""
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM documentos_registro" + where +
                " ORDER BY fecha_generacion DESC, nombre ASC LIMIT %s",
                (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("Error listar_documentos: %s", e)
        return []


def buscar_documentos(texto: str, id_empresa=None) -> list[dict]:
    """Buscador global: referencia, hash, cliente, trabajador, nombre o importe."""
    return listar_documentos(texto=texto, id_empresa=id_empresa)


def obtener_documento(id_documento: str) -> dict | None:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM documentos_registro WHERE id_documento=%s",
                        (id_documento,))
            return _fila_a_dict(cur, cur.fetchone())
    except Exception as e:
        logger.error("Error obtener_documento(%s): %s", id_documento, e)
        return None


def eliminar_documento(id_documento: str, borrar_fichero: bool = False) -> bool:
    """Elimina el REGISTRO (y opcionalmente el fichero físico)."""
    try:
        doc = obtener_documento(id_documento)
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("DELETE FROM documentos_registro WHERE id_documento=%s",
                        (id_documento,))
            conn.commit()
        if borrar_fichero and doc and doc.get("ruta") and os.path.exists(doc["ruta"]):
            try:
                os.remove(doc["ruta"])
            except Exception as e:
                logger.warning("No se pudo borrar el fichero %s: %s", doc["ruta"], e)
        return True
    except Exception as e:
        logger.error("Error eliminar_documento(%s): %s", id_documento, e)
        return False


def contar_por_tipo(id_empresa=None) -> dict:
    """{tipo: nº documentos} para los contadores de la barra lateral."""
    out = {t: 0 for t in TIPOS}
    where, params = "", []
    if id_empresa:
        where = " WHERE id_empresa=%s"; params.append(id_empresa)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "SELECT tipo_documento, COUNT(*) AS n FROM documentos_registro" + where +
                " GROUP BY tipo_documento", params)
            for r in cur.fetchall():
                t = r["tipo_documento"] if isinstance(r, dict) else r[0]
                n = r["n"] if isinstance(r, dict) else r[1]
                out[t if t in out else "otros"] = out.get(t, 0) + int(n)
    except Exception as e:
        logger.error("Error contar_por_tipo: %s", e)
    return out


def reconciliar_carpeta() -> int:
    """Importa al registro los ficheros existentes en documentos/<subcarpeta> que
    aún no estén registrados (clasificados por carpeta). Para que el centro muestre
    también los documentos generados ANTES de existir el registro. Idempotente."""
    base = _dir_documentos()
    if not os.path.isdir(base):
        return 0
    # Rutas ya registradas (para no reinsertar).
    registradas = set()
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT ruta FROM documentos_registro")
            registradas = {(r["ruta"] if isinstance(r, dict) else r[0]) for r in cur.fetchall()}
    except Exception as e:
        logger.error("Error leyendo rutas registradas: %s", e)
        return 0

    import datetime as _dt
    nuevos = 0
    for raiz, _dirs, ficheros in os.walk(base):
        carpeta = os.path.basename(raiz).strip().lower()
        if raiz == base:
            continue  # ignorar ficheros sueltos en la raíz de documentos/
        if carpeta.startswith(".") or carpeta == "__pycache__":
            continue
        tipo = _CARPETA_TIPO.get(carpeta, "otros")
        for fn in ficheros:
            ext = os.path.splitext(fn)[1].lower()
            if ext not in _EXT_DOC:
                continue
            ruta = os.path.join(raiz, fn)
            if ruta in registradas:
                continue
            try:
                ts = os.path.getmtime(ruta)
                fecha = _dt.datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
            except Exception:
                fecha = None
            try:
                with obtener_conexion() as conn, conn.cursor() as cur:
                    cur.execute(
                        "INSERT IGNORE INTO documentos_registro "
                        "(id_documento, id_empresa, tipo_documento, nombre, ruta, "
                        " estado, fecha_generacion) VALUES (%s,%s,%s,%s,%s,%s,"
                        " COALESCE(%s, CURRENT_TIMESTAMP))",
                        (str(uuid.uuid4()), EMPRESA_DEFAULT_ID, tipo, fn, ruta,
                         "generado", fecha))
                    conn.commit()
                nuevos += 1
            except Exception as e:
                logger.debug("No se pudo reconciliar %s: %s", ruta, e)
    if nuevos:
        logger.info("Centro documental: %d documentos reconciliados.", nuevos)
    return nuevos
