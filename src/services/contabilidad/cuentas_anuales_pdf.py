"""
PDF de la Memoria + Informe de Gestión + Propuesta de Aplicación del Resultado (Cuentas Anuales).
Reutiliza EXACTAMENTE el mismo patrón que `cierre_pdf.py`/`informe_anual_pdf.py` (helpers
`rrhh.documents.render.estilo_pdf`, B/N, esquinas redondeadas) — sin motor de PDF paralelo.

Archivo NUEVO en vez de extender `informe_anual_pdf.py`: ese módulo renderiza un documento
DISTINTO (el Informe Anual de Empresa de la pestaña "Cierres", con sus propias secciones de
ventas/plantilla/inversión) — las Cuentas Anuales son un documento legal distinto (Memoria +
Informe de Gestión + Propuesta de Aplicación del Resultado) que un orquestador posterior
combinará con el Balance/ECPN/Estado de Flujos (servicio hermano, no construido aquí). Mezclar
ambos en un solo fichero acoplaría dos documentos con ciclos de vida y "dueños" distintos.

Recibe los dicts YA calculados por `memoria_anual.generar_memoria`,
`informe_gestion.generar_informe_gestion` y `propuesta_resultado.calcular_propuesta_aplicacion`
(no vuelve a consultar nada): son la única fuente de verdad de este documento.
"""

import logging
import os
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer

from src.rrhh.documents.render import estilo_pdf as E

logger = logging.getLogger("contab.cuentas_anuales_pdf")


def _dir_cuentas_anuales() -> str:
    # cuentas_anuales_pdf.py está en src/services/contabilidad/ (3 niveles bajo la raíz) — 4
    # `dirname` para llegar a la raíz (mismo criterio que cierre_pdf.py/informe_anual_pdf.py).
    raiz = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    base = os.path.join(raiz, "documentos", "CuentasAnuales")
    os.makedirs(base, exist_ok=True)
    return base


def _eur(v):
    if isinstance(v, str):
        return v
    try:
        from src.utils import divisas
        return divisas.formatear(v)
    except Exception:
        return f"{float(v or 0):,.2f} €"


def _parrafo(texto, sty):
    return Paragraph((texto or "").replace("\n", "<br/>"), sty["just"])


# ── Etiquetas (clave interna → texto legible) de las partidas de Balance/ECPN/Flujos ─────────
_ETQ_ACTIVO_NC = {"inmovilizado_intangible": "Inmovilizado intangible",
                  "inmovilizado_material": "Inmovilizado material",
                  "inversiones_inmobiliarias": "Inversiones inmobiliarias",
                  "inmovilizado_en_curso": "Inmovilizado en curso",
                  "inversiones_financieras_largo_plazo": "Inversiones financieras L/P",
                  "activo_impuesto_diferido": "Activo por impuesto diferido"}
_ETQ_ACTIVO_C = {"existencias": "Existencias", "deudores_comerciales": "Deudores comerciales",
                 "otros_deudores": "Otros deudores", "hp_deudora": "Hacienda Pública deudora",
                 "inversiones_financieras_corto_plazo": "Inversiones financieras C/P",
                 "periodificaciones": "Periodificaciones", "efectivo": "Efectivo y equivalentes"}
_ETQ_PASIVO_NC = {"provisiones": "Provisiones L/P", "deudas_grupo_largo_plazo": "Deudas grupo L/P",
                  "deudas_financieras_largo_plazo": "Deudas financieras L/P",
                  "deudas_largo_plazo_otras": "Otras deudas L/P",
                  "pasivo_impuesto_diferido": "Pasivo por impuesto diferido"}
_ETQ_PASIVO_C = {"deudas_grupo_corto_plazo": "Deudas grupo C/P",
                 "deudas_financieras_corto_plazo": "Deudas financieras C/P",
                 "acreedores_comerciales": "Acreedores comerciales",
                 "hp_ss_acreedoras": "Hacienda Pública y SS acreedoras",
                 "periodificaciones": "Periodificaciones", "otras_deudas": "Otras deudas"}
