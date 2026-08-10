"""
Tarjeta UNIVERSAL de IA predictiva (Fase 7) — componente reutilizable para mostrar previsiones/riesgo en las
pantallas empresariales EXISTENTES (Smart Stock, Reabastecimiento, Compras, Ventas). REUTILIZA la librería de
componentes existente (`gui/components/enterprise.EnterpriseCard`/`EnterpriseRiskIndicator`); NO crea una
tarjeta nueva por módulo ni recalcula predicciones (los datos vienen de `consulta.resumen_ui` / servicios).
"""


def tarjeta_prevision(resumen: dict):
    """EnterpriseCard con la previsión (a partir de `consulta.resumen_ui`). Etiqueta el ORIGEN con honestidad
    (heurística/estadística/ML); nunca lo llama 'IA' si es heurística."""
    from src.gui.components.enterprise import EnterpriseCard
    total = resumen.get("total_previsto", "—")
    subtitulo = (f"Modelo: {resumen.get('modelo')} · {resumen.get('tipo_modelo')}\n"
                 f"Confianza: {resumen.get('confianza')} · Calidad: {resumen.get('calidad_datos')}\n"
                 f"Observaciones: {resumen.get('n_observaciones')} · {resumen.get('fecha_calculo')}")
    titulo = f"🔮 {resumen.get('titulo', 'PREVISIÓN DE DEMANDA')} ({resumen.get('horizonte_dias', '—')} d)"
    return EnterpriseCard(titulo, str(total), modo="kpi", subtitulo=subtitulo)


def tarjeta_riesgo(riesgo: dict):
    """EnterpriseCard de riesgo de rotura (BAJO/MEDIO/ALTO/INSUFICIENTE) + recomendación. Reutiliza el
    indicador de riesgo existente para el color."""
    from src.gui.components.enterprise import EnterpriseCard
    nivel = str(riesgo.get("nivel", "INSUFICIENTE"))
    mapa = {"BAJO": "ok", "MEDIO": "advertencia", "ALTO": "critico"}
    reco = riesgo.get("recomendacion", "")
    cob = riesgo.get("cobertura_dias")
    sub = (f"Cobertura: {cob} días · Demanda/día: {riesgo.get('demanda_diaria', '—')}\n{reco}"
           if cob is not None else reco)
    try:
        return EnterpriseCard(f"⚠️ RIESGO DE ROTURA", nivel, modo="riesgo",
                              riesgo=mapa.get(nivel, "info"), subtitulo=sub)
    except Exception:
        return EnterpriseCard("⚠️ RIESGO DE ROTURA", nivel, modo="kpi", subtitulo=sub)
