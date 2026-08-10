"""
Paquetes diferenciales (Fase 4, SUBFASE 4.3/4.4). Nunca se envia la BD completa: se empaqueta
solo el conjunto de CAMBIOS (altas/bajas/modificaciones) — cada evento es un cambio con su
payload. El contenido se serializa (JSON) y se COMPRIME (zlib) para minimizar trafico, con
hash de integridad. Reanudacion (4.5) mediante offset_aplicado en sync_paquetes.
"""

import hashlib
import json
import logging
import uuid as _uuid
import zlib

logger = logging.getLogger("sync_transport.paquetes")


def _emp(id_empresa=None):
    if id_empresa:
        return id_empresa
    try:
        from src.db.empresa import empresa_actual_id
        return empresa_actual_id()
    except Exception:
        try:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID
        except Exception:
            return None


def serializar(cambios) -> bytes:
    return json.dumps(cambios, default=str, ensure_ascii=False).encode("utf-8")


def comprimir(raw: bytes) -> bytes:
    return zlib.compress(raw, 6)


def descomprimir(comp) -> list:
    try:
        data = zlib.decompress(comp if isinstance(comp, (bytes, bytearray)) else bytes(comp))
        return json.loads(data.decode("utf-8"))
    except Exception as e:
        logger.error("descomprimir: %s", e)
        return []


def _hash(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def construir(cambios, *, origen_tienda=0, destino_tienda=0, prioridad="MEDIA", tipo="diff",
              transporte="local", id_empresa=None) -> dict | None:
    """Crea y PERSISTE un paquete diferencial comprimido. Devuelve su cabecera (sin contenido)."""
    emp = _emp(id_empresa)
    raw = serializar(cambios)
    comp = comprimir(raw)
    h = _hash(raw)
    u = str(_uuid.uuid4())
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO sync_paquetes (uuid, id_empresa, origen_tienda, destino_tienda, tipo, "
                "prioridad, num_eventos, bytes, bytes_comprimido, hash, contenido, estado, transporte) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,'CREADO',%s)",
                (u, emp, int(origen_tienda or 0), int(destino_tienda or 0), tipo, prioridad,
                 len(cambios), len(raw), len(comp), h, comp, transporte))
            pid = cur.lastrowid
            c.commit()
        return {"id": pid, "uuid": u, "hash": h, "bytes": len(raw), "bytes_comprimido": len(comp),
                "num_eventos": len(cambios), "destino_tienda": int(destino_tienda or 0),
                "ratio": round(len(comp) / len(raw), 3) if raw else 1.0}
    except Exception as e:
        logger.error("construir paquete: %s", e)
        return None


def cargar(id_paquete, id_empresa=None) -> dict | None:
    """Carga un paquete + descomprime su contenido (lista de cambios) para aplicarlo."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM sync_paquetes WHERE id=%s AND id_empresa=%s", (id_paquete, emp))
            r = _filas_a_dicts(cur, cur.fetchall())
            if not r:
                return None
            paq = r[0]
            paq["cambios"] = descomprimir(paq.get("contenido"))
            # Verificacion de integridad (4.11): el hash debe coincidir con el contenido.
            paq["integro"] = (_hash(serializar(paq["cambios"])) == paq.get("hash"))
            return paq
    except Exception as e:
        logger.error("cargar paquete: %s", e)
        return None