_ETQ_PN = {"capital": "Capital", "prima_emision": "Prima de emisión",
           "otros_instrumentos_patrimonio": "Otros instrumentos de patrimonio",
           "otras_aportaciones_socios": "Otras aportaciones de socios", "reservas": "Reservas",
           "acciones_propias_resta": "Acciones propias (-)",
           "resultados_ejercicios_anteriores": "Resultados de ejercicios anteriores",
           "resultado_del_ejercicio": "Resultado del ejercicio",
           "ajustes_y_subvenciones": "Subvenciones y ajustes por cambio de valor"}


def _etq(clave, mapa):
    return mapa.get(clave, clave.replace("_", " ").capitalize())


def _filas_importe(dic, mapa, excluir=("total",)):
    """[(etiqueta, importe)] de un dict de partidas, en el mismo orden de inserción, excluyendo
    `excluir` (normalmente la clave 'total', que se renderiza aparte con `tabla_importes`)."""
    return [(_etq(k, mapa), v) for k, v in dic.items() if k not in excluir]


def _tabla_balance(balance, usable_w, sty):
    """Tablas del Balance de Situación (activo / PN+pasivo) + nota de cuadre, reutilizando
    `tabla_importes` (mismo helper que el resto de este PDF, sin motor de tablas paralelo)."""
    act = balance.get("activo", {})
    pnp = balance.get("pn_pasivo", {})
    pn = pnp.get("patrimonio_neto", {})
    fp = pn.get("fondos_propios", {})
    aj = pn.get("ajustes_y_subvenciones", {})

    bloques = [E.seccion("Activo", usable_w, sty), Spacer(1, 1.5 * mm),
               E.tabla_importes("ACTIVO NO CORRIENTE",
                                _filas_importe(act.get("no_corriente", {}), _ETQ_ACTIVO_NC),
                                "Total activo no corriente", act.get("no_corriente", {}).get("total", 0),
                                usable_w, sty),
               Spacer(1, 2 * mm),
               E.tabla_importes("ACTIVO CORRIENTE",
                                _filas_importe(act.get("corriente", {}), _ETQ_ACTIVO_C),
                                "Total activo corriente", act.get("corriente", {}).get("total", 0),
                                usable_w, sty),
               Spacer(1, 2 * mm),
               E.total_row("TOTAL ACTIVO", act.get("total", 0), usable_w, sty),
               Spacer(1, 5 * mm),
               E.seccion("Patrimonio neto y pasivo", usable_w, sty), Spacer(1, 1.5 * mm),
               E.tabla_importes("PATRIMONIO NETO — FONDOS PROPIOS",
                                _filas_importe(fp, _ETQ_PN), "Total fondos propios",
                                fp.get("total", 0), usable_w, sty),
               Spacer(1, 2 * mm)]
    if aj.get("total"):
        bloques += [E.tabla_importes("SUBVENCIONES Y AJUSTES",
                                     _filas_importe(aj, _ETQ_PN), "Total ajustes",
                                     aj.get("total", 0), usable_w, sty),
                   Spacer(1, 2 * mm)]
    bloques += [E.tabla_importes("PASIVO NO CORRIENTE",
                                 _filas_importe(pnp.get("pasivo_no_corriente", {}), _ETQ_PASIVO_NC),
                                 "Total pasivo no corriente",
                                 pnp.get("pasivo_no_corriente", {}).get("total", 0), usable_w, sty),
               Spacer(1, 2 * mm),
               E.tabla_importes("PASIVO CORRIENTE",
                                _filas_importe(pnp.get("pasivo_corriente", {}), _ETQ_PASIVO_C),
                                "Total pasivo corriente",
                                pnp.get("pasivo_corriente", {}).get("total", 0), usable_w, sty),
               Spacer(1, 2 * mm),
               E.total_row("TOTAL PATRIMONIO NETO + PASIVO", pnp.get("total", 0), usable_w, sty),
               Spacer(1, 3 * mm)]
    nota = ("✔ El balance cuadra (Activo = PN + Pasivo)." if balance.get("cuadra")
           else f"⚠ El balance NO cuadra: diferencia de {_eur(balance.get('diferencia'))}.")
    bloques.append(_parrafo(nota, sty))
    for aviso in balance.get("advertencias") or []:
        bloques += [Spacer(1, 1.5 * mm), _parrafo(f"⚠ {aviso}", sty)]
    return bloques


