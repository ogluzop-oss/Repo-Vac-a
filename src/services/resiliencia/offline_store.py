"""
B7-A — Offline Store (SQLite embebido). Persistencia LOCAL de tienda para operar sin servidor.

NO depende de MariaDB: usa sqlite3 (stdlib). Espejo de catalogo (articulos/clientes/precios/stock)
+ operaciones offline (ventas/movimientos/documentos) + log de eventos local. Multiempresa/tienda
(un fichero por tienda). Checksum + versionado. Idempotente. Al reconectar, el sync_engine lo drena.
"""

import hashlib
import json
import logging
import os
import sqlite3
import threading
import time

logger = logging.getLogger("resiliencia.offline_store")
_LOCK = threading.RLock()

_DDL = """
CREATE TABLE IF NOT EXISTS offline_metadata (clave TEXT PRIMARY KEY, valor TEXT);
CREATE TABLE IF NOT EXISTS offline_articulos (codigo TEXT PRIMARY KEY, nombre TEXT, datos TEXT, version INTEGER DEFAULT 1, checksum TEXT);
CREATE TABLE IF NOT EXISTS offline_clientes (id TEXT PRIMARY KEY, nombre TEXT, datos TEXT, version INTEGER DEFAULT 1, checksum TEXT);
CREATE TABLE IF NOT EXISTS offline_precios (codigo TEXT PRIMARY KEY, precio REAL, datos TEXT, version INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS offline_stock (codigo TEXT PRIMARY KEY, cantidad REAL DEFAULT 0, version INTEGER DEFAULT 1);
CREATE TABLE IF NOT EXISTS offline_ventas (id INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT UNIQUE, payload TEXT, total REAL, hash TEXT, sincronizado INTEGER DEFAULT 0, creado_en TEXT);
CREATE TABLE IF NOT EXISTS offline_movimientos (id INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT UNIQUE, codigo TEXT, tipo TEXT, cantidad REAL, payload TEXT, hash TEXT, sincronizado INTEGER DEFAULT 0, creado_en TEXT);
CREATE TABLE IF NOT EXISTS offline_documentos (id INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT UNIQUE, tipo TEXT, ruta TEXT, payload TEXT, sincronizado INTEGER DEFAULT 0, creado_en TEXT);
CREATE TABLE IF NOT EXISTS offline_eventos (id INTEGER PRIMARY KEY AUTOINCREMENT, idempotency_key TEXT UNIQUE, tipo TEXT, agregado TEXT, agregado_id TEXT, payload TEXT, hash TEXT, hash_anterior TEXT, secuencia INTEGER, sincronizado INTEGER DEFAULT 0, creado_en TEXT);
"""


def _dir():
    base = os.path.join("documentos", "offline")
    try:
        from src.utils.recursos import ruta_datos
        base = ruta_datos("offline")
    except Exception:
        pass
    os.makedirs(base, exist_ok=True)
    return base


def ruta_db(id_empresa, id_tienda=0):
    return os.path.join(_dir(), f"offline_store_{id_empresa}_{id_tienda}.db")


def _conn(id_empresa, id_tienda=0):
    ruta = ruta_db(id_empresa, id_tienda)
    c = sqlite3.connect(ruta, timeout=10)
    c.row_factory = sqlite3.Row
    c.executescript(_DDL)
    return c


def _checksum(d) -> str:
    return hashlib.sha256(json.dumps(d, sort_keys=True, default=str).encode()).hexdigest()


def inicializar(id_empresa, id_tienda=0) -> dict:
    """Crea/abre el almacen offline de la tienda. Idempotente."""
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        c.execute("INSERT OR IGNORE INTO offline_metadata (clave, valor) VALUES ('id_empresa', ?)", (str(id_empresa),))
        c.execute("INSERT OR IGNORE INTO offline_metadata (clave, valor) VALUES ('id_tienda', ?)", (str(id_tienda),))
        c.execute("INSERT OR IGNORE INTO offline_metadata (clave, valor) VALUES ('schema_version', '1')")
        c.commit()
    return {"ok": True, "ruta": ruta_db(id_empresa, id_tienda)}


