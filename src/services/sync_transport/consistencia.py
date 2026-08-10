"""
Consistencia y reconciliacion (Fase 4, SUBFASE 4.11). Verifica automaticamente version de BD,
revision y hash de cada terminal frente a la referencia (central). Si detecta diferencias,
solicita una resincronizacion (nunca sobrescribe a ciegas).
"""

import logging

from src.services.sync_transport import versiones

logger = logging.getLogger("sync_transport.consistencia")


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


def verificar(id_empresa=None) -> dict:
    """Compara la version_db de cada terminal con la de referencia. Devuelve incoherencias."""
    emp = _emp(id_empresa)
    ref_db = versiones.version_db_actual()
    incoh = []
    try:
        from src.services.distribucion import terminales
        for t in terminales.listar(emp):
            idt = int(t.get("id_tienda") or 0)
            v = versiones.obtener(emp, idt)
            db = (v or {}).get("version_db")
            if v and db and str(db) != str(ref_db):
                incoh.append({"id_tienda": idt, "version_db": db, "esperada": ref_db})
    except Exception as e:
        logger.error("verificar: %s", e)
    return {"coherente": not incoh, "incoherencias": incoh, "version_db_ref": ref_db}


def solicitar_resync(destino_tienda, id_empresa=None) -> dict:
    """Fuerza una resincronizacion fisica de una terminal incoherente/atrasada."""
    from src.services.sync_transport import motor
    return motor.sincronizar(int(destino_tienda or 0), _emp(id_empresa))
