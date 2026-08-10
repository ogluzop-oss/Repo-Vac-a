"""
Consultas en lenguaje natural (SUBFASE 7). Interprete de intenciones basado en reglas
(deterministico, sin LLM externo): mapea la pregunta a una consulta real del ERP y responde
SOLO con datos existentes. Nunca inventa datos.
"""

from src.services.ia import adaptadores as A
from src.services.ia import anomalias, configuracion, recomendaciones, resumenes
from src.services.ia.modelos import RespuestaIA


def _tiene(t, *claves):
    return any(k in t for k in claves)


def _resumen_agrupado(periodo, id_empresa, usuario, perfil) -> RespuestaIA:
    """SUBFASE 2.12: responde usando la AGRUPACION del timeline (no recorre millones)."""
    dias = {"dia": 1, "semana": 7, "mes": 30}.get(periodo, 1)
    try:
        from src.services.actividad import agrupacion, sincronizacion
        grupos = agrupacion.resumen_ejecutivo(id_empresa, usuario=usuario, perfil=perfil, dias=dias)
    except Exception:
        grupos = []
    top = sorted(grupos, key=lambda x: x.get("total", 0), reverse=True)
    lineas = [f"{g['total']} {str(g.get('tipo_legible') or g.get('tipo')).lower()}"
              for g in top[:8] if g.get("total")]
    try:
        from src.services.actividad import sincronizacion as _s
        off = len([x for x in _s.panel(id_empresa) if str(x.get("estado")).upper() == "OFFLINE"])
        if off:
            lineas.append(f"{off} tiendas offline")
    except Exception:
        pass
    cab = {"dia": "Hoy", "semana": "Esta semana", "mes": "Este mes"}.get(periodo, "Hoy")
    texto = (f"{cab}: " + "; ".join(lineas) + ".") if lineas else f"{cab}: sin actividad relevante."
    return RespuestaIA("resumen", texto, {"grupos": grupos})


def responder(texto, id_empresa=None, *, usuario=None, perfil=None) -> RespuestaIA:
    if not configuracion.activo("consultas", id_empresa):
        return RespuestaIA("desactivado", "Las consultas de IA estan desactivadas para esta empresa.")
    t = (texto or "").lower().strip()
    if not t:
        return RespuestaIA("vacio", "Formula una consulta. Ej.: ¿que productos necesitan reposicion?")

    # SUBFASE 3.12: preguntas de FUTURO → delega en el motor predictivo.
    if _tiene(t, "proxima semana", "proximo mes", "proximo trimestre", "ocurrira", "ocurrirá",
              "pasara", "pasará", "futuro", "predic", "preve", "preverá", "tendra rotura",
              "tendrá rotura", "habra rotura", "va a pasar", "riesgo"):
        try:
            from src.services import prediccion
            r = prediccion.servicio().responder_futuro(texto, id_empresa)
            return RespuestaIA("prediccion." + str(r.get("intent") or ""), r.get("texto") or "",
                               r.get("datos"))
        except Exception:
            pass

    if _tiene(t, "reposicion", "reponer", "necesitan stock", "falta stock", "reabastec"):
        bajo = A.articulos_bajo_umbral(id_empresa)
        return RespuestaIA("reposicion", f"{len(bajo)} articulos necesitan reposicion.",
                           bajo[:20], recomendaciones.generar(id_empresa, limite=5))

    if _tiene(t, "exceso") and _tiene(t, "stock", "almacen"):
        exc = A.articulos_exceso(id_empresa)
        return RespuestaIA("exceso_stock", f"{len(exc)} articulos con exceso de stock.", exc[:20])

    if _tiene(t, "factura") and _tiene(t, "pendiente", "cobrar", "impag"):
        fp = A.facturas_pendientes(id_empresa)
        return RespuestaIA("facturas_pendientes", f"{len(fp)} facturas pendientes de cobro.", fp[:50])

    if _tiene(t, "contrato") and _tiene(t, "vence", "vencer", "caduc", "proximo"):
        cv = A.contratos_por_vencer(id_empresa)
        return RespuestaIA("contratos", f"{len(cv)} contratos proximos a vencer.", cv)

    if _tiene(t, "anomal", "raro", "extra", "sospech"):
        an = anomalias.detectar(id_empresa)
        return RespuestaIA("anomalias", f"{len(an)} anomalias detectadas.", [a.to_dict() for a in an])

    if _tiene(t, "sincroniz", "terminal", "offline"):
        s = A.sincronizacion(id_empresa)
        g = s.get("global", {})
        off = [x for x in s.get("terminales", []) if str(x.get("estado")).upper() == "OFFLINE"]
        return RespuestaIA("sincronizacion",
                           f"{g.get('errores', 0)} errores de sync, {len(off)} terminales offline.", s)

    if _tiene(t, "vend", "venta", "factur", "ingres"):
        v = A.ventas_por_dia(id_empresa, dias=7)
        tot = sum(float(x.get("total") or 0) for x in v)
        return RespuestaIA("ventas", f"Ventas de los ultimos 7 dias: {tot:.2f}.", v)

    if _tiene(t, "ayer", "hoy", "ocurri", "paso", "pasado", "resumen", "dia") and not _tiene(t, "semana"):
        return _resumen_agrupado("dia", id_empresa, usuario, perfil)

    if _tiene(t, "semana"):
        return _resumen_agrupado("semana", id_empresa, usuario, perfil)

    return RespuestaIA("desconocido",
                       "No he entendido la consulta. Prueba con: reposicion, facturas pendientes, "
                       "ventas, anomalias, contratos por vencer, sincronizacion o resumen del dia.")
