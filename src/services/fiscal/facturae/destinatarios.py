"""
Destinatarios Facturae (C3.4.1) — datos fiscales estructurados + DIR3 del receptor.

La tabla `clientes` no tiene dirección estructurada ni códigos DIR3 (obligatorios en
Facturae B2G). Esta capa, aditiva y multiempresa, los custodia por empresa+NIF y los
combina con `clientes` al generar la factura. Sin estos datos, la emisión B2G se
rechaza con un error claro (no se emite incompleta).
"""

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("fiscal.facturae.destinatarios")

_CAMPOS = ("cliente_id", "razon_social", "tipo_persona", "residencia", "direccion",
           "cp", "municipio", "provincia", "cod_pais", "es_aapp",
           "dir3_oficina_contable", "dir3_organo_gestor", "dir3_unidad_tramitadora",
           "dir3_organo_proponente")


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        from src.db.conexion import EMPRESA_DEFAULT_ID
        return EMPRESA_DEFAULT_ID


def guardar(nif, id_empresa=None, **campos) -> bool:
    """Alta/actualización del destinatario por (empresa, NIF). Idempotente."""
    id_empresa = _empresa(id_empresa)
    if not nif:
        return False
    datos = {k: campos.get(k) for k in _CAMPOS}
    # Defaults de columnas NOT NULL (no se pueden pasar como None en el upsert).
    datos["tipo_persona"] = (datos.get("tipo_persona") or "J")
    datos["residencia"] = (datos.get("residencia") or "R")
    datos["cod_pais"] = (datos.get("cod_pais") or "ESP")
    datos["es_aapp"] = int(datos.get("es_aapp") or 0)
    cols = ["id_empresa", "nif"] + list(_CAMPOS)
    vals = [id_empresa, nif] + [datos[k] for k in _CAMPOS]
    upd = ", ".join(f"{c}=VALUES({c})" for c in _CAMPOS)
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO facturae_destinatarios ({', '.join(cols)}) "
                f"VALUES ({', '.join(['%s'] * len(cols))}) ON DUPLICATE KEY UPDATE {upd}",
                vals)
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar destinatario(%s): %s", nif, e)
        return False


def obtener(nif, id_empresa=None) -> dict | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM facturae_destinatarios WHERE id_empresa=%s AND nif=%s",
                        (id_empresa, nif))
            r = cur.fetchone()
            return _filas_a_dicts(cur, [r])[0] if r else None
    except Exception as e:
        logger.error("obtener destinatario(%s): %s", nif, e)
        return None


def listar(id_empresa=None) -> list:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM facturae_destinatarios WHERE id_empresa=%s ORDER BY id DESC",
                        (id_empresa,))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar destinatarios: %s", e)
        return []


def validar_para_b2g(dest: dict) -> list:
    """Devuelve la lista de campos obligatorios que faltan para emitir B2G (FACe).
    Vacía = listo. (DIR3 obligatorios solo si es_aapp)."""
    faltan = []
    for c in ("razon_social", "direccion", "cp", "municipio", "provincia"):
        if not (dest or {}).get(c):
            faltan.append(c)
    if (dest or {}).get("es_aapp"):
        for c in ("dir3_oficina_contable", "dir3_organo_gestor", "dir3_unidad_tramitadora"):
            if not dest.get(c):
                faltan.append(c)
    return faltan