def _tabla_ecpn(ecpn, usable_w, sty):
    """Tabla del Estado de Cambios en el Patrimonio Neto (inicial/movimiento/final por partida)."""
    lineas = ecpn.get("lineas", {})
    filas = [{"concepto": _etq(k, _ETQ_PN), "inicial": _eur(v.get("inicial")),
              "movimiento": _eur(v.get("movimiento")), "final": _eur(v.get("final"))}
             for k, v in lineas.items()]
    bloques = [
        E.tabla_columnas([("concepto", "Partida"), ("inicial", f"Saldo inicial"),
                          ("movimiento", "Movimiento"), ("final", "Saldo final")],
                         filas, usable_w, sty),
        Spacer(1, 2 * mm),
        E.grid_datos([("pn_inicial", "PN inicial"), ("total_movimientos", "Total movimientos"),
                      ("pn_final", "PN final")],
                     {"pn_inicial": _eur(ecpn.get("pn_inicial")),
                      "total_movimientos": _eur(ecpn.get("total_movimientos")),
                      "pn_final": _eur(ecpn.get("pn_final"))}, usable_w, sty, cols=3),
        Spacer(1, 2 * mm),
    ]
    nota = ("✔ El ECPN reconcilia (inicial + movimientos = final)." if ecpn.get("cuadra")
           else f"⚠ El ECPN NO reconcilia: diferencia de {_eur(ecpn.get('diferencia'))}.")
    bloques.append(_parrafo(nota, sty))
    for aviso in ecpn.get("advertencias") or []:
        bloques += [Spacer(1, 1.5 * mm), _parrafo(f"⚠ {aviso}", sty)]
    return bloques


def _tabla_flujos(ef, usable_w, sty):
    """Tablas del Estado de Flujos de Efectivo (explotación/inversión/financiación + conciliación
    con el efectivo real)."""
    exp, inv, fin = ef.get("explotacion", {}), ef.get("inversion", {}), ef.get("financiacion", {})
    _ETQ_EXP = {"resultado_del_ejercicio": "Resultado del ejercicio",
               "amortizacion": "Amortización (ajuste no monetario)",
               "variacion_capital_circulante": "Variación del capital circulante"}
    _ETQ_INV = {"capex_gmao": "Inversión en maquinaria/vehículos (GMAO)",
               "capex_inmovilizado_finanzas": "Inversión en inmovilizado (Finanzas)",
               "venta_activos": "Venta de activos",
               "variacion_inversiones_financieras_cp": "Variación inversiones financieras C/P"}
    _ETQ_FIN = {"variacion_deuda_financiera": "Variación de deuda financiera",
               "variacion_capital_y_aportaciones": "Variación de capital y aportaciones",
               "dividendos_pagados": "Dividendos pagados"}
    bloques = [
        E.tabla_importes("A) FLUJOS DE EXPLOTACIÓN", _filas_importe(exp, _ETQ_EXP),
                         "Total flujo de explotación", exp.get("total", 0), usable_w, sty),
        Spacer(1, 2 * mm),
        E.tabla_importes("B) FLUJOS DE INVERSIÓN",
                         _filas_importe(inv, _ETQ_INV, excluir=("total", "capex_duplicados_excluidos")),
                         "Total flujo de inversión", inv.get("total", 0), usable_w, sty),
        Spacer(1, 2 * mm),
        E.tabla_importes("C) FLUJOS DE FINANCIACIÓN", _filas_importe(fin, _ETQ_FIN),
                         "Total flujo de financiación", fin.get("total", 0), usable_w, sty),
        Spacer(1, 2 * mm),
        E.total_row("VARIACIÓN NETA DE EFECTIVO (CALCULADA)", ef.get("variacion_neta_calculada", 0),
                   usable_w, sty),
        Spacer(1, 2 * mm),
        E.grid_datos([("efectivo_inicial", "Efectivo inicial"), ("efectivo_final", "Efectivo final"),
                      ("variacion_neta_real_efectivo", "Variación real de efectivo")],
                     {"efectivo_inicial": _eur(ef.get("efectivo_inicial")),
                      "efectivo_final": _eur(ef.get("efectivo_final")),
                      "variacion_neta_real_efectivo": _eur(ef.get("variacion_neta_real_efectivo"))},
                     usable_w, sty, cols=3),
        Spacer(1, 2 * mm),
    ]
    nota = ("✔ El estado de flujos concilia con el efectivo real." if ef.get("cuadra")
           else f"⚠ No concilia con el efectivo real: ajuste de {_eur(ef.get('ajuste_conciliacion'))}.")
    bloques.append(_parrafo(nota, sty))
    for aviso in ef.get("advertencias") or []:
        bloques += [Spacer(1, 1.5 * mm), _parrafo(f"⚠ {aviso}", sty)]
    return bloques


