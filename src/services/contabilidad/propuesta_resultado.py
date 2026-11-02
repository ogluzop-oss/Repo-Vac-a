"""
Propuesta de Aplicación del Resultado (Memoria/Cuentas Anuales). Calcula la dotación MÍNIMA
legalmente exigida a reserva legal (art. 274 LSC: 10% del beneficio del ejercicio hasta que la
reserva legal alcance el 20% del capital social) y dimensiona el resto del resultado como
"base de libre disposición" — una PROPUESTA pendiente de aprobación de los administradores/junta,
nunca una decisión automática ni un asiento contable.

Fuente de las cifras:
- `resultado` del ejercicio: `services.contabilidad.informes.perdidas_ganancias` (motor PyG real,
  ya usado por el resto de Contabilidad — no se recalcula).
- `capital_social`/`reserva_legal` actuales: saldo REAL de las cuentas PGC 100/112
  (`informes.mayor`), acumulado hasta el 31/12 del ejercicio — no un campo nuevo inventado: estas
  cuentas ya existen en el plan contable (`plan_pgc.py`) y se alimentan de los asientos reales
  (apertura/cierre/asientos manuales) ya registrados por el usuario.

Honestidad (regla dura): si la cuenta 100 no tiene saldo (nadie ha registrado el capital social
contablemente), NO se inventa un capital social — se avisa explícitamente y la dotación se calcula
SOLO con el 10% legal mínimo, sin poder verificar el tope del 20% (que queda señalado como
pendiente de revisión manual). Un resultado negativo NUNCA dota reserva legal — se propone
compensación de pérdidas.
"""

import logging

logger = logging.getLogger("contab.propuesta_resultado")

PCT_DOTACION_LEGAL = 0.10     # Art. 274 LSC: 10% del beneficio
PCT_TOPE_RESERVA_LEGAL = 0.20  # ... hasta que la reserva legal alcance el 20% del capital social

_CUENTA_CAPITAL_SOCIAL = "100"
_CUENTA_RESERVA_LEGAL = "112"


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


def _saldo_acreedor_a_fecha(codigo_cuenta, id_empresa, hasta) -> float:
    """Saldo de una cuenta de naturaleza ACREEDORA (patrimonio neto: capital/reservas) acumulado
    hasta `hasta` (inclusive). `informes.mayor` devuelve saldo=Σ(debe-haber); una cuenta acreedora
    con saldo normal da un número negativo, así que se invierte el signo aquí."""
    from src.services.contabilidad.informes import mayor
    r = mayor(codigo_cuenta, id_empresa=id_empresa, hasta=hasta)
    return round(-float(r.get("saldo") or 0), 2)


