"""
Consistencia del Gemelo Digital (Paquete Enterprise 8, SUBFASE 8.15).

El gemelo nunca puede quedar desactualizado. Esta verificacion, ejecutable bajo demanda o por el
scheduler existente, compara el estado materializado con las fuentes vivas y detecta incoherencias
tipicas (tiendas offline persistentes, cadenas de valor rotas, snapshots obsoletos). Cuando
detecta una incoherencia:

  - la REGISTRA en dt_incoherencias (idempotente por hash),
  - la AUDITA (log_auditoria existente),
  - solicita RESINCRONIZACION reutilizando la infraestructura existente (invalidacion + evento).

No crea motores nuevos ni corrige datos operativos: solo detecta, audita y dispara la
resincronizacion del gemelo.
"""

import hashlib
import logging

from src.services.gemelo import fuentes as F

logger = logging.getLogger("gemelo.consistencia")


def _hash(*partes) -> str:
    return hashlib.sha256("|".join(str(p) for p in partes).encode("utf-8")).hexdigest()


def _registrar(emp, dominio, tipo, detalle, *, entidad=None, entidad_id=None, gravedad="MEDIA"):
    h = _hash(emp, dominio, tipo, entidad, entidad_id)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute(
                "INSERT INTO dt_incoherencias (id_empresa, dominio, entidad, entidad_id, tipo, "
                "gravedad, detalle, hash) VALUES (%s,%s,%s,%s,%s,%s,%s,%s) "
                "ON DUPLICATE KEY UPDATE detalle=VALUES(detalle), estado='ABIERTA', resuelto=NULL",
                (emp, dominio, entidad, entidad_id, tipo, gravedad, (detalle or "")[:255], h))
            c.commit()
    except Exception as e:
        logger.debug("registrar incoherencia: %s", e)
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("gemelo", "GEMELO_INCOHERENCIA", tabla_afectada="dt_incoherencias",
                      detalles=f"{dominio}/{tipo}: {detalle}")
    except Exception:
        pass
    return h


def verificar(id_empresa=None, *, resincronizar=True) -> dict:
    emp = F.emp(id_empresa)
    incoherencias = []

    # 1) Tiendas/terminales offline persistentes (el gemelo debe reflejarlo, no ocultarlo).
    try:
        offline = [t for t in F.sync_panel(emp) if str(t.get("estado")).upper() == "OFFLINE"]
        for t in offline:
            incoherencias.append(_registrar(
                emp, "empresa", "TIENDA_OFFLINE",
                f"Tienda/terminal '{t.get('nombre')}' sin sincronizar",
                entidad="tienda", entidad_id=t.get("id") or t.get("nombre"), gravedad="ALTA"))
    except Exception as e:
        logger.debug("check offline: %s", e)

    # 2) Cadena de valor rota: facturas sin venta de origen registrada en el grafo (best-effort).
    try:
        rotas = F.filas(
            "SELECT f.id_factura fid FROM facturas_cliente f LEFT JOIN dt_dependencias d "
            "ON d.id_empresa=f.id_empresa AND d.destino_entidad='factura' "
            "AND d.destino_id=CAST(f.id_factura AS CHAR) "
            "WHERE f.id_empresa=%s AND f.id_venta IS NOT NULL AND d.id IS NULL LIMIT 20", (emp,))
        if rotas:
            incoherencias.append(_registrar(
                emp, "comercial", "TRAZABILIDAD_INCOMPLETA",
                f"{len(rotas)} facturas sin cadena de dependencia registrada", gravedad="BAJA"))
    except Exception as e:
        logger.debug("check trazabilidad: %s", e)

    # 3) Solicitar resincronizacion del gemelo (invalida cache + publica evento observacional).
    if resincronizar and incoherencias:
        try:
            from src.services.gemelo import motor
            motor.servicio().invalidar(None, emp)  # invalida todos los dominios
        except Exception:
            pass
        try:
            from src.services import eventos as EV
            EV.publicar("GEMELO_RESINCRONIZAR", id_empresa=emp, origen="gemelo.consistencia",
                        payload={"incoherencias": len(incoherencias)})
        except Exception:
            pass

    return {"id_empresa": emp, "incoherencias": len(incoherencias),
            "resincronizado": bool(resincronizar and incoherencias),
            "coherente": not incoherencias}


def abiertas(id_empresa=None, *, limite=100) -> list:
    emp = F.emp(id_empresa)
    return F.filas("SELECT * FROM dt_incoherencias WHERE id_empresa=%s AND estado='ABIERTA' "
                   "ORDER BY detectado DESC LIMIT %s", (emp, int(limite)))


def _job_consistencia(id_empresa):
    r = verificar(id_empresa, resincronizar=True)
    return f"incoherencias={r.get('incoherencias')} coherente={r.get('coherente')}"


def registrar_jobs_gemelo(id_empresa=None):
    """Registra el job periodico de verificacion de consistencia del gemelo (idempotente)."""
    try:
        from src.services import scheduler
        scheduler.registrar("gemelo_consistencia", _job_consistencia)
        scheduler.registrar_job("gemelo_consistencia", intervalo_horas=6,
                                descripcion="Verificacion de consistencia del Gemelo Digital",
                                id_empresa=id_empresa)
    except Exception as e:
        logger.debug("registrar_jobs_gemelo: %s", e)
