"""
Descansos mínimos legales — Horarios (RRHH Fase E, punto 4 del plan de "bolsa de horas").

Motor PURO (sin Qt, sin BD): a partir de los turnos de una semana de un empleado tal como ya los
guarda la rejilla de `src/rrhh/gui/horarios.py` (inicio/fin por día, minutos desde medianoche),
comprueba dos descansos mínimos legales:

  - **Descanso diario**: al menos 12h entre el FIN de un turno y el INICIO del siguiente.
  - **Descanso semanal**: al menos 1,5 días (36h) de descanso consecutivo en algún punto de la
    semana.

Cálculo puramente a partir de los propios datos de inicio/fin que la rejilla ya guarda — no
requiere ninguna tabla nueva (ver CLAUDE.md / plan Fase E, punto 4). El cruce de una tabla a la
siguiente (turno del domingo de una semana + turno del lunes de la semana siguiente) es un
"stretch goal" explícitamente aplazado por el plan: este módulo evalúa cada tabla semanal de
forma AISLADA (best effort), incluyendo los huecos entre el inicio/fin de la semana y el primer/
último turno como posibles ventanas de descanso semanal.
"""

import datetime as _dt

DIAS_LABEL = ["lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo"]

DESCANSO_DIARIO_MIN_MINUTOS = 12 * 60
DESCANSO_SEMANAL_MIN_MINUTOS = 36 * 60  # 1,5 días


def _shifts_ordenados(turnos: list) -> list:
    """`turnos`: 7 elementos alineados lunes(0)..domingo(6); cada uno `None` (sin turno ese día —
    ausencia, festivo o día libre) o `{"ini_min": int, "fin_min": int}` (turno dentro del MISMO
    día, `fin_min >= ini_min`, consistente con `_TurnoCelda`, que no permite turnos que crucen
    medianoche). Devuelve `[(dia_idx, ini_min, fin_min), ...]` en orden de día."""
    shifts = []
    for i, t in enumerate(turnos or []):
        if not t:
            continue
        ini = t.get("ini_min")
        fin = t.get("fin_min")
        if ini is None or fin is None or fin < ini:
            continue
        shifts.append((i, int(ini), int(fin)))
    return shifts


def verificar_descansos_semana(turnos: list) -> list:
    """Devuelve la lista de violaciones detectadas para UNA semana de UN empleado:

      - `{"tipo": "diario", "dia_a": int, "dia_b": int, "horas_descanso": float, "mensaje": str}`
        por cada par de turnos consecutivos con menos de 12h de descanso entre ellos.
      - como mucho UNA `{"tipo": "semanal", "horas_descanso": float, "mensaje": str}` si el mayor
        hueco de descanso encontrado en la semana (incluidos los extremos, antes del primer turno
        y después del último) es inferior a 36h.

    Lista vacía si no hay turnos o no se detecta ninguna violación."""
    violaciones = []
    shifts = _shifts_ordenados(turnos)
    if not shifts:
        return violaciones

    gaps = []  # huecos de descanso considerados para el cómputo del descanso semanal (minutos)

    # Hueco al PRINCIPIO de la semana: desde el lunes 00:00 hasta el inicio del primer turno.
    primer_dia, primer_ini, _primer_fin = shifts[0]
    gaps.append(primer_dia * 1440 + primer_ini)

    # Huecos ENTRE turnos consecutivos (aquí es donde se comprueba el descanso DIARIO de 12h).
    for (d1, _i1, f1), (d2, i2, _f2) in zip(shifts, shifts[1:]):
        descanso_min = (d2 - d1) * 1440 + (i2 - f1)
        gaps.append(descanso_min)
        if descanso_min < DESCANSO_DIARIO_MIN_MINUTOS:
            horas = round(descanso_min / 60, 1)
            violaciones.append({
                "tipo": "diario",
                "dia_a": d1,
                "dia_b": d2,
                "horas_descanso": horas,
                "mensaje": (
                    f"Solo {horas}h de descanso entre el turno del {DIAS_LABEL[d1]} "
                    f"y el del {DIAS_LABEL[d2]}."
                ),
            })

    # Hueco al FINAL de la semana: desde el fin del último turno hasta el domingo 24:00.
    ultimo_dia, _ultimo_ini, ultimo_fin = shifts[-1]
    gaps.append((6 - ultimo_dia) * 1440 + (1440 - ultimo_fin))

    max_gap = max(gaps) if gaps else 0
    if max_gap < DESCANSO_SEMANAL_MIN_MINUTOS:
        horas_sem = round(max_gap / 60, 1)
        violaciones.append({
            "tipo": "semanal",
            "horas_descanso": horas_sem,
            "mensaje": (
                f"El descanso semanal es de solo {horas_sem}h "
                f"(mínimo legal: 36h / 1,5 días)."
            ),
        })

    return violaciones
