"""
SAT-H/I — KPIs de soporte (BI) + IA (clasificacion/priorizacion/sugerencia de respuesta) sin
dependencias externas. La IA es heuristica transparente sobre el texto del ticket y la KB.
"""

import logging
import re
from src.db.conexion import obtener_conexion
from src.db.empresa import empresa_actual_id

logger = logging.getLogger("sat.analitica")

# Palabras clave para clasificacion/priorizacion (datos internos, sin APIs).
_URGENTES = ("caido", "caída", "parado", "no funciona", "urgente", "critico", "crítico", "bloqueado",
             "perdida de datos", "no puedo", "error grave", "produccion parada")
_CATEGORIAS = {
    "facturacion": ("factura", "cobro", "pago", "importe", "abono"),
    "tecnico": ("error", "fallo", "bug", "no funciona", "instalacion", "configuracion"),
    "acceso": ("contraseña", "password", "login", "acceso", "usuario bloqueado"),
    "consulta": ("duda", "consulta", "como", "cómo", "informacion"),
}


def _emp(id_empresa=None):
    return id_empresa or empresa_actual_id()


def _val(cur):
    r = cur.fetchone()
    if not r:
        return 0
    return (list(r.values())[0] if isinstance(r, dict) else r[0]) or 0


def kpis(*, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    out = {}
    try:
        with obtener_conexion() as conn, conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM tickets WHERE id_empresa=%s AND estado NOT IN ('cerrado','resuelto')",
                        (eid,))
            out["tickets_abiertos"] = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM tickets WHERE id_empresa=%s AND estado IN ('cerrado','resuelto')", (eid,))
            out["tickets_cerrados"] = int(_val(cur))
            cur.execute("SELECT AVG(TIMESTAMPDIFF(HOUR, fecha_creacion, fecha_primera_respuesta)) FROM tickets "
                        "WHERE id_empresa=%s AND fecha_primera_respuesta IS NOT NULL", (eid,))
            out["tiempo_respuesta_horas"] = round(float(_val(cur)), 2)
            cur.execute("SELECT AVG(TIMESTAMPDIFF(HOUR, fecha_creacion, fecha_resolucion)) FROM tickets "
                        "WHERE id_empresa=%s AND fecha_resolucion IS NOT NULL", (eid,))
            out["tiempo_resolucion_horas"] = round(float(_val(cur)), 2)
            cur.execute("SELECT COUNT(*) FROM tickets WHERE id_empresa=%s AND sla_vencimiento IS NOT NULL", (eid,))
            con_sla = int(_val(cur))
            cur.execute("SELECT COUNT(*) FROM tickets WHERE id_empresa=%s AND sla_incumplido=1", (eid,))
            incumplidos = int(_val(cur))
            out["cumplimiento_sla_pct"] = round((con_sla - incumplidos) * 100 / con_sla, 1) if con_sla else 100.0
            cur.execute("SELECT AVG(satisfaccion) FROM tickets WHERE id_empresa=%s AND satisfaccion IS NOT NULL", (eid,))
            out["satisfaccion_media"] = round(float(_val(cur)), 2)
    except Exception as e:
        logger.error("kpis SAT: %s", e)
    return out


def registrar_en_bi(*, id_empresa=None) -> dict:
    eid = _emp(id_empresa)
    k = kpis(id_empresa=eid)
    try:
        from src.services.bi import kpis as bi_kpis
        if hasattr(bi_kpis, "guardar_valor"):
            for nombre, valor in k.items():
                if isinstance(valor, (int, float)):
                    bi_kpis.guardar_valor(f"sat_{nombre}", valor, id_empresa=eid)
    except Exception as e:
        logger.debug("registrar_en_bi: %s", e)
    return k


# ── IA SAT (heuristica, datos internos) ───────────────────────────────────────
def clasificar(texto) -> str:
    t = (texto or "").lower()
    for cat, claves in _CATEGORIAS.items():
        if any(c in t for c in claves):
            return cat
    return "general"


def priorizar(texto) -> str:
    t = (texto or "").lower()
    if any(u in t for u in _URGENTES):
        return "critica"
    if "importante" in t or "cuanto antes" in t:
        return "alta"
    return "media"


def detectar_urgencia(texto) -> bool:
    return priorizar(texto) == "critica"


def sugerir_respuesta(texto, *, id_empresa=None, top=3) -> list:
    """Sugiere articulos de la KB relevantes al texto (busqueda por palabras significativas)."""
    from src.services.sat import kb
    palabras = [w for w in re.findall(r"\w{4,}", (texto or "").lower())][:8]
    vistos, sugerencias = set(), []
    for w in palabras:
        for art in kb.buscar(w, id_empresa=id_empresa, limite=top):
            if art["id"] not in vistos:
                vistos.add(art["id"]); sugerencias.append(art)
            if len(sugerencias) >= top:
                return sugerencias
    return sugerencias


def analizar_ticket(id_ticket, *, aplicar=False, id_empresa=None) -> dict:
    """Clasifica/prioriza un ticket por su texto y opcionalmente lo aplica. Audita."""
    from src.services.sat import tickets
    t = tickets.obtener(id_ticket)
    if not t:
        return {"ok": False, "error": "ticket inexistente"}
    texto = f"{t.get('asunto', '')} {t.get('descripcion', '')}"
    cat, prio = clasificar(texto), priorizar(texto)
    if aplicar:
        try:
            with obtener_conexion() as conn, conn.cursor() as cur:
                cur.execute("UPDATE tickets SET categoria=%s, prioridad=%s WHERE id=%s", (cat, prio, id_ticket))
                conn.commit()
            from src.db.conexion import log_auditoria
            log_auditoria("sat", "TICKET_CLASIFICADO_IA", "tickets", f"ticket={id_ticket} {cat}/{prio}")
        except Exception as e:
            logger.error("analizar_ticket/aplicar: %s", e)
    return {"ok": True, "categoria": cat, "prioridad": prio,
            "sugerencias_kb": sugerir_respuesta(texto, id_empresa=id_empresa)}