def _bloque_memoria(memoria, usable_w, sty) -> list:
    """Sección 2 (Memoria) completa: actividad, declaración de cumplimiento, normas de valoración,
    inmovilizado, deudas, conciliación fiscal, partes vinculadas. Factorizado (mismo criterio que
    `_tabla_balance`/`_tabla_ecpn`/`_tabla_flujos`) para que
    `cierre_anual_pdf.generar_pdf_cierre_anual_unificado` lo reutilice tal cual: único punto de
    verdad del layout de la Memoria, sin reescribirlo en el documento unificado."""
    memoria = memoria or {}
    story = []
    act = memoria.get("actividad_empresa", {})
    story.append(E.seccion("2. Memoria · Actividad de la empresa", usable_w, sty))
    story.append(Spacer(1, 1.5 * mm))
    story.append(E.grid_datos(
        [("razon_social", "Razón social"), ("cif", "CIF"), ("domicilio", "Domicilio"),
         ("forma_juridica", "Forma jurídica"), ("objeto_social", "Objeto social")],
        act, usable_w, sty, cols=2))
    story.append(Spacer(1, 2 * mm))
    admins = act.get("administradores") or []
    if admins:
        story.append(E.tabla_columnas(
            [("nombre", "Administrador/representante"), ("cargo", "Cargo")],
            [{"nombre": a.get("nombre"), "cargo": a.get("cargo")} for a in admins],
            usable_w, sty))
    else:
        story.append(_parrafo("Sin representantes/administradores dados de alta en el "
                              "sistema.", sty))
    for aviso in act.get("avisos") or []:
        story.append(Spacer(1, 1.5 * mm))
        story.append(_parrafo(f"⚠ {aviso}", sty))
    story.append(Spacer(1, 5 * mm))

    story.append(E.seccion("2.1 Declaración de cumplimiento del marco normativo",
                           usable_w, sty))
    story.append(Spacer(1, 1.5 * mm))
    story.append(_parrafo(memoria.get("declaracion_cumplimiento", ""), sty))
    story.append(Spacer(1, 5 * mm))

    nv = memoria.get("normas_valoracion", {})
    story.append(E.seccion("2.2 Normas de valoración", usable_w, sty))
    story.append(Spacer(1, 1.5 * mm))
    for clave, titulo in (("inmovilizado_material", "Inmovilizado material"),
                          ("existencias", "Existencias")):
        bloque = nv.get(clave, {})
        story.append(_parrafo(f"<b>{titulo}</b> ({bloque.get('metodo', 'no disponible')}): "
                              f"{bloque.get('detalle', '')}", sty))
        story.append(Spacer(1, 2 * mm))
    story.append(PageBreak())

    inm = memoria.get("inmovilizado", {})
    story.append(E.seccion("2.3 Desglose del inmovilizado", usable_w, sty))
    story.append(Spacer(1, 1.5 * mm))
    story.append(E.tabla_columnas(
        [("codigo", "Código"), ("descripcion", "Descripción"), ("categoria", "Categoría"),
         ("valor_adquisicion", "Adquisición"), ("amortizado_acumulado", "Amort. acum."),
         ("valor_neto_contable", "VNC")],
        [{"codigo": a.get("codigo"), "descripcion": a.get("descripcion"),
          "categoria": a.get("categoria"), "valor_adquisicion": _eur(a.get("valor_adquisicion")),
          "amortizado_acumulado": _eur(a.get("amortizado_acumulado")),
          "valor_neto_contable": _eur(a.get("valor_neto_contable"))}
         for a in inm.get("activos", [])],
        usable_w, sty))
    story.append(Spacer(1, 2 * mm))
    story.append(E.total_row("VALOR NETO CONTABLE TOTAL", inm.get("total_valor_neto_contable"),
                             usable_w, sty))
    story.append(Spacer(1, 5 * mm))

    deu = memoria.get("deudas", {})
    story.append(E.seccion("2.4 Deudas y vencimientos", usable_w, sty))
    story.append(Spacer(1, 1.5 * mm))
    story.append(E.grid_datos(
        [("corto_plazo", "Corto plazo"), ("largo_plazo", "Largo plazo"), ("total", "Total")],
        {"corto_plazo": _eur(deu.get("corto_plazo")), "largo_plazo": _eur(deu.get("largo_plazo")),
         "total": _eur(deu.get("total"))}, usable_w, sty, cols=3))
    if deu.get("nota"):
        story.append(Spacer(1, 2 * mm))
        story.append(_parrafo(deu["nota"], sty))
    story.append(Spacer(1, 5 * mm))

    fis = memoria.get("conciliacion_fiscal", {})
    story.append(E.seccion("2.5 Conciliación fiscal (resultado contable vs base imponible IS)",
                           usable_w, sty))
    story.append(Spacer(1, 1.5 * mm))
    story.append(E.grid_datos(
        [("resultado_contable", "Resultado contable"),
         ("ajustes_extracontables", "Ajustes extracontables"),
         ("base_imponible_estimada", "Base imponible (est.)"),
         ("cuota_integra_estimada", "Cuota íntegra (est.)"),
         ("deducciones_estimadas", "Deducciones (est.)"),
         ("impuesto_final_estimado", "Impuesto final (est.)")],
        {k: (_eur(fis.get(k)) if k != "ajustes_extracontables" else _eur(fis.get(k)))
         for k in ("resultado_contable", "ajustes_extracontables", "base_imponible_estimada",
                  "cuota_integra_estimada", "deducciones_estimadas", "impuesto_final_estimado")},
        usable_w, sty, cols=2))
    story.append(Spacer(1, 2 * mm))
    story.append(_parrafo(fis.get("nota", ""), sty))
    story.append(PageBreak())

    pv = memoria.get("partes_vinculadas", {})
    story.append(E.seccion("2.6 Operaciones con partes vinculadas", usable_w, sty))
    story.append(Spacer(1, 1.5 * mm))
    story.append(_parrafo(pv.get("texto", ""), sty))
    if pv.get("operaciones"):
        story.append(Spacer(1, 2 * mm))
        story.append(E.tabla_columnas(
            [("nombre", "Nombre"), ("relacion", "Relación"), ("descripcion", "Descripción"),
             ("importe", "Importe"), ("fecha", "Fecha")],
            [{"nombre": o.get("nombre"), "relacion": o.get("relacion"),
              "descripcion": o.get("descripcion"), "importe": _eur(o.get("importe")),
              "fecha": str(o.get("fecha") or "")} for o in pv["operaciones"]],
            usable_w, sty))
    story.append(Spacer(1, 5 * mm))
    return story


