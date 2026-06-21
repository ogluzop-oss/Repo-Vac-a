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
# Ámbito de la numeración/cadena hash. Cada serie efectiva tiene su propia cadena.
ESTRATEGIAS_SERIE = ("empresa", "tienda", "caja")


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
            "proveedor": "simulado", "integrador": "", "serie": "A",
            "serie_por": "tienda", "entorno": "preproduccion", "activo": 0}
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
                   serie=None, serie_por=None, entorno=None, activo=None,
                   id_empresa=None) -> bool:
    id_empresa = _empresa(id_empresa)
    a = obtener_config(id_empresa)
    sp = (serie_por or a.get("serie_por") or "tienda")
    if sp not in ESTRATEGIAS_SERIE:
        sp = "tienda"
    en = (entorno or a.get("entorno") or "preproduccion")
    if en not in ("preproduccion", "produccion"):
        en = "preproduccion"
    n = {"territorio": territorio or a["territorio"], "modo": modo or a["modo"],
         "proveedor": proveedor or a["proveedor"],
         "integrador": integrador if integrador is not None else a["integrador"],
         "serie": serie or a["serie"], "serie_por": sp, "entorno": en,
         "activo": int(activo if activo is not None else a["activo"])}
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute(
                "INSERT INTO fiscal_config (id_empresa, territorio, modo, proveedor, "
                "integrador, serie, serie_por, entorno, activo) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE territorio=VALUES(territorio), modo=VALUES(modo), "
                "proveedor=VALUES(proveedor), integrador=VALUES(integrador), "
                "serie=VALUES(serie), serie_por=VALUES(serie_por), entorno=VALUES(entorno), "
                "activo=VALUES(activo)",
                (id_empresa, n["territorio"], n["modo"], n["proveedor"], n["integrador"],
                 n["serie"], n["serie_por"], n["entorno"], n["activo"]))
            conn.commit()
        return True
    except Exception as e:
        logger.error("guardar_config: %s", e)
        return False


def serie_efectiva(config: dict, id_tienda=None, id_caja=None) -> str:
    """Resuelve la serie efectiva según la estrategia `serie_por`. Cada serie
    efectiva mantiene su PROPIA cadena hash (numeración independiente):

        empresa → "A"            (una serie por empresa)
        tienda  → "A-T<tienda>"  (una por tienda; por defecto)
        caja    → "A-C<caja>"    (una por caja/terminal)

    Degradación segura: si falta el ámbito (p. ej. instalación de tienda única
    sin id_tienda), cae a la serie base para no romper la numeración existente."""
    base = (config or {}).get("serie") or "A"
    estrategia = (config or {}).get("serie_por") or "tienda"
    if estrategia == "caja" and id_caja not in (None, ""):
        return f"{base}-C{_token_serie(id_caja)}"
    if estrategia in ("caja", "tienda") and id_tienda not in (None, ""):
        return f"{base}-T{_token_serie(id_tienda)}"
    return base


def _token_serie(valor) -> str:
    """Normaliza un identificador de tienda/caja a un sufijo de serie estable
    (alfanumérico). 'CAJA-01' → 'CAJA01'; 3 → '3'."""
    return "".join(ch for ch in str(valor) if ch.isalnum()) or "0"


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
                      id_empresa=None, id_tienda="auto", id_caja=None,
                      campos_hash=None, huella_fn=None) -> dict:
    """Inserta un registro fiscal ENCADENADO (numeración y hash por empresa+serie).
    Atómico (transacción + bloqueo) para que la cadena sea consistente bajo
    concurrencia. Devuelve el registro creado (con numero/hash/hash_anterior).

    Si no se indica `serie`, se resuelve la serie efectiva según la estrategia
    `serie_por` de la empresa (empresa/tienda/caja).

    Puntos de extensión (aditivos, retrocompatibles):
    - `campos_hash`: dict o callable(serie,numero,tipo,referencia,total)->dict con
      los campos que entran en la huella (cada régimen fija los suyos).
    - `huella_fn`: callable(campos, hash_anterior)->str para serializar la huella
      con el FORMATO LEGAL del régimen (Verifactu). Si es None, se usa la huella
      neutra del núcleo (comportamiento histórico intacto)."""
    id_empresa = _empresa(id_empresa)
    if id_tienda == "auto":
        try:
            from src.db.empresa import tienda_actual_id
            id_tienda = tienda_actual_id()
        except Exception:
            id_tienda = None
    if not serie:
        serie = serie_efectiva(obtener_config(id_empresa), id_tienda, id_caja)
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
            # `campos_hash` puede ser un dict precomputado o un callable que recibe
            # el número definitivo (resuelto atómicamente aquí) → cada proveedor
            # decide qué campos entran en la huella sin perder el encadenado seguro.
            if callable(campos_hash):
                datos = campos_hash(serie, numero, tipo, referencia,
                                    round(float(total or 0), 2))
            else:
                datos = campos_hash or {"serie": serie, "numero": numero, "tipo": tipo,
                                        "referencia": referencia,
                                        "total": round(float(total or 0), 2)}
            # `huella_fn` permite el formato legal del régimen; por defecto, núcleo.
            h = (huella_fn or huella)(datos, ult_hash)
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