# ── Espejo de catalogo (sincronizacion incremental desde central) ─────────────
def upsert_articulo(id_empresa, codigo, nombre, datos, *, id_tienda=0, version=1):
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        c.execute("INSERT INTO offline_articulos (codigo, nombre, datos, version, checksum) VALUES (?,?,?,?,?) "
                  "ON CONFLICT(codigo) DO UPDATE SET nombre=excluded.nombre, datos=excluded.datos, "
                  "version=excluded.version, checksum=excluded.checksum",
                  (codigo, nombre, json.dumps(datos, default=str), version, _checksum(datos)))
        c.commit()


def upsert_cliente(id_empresa, id_cliente, nombre, datos, *, id_tienda=0, version=1):
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        c.execute("INSERT INTO offline_clientes (id, nombre, datos, version, checksum) VALUES (?,?,?,?,?) "
                  "ON CONFLICT(id) DO UPDATE SET nombre=excluded.nombre, datos=excluded.datos, "
                  "version=excluded.version, checksum=excluded.checksum",
                  (str(id_cliente), nombre, json.dumps(datos, default=str), version, _checksum(datos)))
        c.commit()


def set_precio(id_empresa, codigo, precio, *, id_tienda=0, datos=None):
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        c.execute("INSERT INTO offline_precios (codigo, precio, datos) VALUES (?,?,?) "
                  "ON CONFLICT(codigo) DO UPDATE SET precio=excluded.precio, datos=excluded.datos",
                  (codigo, float(precio), json.dumps(datos or {}, default=str)))
        c.commit()


def set_stock(id_empresa, codigo, cantidad, *, id_tienda=0):
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        c.execute("INSERT INTO offline_stock (codigo, cantidad) VALUES (?,?) "
                  "ON CONFLICT(codigo) DO UPDATE SET cantidad=excluded.cantidad, version=version+1",
                  (codigo, float(cantidad)))
        c.commit()


def consultar_stock(id_empresa, codigo, *, id_tienda=0) -> float:
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        r = c.execute("SELECT cantidad FROM offline_stock WHERE codigo=?", (codigo,)).fetchone()
        return float(r["cantidad"]) if r else 0.0


def articulo(id_empresa, codigo, *, id_tienda=0) -> dict | None:
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        r = c.execute("SELECT * FROM offline_articulos WHERE codigo=?", (codigo,)).fetchone()
        if not r:
            return None
        return {"codigo": r["codigo"], "nombre": r["nombre"], "datos": json.loads(r["datos"] or "{}"),
                "version": r["version"]}


def precio(id_empresa, codigo, *, id_tienda=0) -> float | None:
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        r = c.execute("SELECT precio FROM offline_precios WHERE codigo=?", (codigo,)).fetchone()
        return float(r["precio"]) if r else None


# ── Operaciones offline (generan evento + descuentan stock local) ─────────────
def _ult_hash(c) -> str | None:
    r = c.execute("SELECT hash FROM offline_eventos ORDER BY secuencia DESC LIMIT 1").fetchone()
    return r["hash"] if r else None


def _registrar_evento(c, tipo, agregado, agregado_id, payload, idem):
    prev = _ult_hash(c)
    seqr = c.execute("SELECT COALESCE(MAX(secuencia),0)+1 s FROM offline_eventos").fetchone()
    seq = seqr["s"]
    h = hashlib.sha256(f"{prev}|{tipo}|{idem}|{json.dumps(payload, sort_keys=True, default=str)}".encode()).hexdigest()
    c.execute("INSERT OR IGNORE INTO offline_eventos (idempotency_key, tipo, agregado, agregado_id, payload, "
              "hash, hash_anterior, secuencia, creado_en) VALUES (?,?,?,?,?,?,?,?,?)",
              (idem, tipo, agregado, str(agregado_id), json.dumps(payload, default=str), h, prev, seq,
               _ahora()))
    return h, seq