def calcular_propuesta_aplicacion(anio, id_empresa=None) -> dict:
    """Propuesta de aplicación del resultado del ejercicio `anio`. Devuelve un dict con el
    resultado, capital social y reserva legal REALES, la dotación legal mínima calculada, y el
    remanente que los administradores deben configurar/aprobar (dividendos / reservas voluntarias /
    remanente) — o, si el resultado es negativo, la propuesta de compensación de pérdidas.
    NUNCA contabiliza nada: es solo el cálculo para que la Memoria lo muestre como propuesta."""
    anio = int(anio)
    id_empresa = _empresa(id_empresa)
    avisos = []

    from src.services.contabilidad.informes import perdidas_ganancias
    pyg = perdidas_ganancias(id_empresa=id_empresa, anio=anio) or {}
    resultado = round(float(pyg.get("resultado") or 0), 2)

    hasta = f"{anio}-12-31"
    capital_social = _saldo_acreedor_a_fecha(_CUENTA_CAPITAL_SOCIAL, id_empresa, hasta)
    reserva_legal_actual = _saldo_acreedor_a_fecha(_CUENTA_RESERVA_LEGAL, id_empresa, hasta)

    capital_social_registrado = capital_social > 0.0
    if not capital_social_registrado:
        avisos.append(
            "La cuenta 100 «Capital social» no tiene saldo registrado en Contabilidad para esta "
            "empresa: no se puede verificar el límite legal del 20% del capital social. La "
            "dotación propuesta usa solo el mínimo del 10% del beneficio; revisar manualmente "
            "contra la escritura de constitución antes de aprobar.")

    if resultado <= 0:
        dotacion_reserva_legal = 0.0
        reserva_legal_tras_dotacion = reserva_legal_actual
        compensacion_perdidas = round(-resultado, 2) if resultado < 0 else 0.0
        base_libre_disposicion = 0.0
        tipo_resultado = "perdida" if resultado < 0 else "nulo"
        if resultado < 0:
            propuesta_texto = (
                f"El ejercicio {anio} arroja una PÉRDIDA de {abs(resultado):,.2f} €. No procede "
                "ninguna dotación a reserva legal (solo se dota con beneficio). Se propone "
                "compensación de pérdidas con cargo a reservas voluntarias/remanente de "
                "ejercicios anteriores, sujeto a disponibilidad y a la aprobación de los "
                "administradores/junta.")
        else:
            propuesta_texto = (
                f"El ejercicio {anio} arroja un resultado NULO (0,00 €). No procede ninguna "
                "aplicación del resultado.")
    else:
        tope_reserva_legal = round(capital_social * PCT_TOPE_RESERVA_LEGAL, 2)
        margen_hasta_tope = max(0.0, round(tope_reserva_legal - reserva_legal_actual, 2))
        dotacion_10pct = round(resultado * PCT_DOTACION_LEGAL, 2)
        if capital_social_registrado:
            dotacion_reserva_legal = round(min(dotacion_10pct, margen_hasta_tope), 2)
            if dotacion_reserva_legal < dotacion_10pct:
                avisos.append(
                    f"La reserva legal ya está a {margen_hasta_tope:,.2f} € del tope del 20% del "
                    "capital social: la dotación propuesta se ha reducido respecto al 10% íntegro "
                    "del beneficio para no superar ese límite.")
        else:
            dotacion_reserva_legal = dotacion_10pct
        reserva_legal_tras_dotacion = round(reserva_legal_actual + dotacion_reserva_legal, 2)
        compensacion_perdidas = 0.0
        base_libre_disposicion = round(resultado - dotacion_reserva_legal, 2)
        tipo_resultado = "beneficio"
        propuesta_texto = (
            f"El ejercicio {anio} arroja un BENEFICIO de {resultado:,.2f} €. Dotación mínima legal "
            f"propuesta a reserva legal: {dotacion_reserva_legal:,.2f} € (art. 274 LSC). Queda un "
            f"remanente de {base_libre_disposicion:,.2f} € como base de libre disposición: "
            "PENDIENTE de que los administradores configuren su destino (dividendos / reservas "
            "voluntarias / remanente), sujeto a aprobación de la junta. Este sistema no decide "
            "ese reparto ni lo contabiliza automáticamente.")

    return {
        "anio": anio,
        "id_empresa": id_empresa,
        "resultado": resultado,
        "tipo_resultado": tipo_resultado,
        "capital_social": capital_social,
        "capital_social_registrado": capital_social_registrado,
        "reserva_legal_actual": reserva_legal_actual,
        "reserva_legal_tope_20pct": round(capital_social * PCT_TOPE_RESERVA_LEGAL, 2),
        "dotacion_reserva_legal_propuesta": dotacion_reserva_legal,
        "reserva_legal_tras_dotacion": reserva_legal_tras_dotacion,
        "compensacion_perdidas_propuesta": compensacion_perdidas,
        "base_libre_disposicion": base_libre_disposicion,
        "propuesta_texto": propuesta_texto,
        "avisos": avisos,
        "nota_legal": (
            "Propuesta de aplicación del resultado pendiente de aprobación por los "
            "administradores/junta general — ninguna cifra de esta propuesta se contabiliza "
            "automáticamente. Validar con un asesor fiscal/contable antes de formalizar."),
    }