def _bloque_informe_gestion(informe_gestion, anio, usable_w, sty) -> list:
    """Sección 3 (Informe de Gestión): evolución del negocio + riesgos e incertidumbres.
    Factorizado por el mismo motivo que `_bloque_memoria`."""
    informe_gestion = informe_gestion or {}
    story = []
    ev = informe_gestion.get("evolucion_negocio", {})
    story.append(E.seccion("3. Informe de Gestión · Evolución del negocio", usable_w, sty))
    story.append(Spacer(1, 1.5 * mm))
    a_act, a_ant = ev.get("actual", {}), ev.get("anterior", {})
    story.append(E.grid_datos(
        [("ing_a", f"Ingresos {ev.get('anio', anio)}"),
         ("gas_a", f"Gastos {ev.get('anio', anio)}"),
         ("res_a", f"Resultado {ev.get('anio', anio)}"),
         ("ing_b", f"Ingresos {ev.get('anio_anterior', anio - 1)}"),
         ("gas_b", f"Gastos {ev.get('anio_anterior', anio - 1)}"),
         ("res_b", f"Resultado {ev.get('anio_anterior', anio - 1)}")],
        {"ing_a": _eur(a_act.get("ingresos")), "gas_a": _eur(a_act.get("gastos")),
         "res_a": _eur(a_act.get("resultado")), "ing_b": _eur(a_ant.get("ingresos")),
         "gas_b": _eur(a_ant.get("gastos")), "res_b": _eur(a_ant.get("resultado"))},
        usable_w, sty, cols=3))
    story.append(Spacer(1, 5 * mm))

    ries = informe_gestion.get("riesgos_incertidumbres", {})
    story.append(E.seccion("3.1 Riesgos e incertidumbres", usable_w, sty))
    story.append(Spacer(1, 1.5 * mm))
    story.append(_parrafo(ries.get("texto", ""), sty))
    if ries.get("senales"):
        story.append(Spacer(1, 2 * mm))
        story.append(E.tabla_columnas(
            [("ratio", "Ratio"), ("valor", "Valor"), ("nivel", "Nivel"), ("texto", "Detalle")],
            [{"ratio": s.get("ratio"), "valor": s.get("valor"), "nivel": s.get("nivel"),
              "texto": s.get("texto")} for s in ries["senales"]],
            usable_w, sty))
    story.append(PageBreak())
    return story


