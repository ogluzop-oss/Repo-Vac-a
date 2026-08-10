"""
Inmovilizado / Activos fijos (Módulo 11, enriquecimiento de Finanzas). Registro de bienes de
inmovilizado con amortización contable (lineal), dotación periódica, valor neto contable y bajas.
Genuinamente ausente hasta ahora (el inmovilizado solo aparecía como grupo del PGC). Multiempresa,
auditado. Reutiliza la cola contable existente para el asiento de dotación cuando está disponible.
"""

import datetime as _dt
import logging

logger = logging.getLogger("finanzas.inmovilizado")


def _emp(id_empresa=None):
    # IOC v2 (Bloque III): resolución de empresa vía capa de identidad (Strangler).
    try:
        from src.services.finanzas.identidad_finanzas import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)


def _audit(accion, detalle, tabla="inmovilizado_activos"):
    try:
        from src.db.conexion import log_auditoria
        log_auditoria("inmovilizado", accion, tabla, (detalle or "")[:255])
    except Exception:
        pass


def _filas(cur):
    from src.db.conexion import _filas_a_dicts
    return _filas_a_dicts(cur, cur.fetchall())


def alta_activo(descripcion, valor_adquisicion, *, codigo=None, categoria=None, cuenta_contable=None,
                fecha_alta=None, valor_residual=0, vida_util_meses=60, id_centro_coste=None,
                id_empresa=None) -> int | None:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("INSERT INTO inmovilizado_activos (id_empresa, codigo, descripcion, categoria, "
                        "cuenta_contable, fecha_alta, valor_adquisicion, valor_residual, vida_util_meses, "
                        "id_centro_coste) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                        (emp, codigo, descripcion[:200], categoria, cuenta_contable,
                         fecha_alta or _dt.date.today().isoformat(), float(valor_adquisicion or 0),
                         float(valor_residual or 0), int(vida_util_meses or 60), id_centro_coste))
            aid = cur.lastrowid
            c.commit()
        _audit("ACTIVO_ALTA", f"{aid}:{descripcion} {valor_adquisicion}€")
        return aid
    except Exception as e:
        logger.error("alta_activo: %s", e)
        return None


def cuota_mensual(activo) -> float:
    base = float(activo["valor_adquisicion"] or 0) - float(activo["valor_residual"] or 0)
    meses = max(1, int(activo["vida_util_meses"] or 1))
    return round(base / meses, 2)


def plan_amortizacion(id_activo, *, id_empresa=None) -> list:
    """Genera el cuadro de amortización lineal (periodo YYYY-MM, importe, acumulado, valor neto)."""
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT * FROM inmovilizado_activos WHERE id=%s AND id_empresa<=>%s", (id_activo, emp))
            filas = _filas(cur)
            if not filas:
                return []
        a = filas[0]
        cuota = cuota_mensual(a)
        meses = max(1, int(a["vida_util_meses"] or 1))
        adq = float(a["valor_adquisicion"] or 0)
        residual = float(a["valor_residual"] or 0)
        fecha = a.get("fecha_alta") or _dt.date.today().isoformat()
        try:
            y, m = int(str(fecha)[:4]), int(str(fecha)[5:7])
        except Exception:
            y, m = _dt.date.today().year, _dt.date.today().month
        plan, acumulado = [], 0.0
        for i in range(meses):
            importe = cuota
            if i == meses - 1:  # última cuota ajusta el redondeo hasta el valor residual
                importe = round(adq - residual - acumulado, 2)
            acumulado = round(acumulado + importe, 2)
            neto = round(adq - acumulado, 2)
            plan.append({"periodo": f"{y:04d}-{m:02d}", "importe": importe,
                         "acumulado": acumulado, "valor_neto": neto})
            m += 1
            if m > 12:
                m = 1; y += 1
        return plan
    except Exception as e:
        logger.error("plan_amortizacion: %s", e)
        return []


def dotar_amortizacion(id_activo, periodo, *, id_empresa=None) -> dict:
    """Registra (dota) la amortización de un periodo YYYY-MM: persiste la línea, actualiza el
    acumulado del activo y publica el asiento contable si la cola está disponible."""
    emp = _emp(id_empresa)
    try:
        plan = plan_amortizacion(id_activo, id_empresa=emp)
        linea = next((p for p in plan if p["periodo"] == periodo), None)
        if not linea:
            return {"ok": False, "motivo": "periodo fuera del plan"}
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT id FROM inmovilizado_amortizaciones WHERE id_activo=%s AND periodo=%s "
                        "AND dotada=1", (id_activo, periodo))
            if cur.fetchall():
                return {"ok": False, "motivo": "periodo ya dotado"}
            cur.execute("INSERT INTO inmovilizado_amortizaciones (id_empresa, id_activo, periodo, importe, "
                        "acumulado, valor_neto, dotada) VALUES (%s,%s,%s,%s,%s,%s,1)",
                        (emp, id_activo, periodo, linea["importe"], linea["acumulado"], linea["valor_neto"]))
            cur.execute("UPDATE inmovilizado_activos SET amortizado_acumulado=%s WHERE id=%s",
                        (linea["acumulado"], id_activo))
            c.commit()
        # Asiento de dotación (6811 a 281x) — best-effort vía la cola de posting existente.
        try:
            from src.services.contabilidad import posting
            posting.encolar("amortizacion_inmovilizado", f"ACT{id_activo}-{periodo}",
                            linea["importe"], f"{periodo}-28", subtipo="dotacion",
                            extra={"id_activo": id_activo}, id_empresa=emp)
        except Exception:
            pass
        _audit("ACTIVO_DOTACION", f"{id_activo}:{periodo} {linea['importe']}€",
               "inmovilizado_amortizaciones")
        return {"ok": True, **linea}
    except Exception as e:
        logger.error("dotar_amortizacion: %s", e)
        return {"ok": False, "motivo": str(e)}


def valor_neto_contable(id_activo, *, id_empresa=None) -> float:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT valor_adquisicion, amortizado_acumulado FROM inmovilizado_activos "
                        "WHERE id=%s AND id_empresa<=>%s", (id_activo, emp))
            r = cur.fetchone()
            if not r:
                return 0.0
            r = r if not isinstance(r, dict) else list(r.values())
            return round(float(r[0] or 0) - float(r[1] or 0), 2)
    except Exception as e:
        logger.error("valor_neto_contable: %s", e)
        return 0.0


def baja_activo(id_activo, *, fecha_baja=None, id_empresa=None) -> dict:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("UPDATE inmovilizado_activos SET estado='BAJA', fecha_baja=%s WHERE id=%s "
                        "AND id_empresa<=>%s", (fecha_baja or _dt.date.today().isoformat(), id_activo, emp))
            c.commit()
        _audit("ACTIVO_BAJA", f"{id_activo}")
        return {"ok": True, "valor_neto": valor_neto_contable(id_activo, id_empresa=emp)}
    except Exception as e:
        logger.error("baja_activo: %s", e)
        return {"ok": False, "motivo": str(e)}


def listar_activos(id_empresa=None, *, estado=None, categoria=None) -> list:
    emp = _emp(id_empresa)
    try:
        from src.db.conexion import obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            q = "SELECT * FROM inmovilizado_activos WHERE id_empresa<=>%s"; p = [emp]
            if estado:
                q += " AND estado=%s"; p.append(estado)
            if categoria:
                q += " AND categoria=%s"; p.append(categoria)
            q += " ORDER BY fecha_alta DESC"
            cur.execute(q, p)
            return _filas(cur)
    except Exception as e:
        logger.error("listar_activos: %s", e)
        return []
