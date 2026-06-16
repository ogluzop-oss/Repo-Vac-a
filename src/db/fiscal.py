"""
Capa de datos del NÚCLEO FISCAL (C3.1) — neutro respecto a la normativa.

Provee:
- Config fiscal POR EMPRESA (`fiscal_config`).
- ENCADENADO HASH de registros (`fiscal_registros`): cada registro incluye la huella
  del anterior (por empresa+serie) → cadena inalterable.
- Cola de envío/reenvío (`fiscal_cola`).

No implementa lógica legal (Verifactu/Facturae/TicketBAI): solo la base reutilizable.
Las tablas las crea la migración C4 `0002_fiscal`.
"""

import hashlib
import json
import logging

from src.db.conexion import (EMPRESA_DEFAULT_ID, _filas_a_dicts, ensure_schema,
                             obtener_conexion, transaccion)

logger = logging.getLogger("fiscal_db")

TERRITORIOS = ("comun", "araba", "bizkaia", "gipuzkoa")
MODOS = ("verifactu", "no_verifactu")


def _empresa(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        return EMPRESA_DEFAULT_ID


# ── Config fiscal por empresa ────────────────────────────────────────────────
def obtener_config(id_empresa=None) -> dict:
    id_empresa = _empresa(id_empresa)
    base = {"id_empresa": id_empresa, "territorio": "comun", "modo": "verifactu",
            "proveedor": "simulado", "integrador": "", "serie": "A", "activo": 0}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_config WHERE id_empresa=%s", (id_empresa,))
            r = cur.fetchone()
            if r:
                if not isinstance(r, dict):
                    r = dict(zip([d[0] for d in cur.description], r))
                base.update({k: (r.get(k) if r.get(k) is not None else base[k]) for k in base})
    except Exception as e:
        logger.error("obtener_config: %s", e)
    return base


def guardar_config(territorio=None, modo=None, proveedor=None, integrador=None,
                   serie=None, activo=None, id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    a = obtener_config(id_empresa)
    n = {"territorio": territorio or a["territorio"], "modo": modo or a["modo"],
         "proveedor": proveedor or a["proveedor"],
         "integrador": integrador if integrador is not None else a["integrador"],
         "serie": serie or a["serie"],
         "activo": int(activo if activo is not None else a["activo"])}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO fiscal_config (id_empresa, territorio, modo, proveedor, "
                "integrador, serie, activo) VALUES (%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE territorio=VALUES(territorio), modo=VALUES(modo), "
                "proveedor=VALUES(proveedor), integrador=VALUES(integrador), "
                "serie=VALUES(serie), activo=VALUES(activo)",
                (id_empresa, n["territorio"], n["modo"], n["proveedor"], n["integrador"],
                 n["serie"], n["activo"]))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_config: %s", e)
        return False


# ── Encadenado hash + registros ──────────────────────────────────────────────
def huella(campos: dict, hash_anterior: str | None) -> str:
    """Huella SHA-256 de un registro encadenada con la del anterior. El formato
    legal exacto (Verifactu/TicketBAI) se concretará en C3.3/C3.4; aquí se define
    el mecanismo neutro de encadenado."""
    base = json.dumps(campos, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(((hash_anterior or "") + "|" + base).encode("utf-8")).hexdigest()


def _ultimo(cur, id_empresa, serie):
    cur.execute("SELECT numero, hash FROM fiscal_registros "
                "WHERE id_empresa=%s AND serie=%s ORDER BY numero DESC LIMIT 1",
                (id_empresa, serie))
    r = cur.fetchone()
    if not r:
        return 0, None
    return (r[0], r[1]) if not isinstance(r, dict) else (r["numero"], r["hash"])


def insertar_registro(tipo, referencia=None, total=0.0, serie=None, payload=None,
                      qr=None, proveedor="simulado", estado="generado",
                      id_empresa=None, id_tienda="auto", campos_hash=None) -> dict:
    """Inserta un registro fiscal ENCADENADO (numeración y hash por empresa+serie).
    Atómico (transacción + bloqueo) para que la cadena sea consistente bajo
    concurrencia. Devuelve el registro creado (con numero/hash/hash_anterior)."""
    id_empresa = _empresa(id_empresa)
    if id_tienda == "auto":
        try:
            from src.db.empresa import tienda_actual_id
            id_tienda = tienda_actual_id()
        except Exception:
            id_tienda = None
    serie = serie or obtener_config(id_empresa)["serie"]
    payload_str = json.dumps(payload, ensure_ascii=False, default=str) if payload is not None else None
    try:
        with transaccion() as conn, conn.cursor() as cur:
            # FOR UPDATE sobre el último de la serie → numeración/cadena sin carreras.
            cur.execute("SELECT numero, hash FROM fiscal_registros "
                        "WHERE id_empresa=%s AND serie=%s ORDER BY numero DESC LIMIT 1 FOR UPDATE",
                        (id_empresa, serie))
            r = cur.fetchone()
            ult_num, ult_hash = ((r[0], r[1]) if r and not isinstance(r, dict)
                                 else (r["numero"], r["hash"]) if r else (0, None))
            numero = int(ult_num or 0) + 1
            datos = campos_hash or {"serie": serie, "numero": numero, "tipo": tipo,
                                    "referencia": referencia, "total": round(float(total or 0), 2)}
            h = huella(datos, ult_hash)
            cur.execute(
                "INSERT INTO fiscal_registros (id_empresa, id_tienda, serie, numero, tipo, "
                "referencia, total, hash, hash_anterior, qr, payload, proveedor, estado) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (id_empresa, id_tienda, serie, numero, tipo, referencia,
                 round(float(total or 0), 2), h, ult_hash, qr, payload_str, proveedor, estado))
            rid = cur.lastrowid
        return {"id": rid, "id_empresa": id_empresa, "serie": serie, "numero": numero,
                "tipo": tipo, "referencia": referencia, "total": round(float(total or 0), 2),
                "hash": h, "hash_anterior": ult_hash, "qr": qr, "proveedor": proveedor,
                "estado": estado}
    except Exception as e:
        logger.error("insertar_registro: %s", e)
        return {}


def listar_registros(id_empresa=None, serie=None, limite=500) -> list:
    id_empresa = _empresa(id_empresa)
    filtros, params = ["id_empresa=%s"], [id_empresa]
    if serie:
        filtros.append("serie=%s"); params.append(serie)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_registros WHERE " + " AND ".join(filtros)
                        + " ORDER BY serie, numero LIMIT %s", (*params, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_registros: %s", e)
        return []


def actualizar_estado(id_registro, estado) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE fiscal_registros SET estado=%s WHERE id=%s", (estado, id_registro))
            conn.commit()
        return True
    except Exception as e:
        logger.error("actualizar_estado(%s): %s", id_registro, e)
        return False


def cadena_valida(id_empresa=None, serie="A") -> bool:
    """Verifica la integridad del encadenado hash de una serie (re-calcula y compara)."""
    id_empresa = _empresa(id_empresa)
    prev = None
    for reg in listar_registros(id_empresa, serie=serie, limite=100000):
        datos = {"serie": reg["serie"], "numero": reg["numero"], "tipo": reg["tipo"],
                 "referencia": reg["referencia"], "total": round(float(reg["total"] or 0), 2)}
        if reg["hash_anterior"] != prev or huella(datos, prev) != reg["hash"]:
            return False
        prev = reg["hash"]
    return True


# ── Cola de envío / reenvío ──────────────────────────────────────────────────
def encolar(id_registro, accion="enviar", id_empresa=None) -> int | None:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO fiscal_cola (id_empresa, id_registro, accion) "
                        "VALUES (%s,%s,%s)", (id_empresa, id_registro, accion))
            conn.commit()
            return cur.lastrowid
    except Exception as e:
        logger.error("encolar(%s): %s", id_registro, e)
        return None


def listar_cola(estado="pendiente", id_empresa=None, limite=200) -> list:
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_cola WHERE id_empresa=%s AND estado=%s "
                        "ORDER BY fecha LIMIT %s", (id_empresa, estado, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_cola: %s", e)
        return []


def actualizar_cola(id_cola, estado, error=None) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE fiscal_cola SET estado=%s, intentos=intentos+1, "
                        "ultimo_error=%s WHERE id=%s", (estado, (error or "")[:500], id_cola))
            conn.commit()
        return True
    except Exception as e:
        logger.error("actualizar_cola(%s): %s", id_cola, e)
        return False
