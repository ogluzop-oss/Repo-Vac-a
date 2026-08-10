"""
Global SaaS · Regiones (Fase VI · Bloque 13). Soporte multi-región (Europa/América/Asia/África/
Oceanía) y resolución jerárquica Region → Cluster → Node → Tenant. Cada empresa pertenece a una
región (`empresa_region`). Reutiliza el Cloud (nodes/cluster/routing) para bajar de región a nodo.
"""

from __future__ import annotations

import logging

from src.db.conexion import _filas_a_dicts, ensure_schema, obtener_conexion

logger = logging.getLogger("saas_global.regiones")

REGIONES = ("eu", "am", "as", "af", "oc")


def listar_regiones() -> list:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo, nombre, activo FROM saas_regiones ORDER BY codigo")
            filas = _filas_a_dicts(cur, cur.fetchall())
            return filas or [{"codigo": c, "nombre": c.upper(), "activo": 1} for c in REGIONES]
    except Exception:
        return [{"codigo": c, "nombre": c.upper(), "activo": 1} for c in REGIONES]


def asignar_region(id_empresa, codigo_region, *, cluster=None) -> bool:
    if codigo_region not in REGIONES or not id_empresa:
        return False
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO empresa_region (id_empresa, codigo_region, cluster) "
                        "VALUES (%s,%s,%s) ON DUPLICATE KEY UPDATE codigo_region=VALUES(codigo_region),"
                        " cluster=VALUES(cluster), actualizado=NOW()",
                        (id_empresa, codigo_region, cluster))
            conn.commit()
        return True
    except Exception as e:
        logger.error("asignar_region: %s", e)
        return False


def region_de(id_empresa) -> str:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT codigo_region FROM empresa_region WHERE id_empresa=%s", (id_empresa,))
            r = cur.fetchone()
        if r:
            return (r[0] if not isinstance(r, dict) else r["codigo_region"])
    except Exception:
        pass
    return "eu"     # región por defecto


def resolver(id_empresa, *, estrategia="region_first") -> dict:
    """Resolución Region → Cluster → Node → Tenant. Baja hasta el nodo que atendería a la empresa,
    reutilizando el load balancing del Cloud. Devuelve la cadena resuelta (preparado)."""
    region = region_de(id_empresa)
    nodo = cluster = None
    try:
        from src.platform import cloud
        elegido = cloud.routing.elegir(estrategia, region=region,
                                       clave_sesion=str(id_empresa))
        if elegido:
            nodo = elegido.nombre
        clusters = [c for c in cloud.cluster.listar_clusters() if c.get("region") == region]
        cluster = clusters[0]["cluster"] if clusters else None
    except Exception:
        pass
    return {"region": region, "cluster": cluster, "nodo": nodo, "tenant": id_empresa}


__all__ = ["REGIONES", "listar_regiones", "asignar_region", "region_de", "resolver"]