def _bloque_propuesta(propuesta, usable_w, sty) -> list:
    """Sección 4 (Propuesta de Aplicación del Resultado). Factorizado por el mismo motivo que
    `_bloque_memoria`/`_bloque_informe_gestion`."""
    propuesta = propuesta or {}
    story = [
        E.seccion("4. Propuesta de Aplicación del Resultado", usable_w, sty),
        Spacer(1, 1.5 * mm),
        E.grid_datos(
            [("resultado", "Resultado del ejercicio"), ("capital_social", "Capital social"),
             ("reserva_legal_actual", "Reserva legal (actual)"),
             ("reserva_legal_tope_20pct", "Tope reserva legal (20% capital)"),
             ("dotacion_reserva_legal_propuesta", "Dotación propuesta a reserva legal"),
             ("base_libre_disposicion", "Base de libre disposición"),
             ("compensacion_perdidas_propuesta", "Compensación de pérdidas propuesta")],
            {k: _eur(propuesta.get(k)) for k in
             ("resultado", "capital_social", "reserva_legal_actual", "reserva_legal_tope_20pct",
              "dotacion_reserva_legal_propuesta", "base_libre_disposicion",
              "compensacion_perdidas_propuesta")},
            usable_w, sty, cols=2),
        Spacer(1, 2 * mm),
        _parrafo(propuesta.get("propuesta_texto", ""), sty),
    ]
    for aviso in propuesta.get("avisos") or []:
        story.append(Spacer(1, 2 * mm))
        story.append(_parrafo(f"⚠ {aviso}", sty))
    if propuesta.get("nota_legal"):
        story.append(Spacer(1, 2 * mm))
        nota = sty["sub"].clone("nota_prop")
        nota.textColor = colors.HexColor("#555555")
        story.append(Paragraph(propuesta["nota_legal"], nota))
    return story


