"""
Informe de Gestión (Cuentas Anuales). Orquestador de SOLO LECTURA: evolución del negocio
(reutilizando `informes.perdidas_ganancias` del ejercicio y del anterior, mismo patrón que
`informe_anual.generar_informe_anual`) y riesgos/incertidumbres derivados de los ratios
financieros REALES ya calculados por `services.finanzas.ratios` (KPIs del ERP) — no se inventa
una narrativa de riesgo: se aplican umbrales estándar de análisis financiero sobre ratios que el
sistema ya computa a partir de balance/PyG/tesorería/deuda reales.

Si ni siquiera esos ratios están disponibles (contabilidad sin datos suficientes del ejercicio),
se declara honestamente que la sección requiere input manual de los administradores en vez de
fabricar un relato de riesgos.
"""

import logging

logger = logging.getLogger("contab.informe_gestion")


def _empresa(id_empresa=None):
    try:
        from src.services.contabilidad.identidad_contabilidad import empresa_id
        return empresa_id(id_empresa)
    except Exception:
        if id_empresa:
            return id_empresa
        try:
            from src.db.empresa import empresa_actual_id
            return empresa_actual_id()
        except Exception:
            from src.db.conexion import EMPRESA_DEFAULT_ID
            return EMPRESA_DEFAULT_ID


# ── Evolución del negocio ─────────────────────────────────────────────────────
def _evolucion_negocio(anio, id_empresa) -> dict:
    from src.services.contabilidad.informes import perdidas_ganancias
    actual = perdidas_ganancias(id_empresa=id_empresa, anio=anio) or {}
    anterior = perdidas_ganancias(id_empresa=id_empresa, anio=anio - 1) or {}

    def _var_pct(a, b):
        try:
            a, b = float(a or 0), float(b or 0)
            return round((a - b) * 100 / abs(b), 2) if b else None
        except Exception:
            return None

    return {
        "anio": anio, "anio_anterior": anio - 1,
        "actual": actual, "anterior": anterior,
        "variacion_ingresos_pct": _var_pct(actual.get("ingresos"), anterior.get("ingresos")),
        "variacion_gastos_pct": _var_pct(actual.get("gastos"), anterior.get("gastos")),
        "variacion_resultado_pct": _var_pct(actual.get("resultado"), anterior.get("resultado")),
    }


# ── Riesgos e incertidumbres ──────────────────────────────────────────────────
# Umbrales estándar de análisis financiero (no específicos de esta empresa, aplicados sobre
# ratios reales): solvencia<1 = patrimonio/activo no cubre el pasivo (alerta fuerte); <1.5 =
# holgura reducida. Liquidez corriente<1 = el activo corriente no cubre el pasivo exigible a
# corto. Endeudamiento>0.6 = más del 60% del activo financiado con deuda (umbral habitual de
# alerta en manuales de análisis de balances).
def _riesgos_incertidumbres(anio, id_empresa) -> dict:
    try:
        from src.services.finanzas import ratios as R
        k = R.calcular(anio=anio, id_empresa=id_empresa) or {}
    except Exception as e:
        logger.error("_riesgos_incertidumbres ratios.calcular: %s", e)
        k = {}

    if not k or all(v is None for v in k.values()):
        return {
            "senales": [],
            "ratios": k,
            "texto": ("No ha sido posible calcular ratios financieros fiables para este ejercicio "
                     "(datos contables/tesorería insuficientes) — esta sección requiere input "
                     "manual de los administradores: no se fabrica una narrativa de riesgos sin "
                     "datos reales que la respalden."),
        }

    senales = []

    solvencia = k.get("solvencia")
    if solvencia is not None:
        if solvencia < 1.0:
            senales.append({"nivel": "riesgo", "ratio": "solvencia", "valor": solvencia,
                            "texto": f"Solvencia {solvencia:.2f}: el pasivo supera al activo "
                                    "(patrimonio neto negativo o próximo a serlo) — riesgo de "
                                    "insolvencia técnica."})
        elif solvencia < 1.5:
            senales.append({"nivel": "atencion", "ratio": "solvencia", "valor": solvencia,
                            "texto": f"Solvencia {solvencia:.2f}: holgura reducida entre activo y "
                                    "pasivo."})

    liquidez = k.get("liquidez_corriente")
    if liquidez is not None and liquidez < 1.0:
        senales.append({"nivel": "riesgo", "ratio": "liquidez_corriente", "valor": liquidez,
                        "texto": f"Liquidez corriente {liquidez:.2f}: el activo corriente "
                                "estimado no cubre los pagos comprometidos a corto plazo — "
                                "riesgo de tensión de tesorería."})

    endeudamiento = k.get("endeudamiento")
    if endeudamiento is not None and endeudamiento > 0.6:
        senales.append({"nivel": "atencion", "ratio": "endeudamiento", "valor": endeudamiento,
                        "texto": f"Endeudamiento {endeudamiento * 100:.1f}% del activo financiado "
                                "con deuda — nivel de apalancamiento elevado."})

    margen_neto = k.get("margen_neto")
    if margen_neto is not None and margen_neto < 0:
        senales.append({"nivel": "riesgo", "ratio": "margen_neto", "valor": margen_neto,
                        "texto": f"Margen neto {margen_neto:.2f}%: el ejercicio arroja pérdidas."})

    texto = (f"Se han detectado {len(senales)} señal(es) de atención en los ratios financieros "
            "del ejercicio." if senales else
            "No se han detectado señales de riesgo relevantes en los ratios financieros "
            "calculados para este ejercicio (umbrales estándar de solvencia/liquidez/"
            "endeudamiento/margen).")

    return {"senales": senales, "ratios": k, "texto": texto}


# ── Orquestador público ───────────────────────────────────────────────────────
def generar_informe_gestion(anio, id_empresa=None) -> dict:
    anio = int(anio)
    id_empresa = _empresa(id_empresa)
    return {
        "anio": anio,
        "id_empresa": id_empresa,
        "evolucion_negocio": _evolucion_negocio(anio, id_empresa),
        "riesgos_incertidumbres": _riesgos_incertidumbres(anio, id_empresa),
    }
