"""
Motor de RAZONAMIENTO del SomaObserver (Fase 4). No se limita a informar: INTERPRETA los datos ya
calculados por la infraestructura (PredictionService, Gemelo Digital, Workflow, Auditoría, BI/KPIs)
y produce HALLAZGOS explicables (qué ha ocurrido, en qué datos se basa, qué consecuencias prevé y qué
conviene hacer). Reutiliza los servicios existentes; nunca recalcula ni crea un segundo motor.

Cada hallazgo es EXPLICABLE por diseño: lleva por_que / datos / consecuencias / accion.
"""

import hashlib
import logging

from src.soma import prioridad as P

logger = logging.getLogger("soma.razonamiento")


def _emp(id_empresa=None):
    try:
        from src.services.gemelo import fuentes
        return fuentes.emp(id_empresa)
    except Exception:
        return id_empresa


def hallazgo(clave, titulo, mensaje, *, prioridad=P.MEDIA, dominio="general",
             por_que="", datos=None, consecuencias="", accion="") -> dict:
    h = f"{clave}"
    return {
        "clave": hashlib.sha256(h.encode("utf-8")).hexdigest()[:16],
        "clave_legible": clave,
        "titulo": titulo,
        "mensaje": mensaje,
        "prioridad": prioridad,
        "dominio": dominio,
        "por_que": por_que,
        "datos": datos or {},
        "consecuencias": consecuencias,
        "accion": accion,
    }


# ── PREDICCIÓN (roturas, impagos, caídas de ventas, sobrestock, riesgos) ───────
def analizar_predicciones(emp) -> list:
    out = []
    try:
        from src.services import prediccion
        svc = prediccion.servicio()
    except Exception:
        return out
    # Riesgos interpretados
    try:
        for r in (svc.riesgos(emp) or []):
            texto = r.get("texto") or r.get("descripcion") or ""
            nivel = str(r.get("nivel") or r.get("gravedad") or "MEDIO").upper()
            dom = r.get("dominio") or r.get("categoria") or "riesgo"
            if not texto:
                continue
            out.append(hallazgo(
                f"pred_riesgo_{dom}_{texto[:40]}",
                "Riesgo detectado",
                f"He detectado algo que creo que deberías revisar: {texto}",
                prioridad=P.desde_riesgo(nivel), dominio=str(dom),
                por_que="Lo señala el motor predictivo del ERP a partir de la evolución reciente.",
                datos=r, consecuencias="Si la tendencia continúa, podría agravarse en los próximos días.",
                accion="Puedo prepararte una propuesta (pasaría por aprobación) si quieres."))
    except Exception as e:
        logger.debug("riesgos: %s", e)
    # Stock: rotura / sobrestock razonados
    try:
        st = svc.stock(emp)
        preds = {p.get("metrica"): p.get("valor") for p in (st.get("predicciones") or [])}
        rot = int(preds.get("rotura_stock", 0) or 0)
        exc = int(preds.get("sobrestock", 0) or 0)
        if rot:
            out.append(hallazgo(
                f"pred_rotura_{rot}", "Riesgo de rotura de stock",
                f"Creo que merece tu atención: hay {rot} artículo(s) en riesgo de quedarse sin stock. "
                "Si el consumo se mantiene, faltarán antes de que llegue la reposición.",
                prioridad=P.ALTA if rot > 5 else P.MEDIA, dominio="inventario",
                por_que="El motor predictivo proyecta el consumo reciente frente al stock disponible.",
                datos={"articulos_en_riesgo": rot},
                consecuencias="Posibles ventas perdidas o incidencias por falta de producto.",
                accion="Puedo preparar una propuesta de reposición (la decides tú)."))
        if exc > 5:
            out.append(hallazgo(
                f"pred_sobrestock_{exc}", "Posible sobrestock",
                f"He encontrado una posible mejora: {exc} artículo(s) presentan sobrestock. "
                "Podrías liberar inmovilizado ajustando las próximas compras.",
                prioridad=P.MEDIA, dominio="inventario",
                por_que="El motor predictivo compara el stock con la rotación esperada.",
                datos={"articulos_sobrestock": exc},
                consecuencias="Inmovilizado innecesario y riesgo de merma/caducidad.",
                accion="Puedo proponer una revisión de las compras de esos artículos."))
    except Exception as e:
        logger.debug("stock: %s", e)
    return out