def existe_registro(referencia, id_empresa=None) -> dict | None:
    """H4 — idempotencia fiscal: devuelve el registro fiscal de una referencia si ya existe
    (una venta = un registro fiscal). NO crea nada. Conserva numeración/hash/Verifactu."""
    if referencia is None:
        return None
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_registros WHERE id_empresa=%s AND referencia=%s "
                        "ORDER BY id LIMIT 1", (id_empresa, str(referencia)))
            return _filas_a_dicts(cur, cur.fetchall())[0] if cur.rowcount else None
    except Exception as e:
        logger.error("existe_registro(%s): %s", referencia, e)
        return None


def actualizar_estado(id_registro, estado) -> bool:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE fiscal_registros SET estado=%s WHERE id=%s", (estado, id_registro))
            conn.commit()
        return True
    except Exception as e:
        logger.error("actualizar_estado(%s): %s", id_registro, e)
        return False


def _proveedor_inst(proveedor):
    """Instancia del proveedor (para reutilizar su campos_hash/huella en la
    verificación). None si no está disponible."""
    try:
        from src.services.fiscal.registry import clase_de
        clase = clase_de(proveedor)
        return clase() if clase is not None else None
    except Exception:
        return None


def _campos_neutros(serie, numero, tipo, referencia, total) -> dict:
    return {"serie": serie, "numero": numero, "tipo": tipo,
            "referencia": referencia, "total": round(float(total or 0), 2)}


def cadena_valida(id_empresa=None, serie="A") -> bool:
    """Verifica la integridad del encadenado hash de una serie (re-calcula y compara).
    Re-deriva la huella con `recalcular_huella` del PROVEEDOR de cada registro, de
    modo que valida igual el formato neutro (simulado) y el legal (Verifactu)."""
    id_empresa = _empresa(id_empresa)
    prev = None
    for reg in listar_registros(id_empresa, serie=serie, limite=100000):
        inst = _proveedor_inst(reg.get("proveedor"))
        if inst is not None:
            esperado = inst.recalcular_huella(reg, prev)
        else:
            esperado = huella(_campos_neutros(reg["serie"], reg["numero"], reg["tipo"],
                                              reg["referencia"],
                                              round(float(reg["total"] or 0), 2)), prev)
        if reg["hash_anterior"] != prev or esperado != reg["hash"]:
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


def listar_cola(estado="pendiente", id_empresa=None, limite=200, listos=False) -> list:
    """Lista entradas de la cola. Con `listos=True` excluye las que aún están en
    espera de backoff (proximo_intento en el futuro) → lo usa el worker."""
    id_empresa = _empresa(id_empresa)
    extra = " AND (proximo_intento IS NULL OR proximo_intento <= NOW())" if listos else ""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_cola WHERE id_empresa=%s AND estado=%s"
                        + extra + " ORDER BY fecha LIMIT %s",
                        (id_empresa, estado, int(limite)))
            return _filas_a_dicts(cur, cur.fetchall())
    except Exception as e:
        logger.error("listar_cola: %s", e)
        return []


def actualizar_cola(id_cola, estado, error=None, proximo_intento=None) -> bool:
    """Actualiza una entrada de la cola. `proximo_intento` (datetime/str) programa
    el siguiente reintento (backoff)."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE fiscal_cola SET estado=%s, intentos=intentos+1, "
                        "ultimo_error=%s, proximo_intento=%s WHERE id=%s",
                        (estado, (error or "")[:500] or None, proximo_intento, id_cola))
            conn.commit()
        return True
    except Exception as e:
        logger.error("actualizar_cola(%s): %s", id_cola, e)
        return False


def actualizar_aeat(id_registro, estado_aeat=None, csv_aeat=None) -> bool:
    """Persiste la trazabilidad de AEAT (estado y CSV del acuse) de un registro.
    Aditivo: columnas creadas por la migración 0004; no altera el encadenado."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("UPDATE fiscal_registros SET estado_aeat=%s, csv_aeat=%s WHERE id=%s",
                        (estado_aeat, csv_aeat, id_registro))
            conn.commit()
        return True
    except Exception as e:
        logger.error("actualizar_aeat(%s): %s", id_registro, e)
        return False


def obtener_registro(id_registro) -> dict | None:
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_registros WHERE id=%s", (id_registro,))
            r = cur.fetchone()
            return _filas_a_dicts(cur, [r])[0] if r else None
    except Exception as e:
        logger.error("obtener_registro(%s): %s", id_registro, e)
        return None


def obtener_por_serie_numero(id_empresa, serie, numero) -> dict | None:
    """Registro por (empresa, serie, numero). Lo usa el serializador XML para
    reconstruir el `RegistroAnterior` del encadenamiento. Aditivo, solo lectura."""
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_registros WHERE id_empresa=%s AND serie=%s "
                        "AND numero=%s LIMIT 1", (id_empresa, serie, int(numero)))
            r = cur.fetchone()
            return _filas_a_dicts(cur, [r])[0] if r else None
    except Exception as e:
        logger.error("obtener_por_serie_numero(%s,%s): %s", serie, numero, e)
        return None


def obtener_por_referencia(referencia, id_empresa=None, tipo="ticket") -> dict | None:
    """Último registro fiscal de una referencia (p. ej. venta_id) de la empresa.
    Lo usa el ticket para incrustar el QR/leyenda legales. Aditivo, solo lectura."""
    id_empresa = _empresa(id_empresa)
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT * FROM fiscal_registros WHERE id_empresa=%s AND referencia=%s "
                        "AND tipo=%s ORDER BY id DESC LIMIT 1",
                        (id_empresa, str(referencia), tipo))
            r = cur.fetchone()
            return _filas_a_dicts(cur, [r])[0] if r else None
    except Exception as e:
        logger.error("obtener_por_referencia(%s): %s", referencia, e)
        return None