def _ahora():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def registrar_venta(id_empresa, idempotency_key, payload, total, *, id_tienda=0, descontar_stock=True) -> dict:
    """Registra una venta OFFLINE (idempotente), genera evento y descuenta stock local."""
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        existe = c.execute("SELECT id FROM offline_ventas WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if existe:
            return {"ok": True, "id": existe["id"], "duplicado": True}
        h = hashlib.sha256(f"{idempotency_key}|{json.dumps(payload, sort_keys=True, default=str)}".encode()).hexdigest()
        cur = c.execute("INSERT INTO offline_ventas (idempotency_key, payload, total, hash, creado_en) "
                        "VALUES (?,?,?,?,?)",
                        (idempotency_key, json.dumps(payload, default=str), float(total), h, _ahora()))
        vid = cur.lastrowid
        if descontar_stock:
            for ln in (payload.get("lineas") or []):
                cod, cant = ln.get("codigo"), float(ln.get("cantidad", 0))
                if cod:
                    c.execute("INSERT INTO offline_stock (codigo, cantidad) VALUES (?, ?) "
                              "ON CONFLICT(codigo) DO UPDATE SET cantidad=cantidad-?, version=version+1",
                              (cod, -cant, cant))
        _registrar_evento(c, "VENTA_OFFLINE", "venta", vid, payload, idempotency_key)
        c.commit()
    return {"ok": True, "id": vid, "hash": h}


def registrar_movimiento(id_empresa, idempotency_key, codigo, tipo, cantidad, *, id_tienda=0, payload=None) -> dict:
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        existe = c.execute("SELECT id FROM offline_movimientos WHERE idempotency_key=?", (idempotency_key,)).fetchone()
        if existe:
            return {"ok": True, "id": existe["id"], "duplicado": True}
        pl = payload or {"codigo": codigo, "tipo": tipo, "cantidad": cantidad}
        h = hashlib.sha256(f"{idempotency_key}|{json.dumps(pl, sort_keys=True, default=str)}".encode()).hexdigest()
        cur = c.execute("INSERT INTO offline_movimientos (idempotency_key, codigo, tipo, cantidad, payload, hash, "
                        "creado_en) VALUES (?,?,?,?,?,?,?)", (idempotency_key, codigo, tipo, float(cantidad),
                                                              json.dumps(pl, default=str), h, _ahora()))
        mid = cur.lastrowid
        delta = float(cantidad) if tipo in ("ENTRADA", "RECEPCION", "DEVOLUCION") else -float(cantidad)
        c.execute("INSERT INTO offline_stock (codigo, cantidad) VALUES (?, ?) "
                  "ON CONFLICT(codigo) DO UPDATE SET cantidad=cantidad+?, version=version+1", (codigo, delta, delta))
        _registrar_evento(c, "MOV_OFFLINE", "movimiento", mid, pl, idempotency_key)
        c.commit()
    return {"ok": True, "id": mid}


def pendientes_sync(id_empresa, *, id_tienda=0) -> dict:
    """Cuenta de registros offline aun no sincronizados (por entidad)."""
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        out = {}
        for ent in ("offline_ventas", "offline_movimientos", "offline_documentos", "offline_eventos"):
            r = c.execute(f"SELECT COUNT(*) n FROM {ent} WHERE sincronizado=0").fetchone()
            out[ent.replace("offline_", "")] = r["n"]
        return out


def items_pendientes(id_empresa, entidad, *, id_tienda=0, limite=500) -> list:
    tabla = f"offline_{entidad}"
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        rows = c.execute(f"SELECT * FROM {tabla} WHERE sincronizado=0 ORDER BY id LIMIT ?", (limite,)).fetchall()
        return [dict(r) for r in rows]


def marcar_sincronizado(id_empresa, entidad, ids, *, id_tienda=0):
    if not ids:
        return
    tabla = f"offline_{entidad}"
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        c.executemany(f"UPDATE {tabla} SET sincronizado=1 WHERE id=?", [(i,) for i in ids])
        c.commit()


def verificar_integridad(id_empresa, *, id_tienda=0) -> dict:
    """Verifica el encadenado hash del log de eventos offline (no manipulado)."""
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        rows = c.execute("SELECT hash, hash_anterior FROM offline_eventos ORDER BY secuencia").fetchall()
    prev = None
    for r in rows:
        if r["hash_anterior"] != prev:
            return {"ok": False, "roto_en": r["hash"]}
        prev = r["hash"]
    return {"ok": True, "eventos": len(rows)}


def estadisticas(id_empresa, *, id_tienda=0) -> dict:
    with _LOCK, _conn(id_empresa, id_tienda) as c:
        def _n(t):
            return c.execute(f"SELECT COUNT(*) n FROM {t}").fetchone()["n"]
        return {"articulos": _n("offline_articulos"), "clientes": _n("offline_clientes"),
                "stock": _n("offline_stock"), "ventas": _n("offline_ventas"),
                "movimientos": _n("offline_movimientos"), "eventos": _n("offline_eventos")}