# ── GEMELO DIGITAL (estado por dominios, alertas, consistencia) ────────────────
def analizar_gemelo(emp) -> list:
    out = []
    try:
        from src.services import gemelo
        g = gemelo.servicio().estado_empresa(emp)
    except Exception:
        return out
    for alerta in (g.get("alertas") or []):
        dom = alerta.get("dominio") if isinstance(alerta, dict) else "empresa"
        texto = alerta.get("texto") if isinstance(alerta, dict) else str(alerta)
        if not texto:
            continue
        riesgo = str((g.get("dominios") or {}).get(dom, {}).get("riesgo", "MEDIO")).upper()
        out.append(hallazgo(
            f"gemelo_{dom}_{texto[:40]}", "Estado de la empresa",
            f"Revisando el estado de la empresa, creo que esto merece tu atención: {texto}",
            prioridad=P.desde_riesgo(riesgo), dominio=str(dom),
            por_que="Lo refleja el Gemelo Digital al agregar el estado vivo de ese dominio.",
            datos={"alerta": texto, "riesgo": riesgo},
            consecuencias="Puede afectar a la operativa si no se atiende.",
            accion="Puedo darte el detalle del dominio afectado."))
    return out


# ── WORKFLOW (procesos bloqueados / cuellos de botella) ───────────────────────
def analizar_workflow(emp) -> list:
    out = []
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM wf_instancias WHERE id_empresa=%s "
                        "AND estado IN ('EN_CURSO','PENDIENTE')", (emp,))
            r = _filas_a_dicts(cur, cur.fetchall())
            pend = int((r[0].get("n") if r else 0) or 0)
    except Exception:
        pend = 0
    if pend >= 5:
        out.append(hallazgo(
            f"wf_pendientes_{pend}", "Aprobaciones acumuladas",
            f"He observado que hay {pend} procesos pendientes de aprobación. Podría estar "
            "formándose un cuello de botella en el flujo de trabajo.",
            prioridad=P.ALTA if pend >= 10 else P.MEDIA, dominio="workflow",
            por_que="Recuento de instancias de Workflow en curso/pendientes.",
            datos={"pendientes": pend},
            consecuencias="Retrasos en decisiones y en la operativa dependiente.",
            accion="Puedo mostrarte la bandeja de aprobaciones para agilizarlas."))
    return out


# ── AUDITORÍA (errores repetidos / patrones inusuales) ────────────────────────
def analizar_auditoria(emp) -> list:
    out = []
    try:
        from src.db.conexion import _filas_a_dicts, obtener_conexion
        with obtener_conexion() as c, c.cursor() as cur:
            cur.execute("SELECT COUNT(*) n FROM auditoria_logs WHERE accion LIKE '%ERROR%' "
                        "AND fecha >= (NOW() - INTERVAL 1 DAY)")
            r = _filas_a_dicts(cur, cur.fetchall())
            errs = int((r[0].get("n") if r else 0) or 0)
    except Exception:
        errs = 0
    if errs >= 10:
        out.append(hallazgo(
            f"audit_errores_{errs}", "Errores repetidos",
            f"He notado {errs} errores registrados en las últimas 24 horas. No es una acusación: "
            "quizá hay un proceso que conviene revisar.",
            prioridad=P.MEDIA, dominio="auditoria",
            por_que="Recuento de entradas de error en la auditoría del día.",
            datos={"errores_24h": errs},
            consecuencias="Posible incidencia recurrente afectando a la operativa.",
            accion="Puedo ayudarte a localizar el origen si quieres."))
    return out


# ── KPIs (Business Intelligence): fuera de rango / anómalos ───────────────────
def analizar_kpis(emp) -> list:
    out = []
    try:
        from src.services.bi import dashboard as _D
        panel = _D.panel(emp, periodo="mes", con_forecast=False) or {}
    except Exception:
        return out
    # Interpretación prudente: liquidez estimada negativa u otros marcadores explícitos.
    fl = panel.get("forecast_liquidez") or {}
    try:
        for p in (fl.get("proyecciones") or []):
            if p.get("horizonte_dias") == 90 and float(p.get("liquidez_estimada", 0)) < 0:
                out.append(hallazgo(
                    "kpi_liquidez_90", "Liquidez en riesgo",
                    "Analizando los KPIs, la liquidez estimada a 90 días es negativa. Creo que "
                    "deberías revisarlo con tiempo para anticiparte.",
                    prioridad=P.ALTA, dominio="tesoreria",
                    por_que="Proyección de liquidez del cuadro de mando (BI).",
                    datos={"liquidez_90d": p.get("liquidez_estimada")},
                    consecuencias="Tensiones de tesorería si no se planifica.",
                    accion="Puedo mostrarte la previsión financiera detallada."))
                break
    except Exception as e:
        logger.debug("kpis: %s", e)
    return out


def recopilar(id_empresa=None) -> list:
    """Ejecuta todo el razonamiento y devuelve la lista de hallazgos (interpretados y explicables)."""
    emp = _emp(id_empresa)
    hallazgos = []
    for fn in (analizar_predicciones, analizar_gemelo, analizar_workflow,
               analizar_auditoria, analizar_kpis):
        try:
            hallazgos.extend(fn(emp) or [])
        except Exception as e:
            logger.debug("razonamiento %s: %s", fn.__name__, e)
    return hallazgos
