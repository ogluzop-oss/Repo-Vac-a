"""
Global SaaS · Consumo (Fase VI · Bloque 13). Registro y consulta de consumo por empresa/recurso/
periodo sobre `saas_consumo`. Complementa `saas.metricas` (que ya calcula consumo agregado) para el
gate de límites. Multiempresa. Sin cobros.
"""

from __future__ import annotations

import datetime
import logging

from src.db.conexion import ensure_schema, obtener_conexion

logger = logging.getLogger("saas_global.consumo")


def _periodo(periodo=None) -> str:
    return periodo or datetime.date.today().strftime("%Y-%m")


def registrar(recurso, valor=1, *, id_empresa=None, periodo=None) -> bool:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("INSERT INTO saas_consumo (id_empresa, recurso, valor, periodo) "
                        "VALUES (%s,%s,%s,%s)", (id_empresa, recurso, int(valor), _periodo(periodo)))
            conn.commit()
        return True
    except Exception as e:
        logger.debug("registrar consumo: %s", e)
        return False


def consumo_actual(recurso, *, id_empresa=None, periodo=None) -> int:
    try:
        ensure_schema()
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COALESCE(SUM(valor),0) FROM saas_consumo WHERE id_empresa=%s AND "
                        "recurso=%s AND periodo=%s", (id_empresa, recurso, _periodo(periodo)))
            r = cur.fetchone()
        return int(r[0] if not isinstance(r, dict) else list(r.values())[0])
    except Exception:
        return 0


def resumen_empresa(id_empresa, *, periodo=None) -> dict:
    """Consumo por recurso de una empresa en el periodo (+ el resumen SaaS existente si hay)."""
    from src.services.saas_global import limites
    datos = {r: consumo_actual(r, id_empresa=id_empresa, periodo=periodo) for r in limites.RECURSOS}
    base = {}
    try:
        from src.services.saas import metricas
        base = metricas.consumo_empresa(id_empresa)
    except Exception:
        pass
    return {"id_empresa": id_empresa, "periodo": _periodo(periodo), "por_recurso": datos,
            "saas": base}


__all__ = ["registrar", "consumo_actual", "resumen_empresa"]