def generar_pdf_cuentas_anuales(anio, id_empresa, memoria, informe_gestion, propuesta,
                                 datos_empresa=None, balance=None, ecpn=None,
                                 estado_flujos=None) -> str | None:
    """Genera el PDF de Memoria + Informe de Gestión + Propuesta de Aplicación del Resultado del
    ejercicio `anio`, a partir de los dicts YA calculados. Devuelve la ruta, o None si falla.

    `balance`/`ecpn`/`estado_flujos` son OPCIONALES (retrocompatible: por defecto `None`, y la
    sección 1 sigue mostrando el texto de marcador de posición, igual que antes de este cambio)
    — si se pasan (dicts de `balance_situacion.generar_balance` / `ecpn.generar_ecpn` /
    `estado_flujos.generar_estado_flujos`), se renderizan como tablas reales con los mismos
    helpers (`tabla_columnas`/`tabla_importes`) que ya usa el resto de este fichero."""
    try:
        anio = int(anio)
        memoria = memoria or {}
        informe_gestion = informe_gestion or {}
        propuesta = propuesta or {}
        datos_empresa = datos_empresa or {}
        ruta = os.path.join(_dir_cuentas_anuales(), f"CUENTAS-ANUALES-{anio}.pdf")

        doc = SimpleDocTemplate(ruta, pagesize=A4, leftMargin=16 * mm, rightMargin=16 * mm,
                                topMargin=14 * mm, bottomMargin=14 * mm,
                                title=f"Cuentas Anuales {anio}")
        usable_w = doc.width
        sty = E.estilos()

        emp_nombre = datos_empresa.get("nombre") or ""
        emp_cif = datos_empresa.get("cif") or ""
        emp_dir = datos_empresa.get("dir") or ""
        fecha_gen = datetime.now().strftime("%d/%m/%Y %H:%M")

        story = [
            Paragraph(f"CUENTAS ANUALES {anio}", sty["tit"]),
            Paragraph(f"{emp_nombre}" + (f" · CIF {emp_cif}" if emp_cif else "") +
                     (f" · {emp_dir}" if emp_dir else ""), sty["sub"]),
            Paragraph(f"Generado: {fecha_gen}", sty["sub"]),
            Spacer(1, 4 * mm),

            E.seccion("1. Balance de situación / ECPN / Estado de flujos de efectivo",
                     usable_w, sty),
            Spacer(1, 1.5 * mm),
        ]

        if balance:
            story.append(E.seccion("1.1 Balance de situación", usable_w, sty))
            story.append(Spacer(1, 1.5 * mm))
            story += _tabla_balance(balance, usable_w, sty)
            story.append(PageBreak())
        if ecpn:
            story.append(E.seccion("1.2 Estado de cambios en el patrimonio neto (ECPN)",
                                   usable_w, sty))
            story.append(Spacer(1, 1.5 * mm))
            story += _tabla_ecpn(ecpn, usable_w, sty)
            story.append(Spacer(1, 5 * mm))
        if estado_flujos:
            story.append(E.seccion("1.3 Estado de flujos de efectivo (método indirecto)",
                                   usable_w, sty))
            story.append(Spacer(1, 1.5 * mm))
            story += _tabla_flujos(estado_flujos, usable_w, sty)
            story.append(PageBreak())
        if not (balance or ecpn or estado_flujos):
            story.append(_parrafo("[Espacio reservado — estas tablas las genera un servicio "
                                  "hermano (balance_situacion.py / ecpn.py / estado_flujos.py) y "
                                  "las integra el orquestador de Cuentas Anuales en esta sección "
                                  "cuando se le pasan los dicts correspondientes.]", sty))
        story.append(Spacer(1, 5 * mm))

        # ── Memoria / Informe de Gestión / Propuesta de Aplicación del Resultado ────────────────
        story += _bloque_memoria(memoria, usable_w, sty)
        story += _bloque_informe_gestion(informe_gestion, anio, usable_w, sty)
        story += _bloque_propuesta(propuesta, usable_w, sty)

        pie = sty["sub"].clone("pie"); pie.fontSize = 7; pie.textColor = colors.HexColor("#888888")
        story.append(Spacer(1, 8 * mm))
        story.append(Paragraph(
            f"Documento generado por Smart Manager · CUENTAS-ANUALES-{anio} · {fecha_gen}", pie))
        doc.build(story)
        return ruta
    except Exception as e:
        logger.error("generar_pdf_cuentas_anuales(%s): %s", anio, e)
        return None
